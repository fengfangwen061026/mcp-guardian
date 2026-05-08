import sqlite3
from unittest.mock import patch

import pytest

from guardian.approvals import sanitize_params
from guardian.dispatch import dispatch
from guardian.intercept import precheck_call
from guardian.persist import OffsetStore
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="approval_flow_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_high_risk_bash_records_pending_approval_without_ack(session, store, tmp_path):
    result = await dispatch(
        session,
        "guardian_run_bash",
        {"command": "git reset --hard", "cwd": str(tmp_path), "description": "discard local changes after user approval"},
        store,
    )

    assert result["success"] is False
    assert result["status"] == "APPROVAL_REQUIRED"
    assert "approval_id" in result
    assert "ack_token" not in result

    pending = await dispatch(session, "guardian_pending_approvals", {}, store)
    assert pending["count"] == 1
    approval = pending["approvals"][0]
    assert approval["approval_id"] == result["approval_id"]
    assert approval["session_id"] == session.session_id
    assert approval["tool_name"] == "guardian_run_bash"
    assert approval["risk"] == result["risk"]
    assert approval["status"] == "pending"


@pytest.mark.asyncio
async def test_sensitive_path_approval_sanitizes_large_content(session, store, tmp_path):
    target = tmp_path / ".env"
    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "TOKEN=secret"}, store)

    assert result["status"] == "APPROVAL_REQUIRED"
    pending = await dispatch(session, "guardian_pending_approvals", {}, store)
    assert pending["approvals"][0]["approval_id"] == result["approval_id"]
    assert "params" not in pending["approvals"][0]
    with sqlite3.connect(str(store.db_path)) as conn:
        params_json = conn.execute("SELECT params_json FROM approvals WHERE approval_id = ?", (result["approval_id"],)).fetchone()[0]
    assert "[REDACTED_TEXT length=12]" in params_json


@pytest.mark.asyncio
async def test_expired_approvals_are_not_returned(store):
    session = SessionState(session_id="expired_approval_test")
    approval = await store.create_approval(session.session_id, "guardian_run_bash", "{}", 0.9, "[]", ttl_seconds=-1)

    pending = await dispatch(session, "guardian_pending_approvals", {}, store)

    assert pending["count"] == 0
    with sqlite3.connect(str(store.db_path)) as conn:
        status = conn.execute("SELECT status FROM approvals WHERE approval_id = ?", (approval["approval_id"],)).fetchone()[0]
    assert status == "expired"


def test_medium_risk_precheck_returns_model_ack():
    session = SessionState(session_id="model_ack_test")
    session.total_prechecks = 10
    session.ack_successes = 9

    with patch("guardian.risk.compute_risk", return_value=0.7):
        result = precheck_call(session, "guardian_run_bash", {"command": "echo test"})

    assert result["status"] == "MODEL_ACK_REQUIRED"
    assert result["error_type"] == "MODEL_ACK_REQUIRED"
    assert result["ack_token"] in session.pending_fallbacks


def test_high_risk_precheck_requires_approval_without_ack():
    session = SessionState(session_id="approval_precheck_test")
    session.total_prechecks = 10
    session.ack_successes = 9

    result = precheck_call(session, "guardian_write_file", {"path": "/etc/app.conf", "content": "x"})

    assert result["status"] == "APPROVAL_REQUIRED"
    assert "ack_token" not in result


def test_passive_mode_still_requires_high_risk_approval():
    session = SessionState(session_id="passive_approval_test")
    session.total_prechecks = 10
    session.ack_successes = 1

    result = precheck_call(session, "guardian_write_file", {"path": "/etc/app.conf", "content": "x"})

    assert result["status"] == "APPROVAL_REQUIRED"


def test_model_ack_is_bound_to_tool_and_params():
    session = SessionState(session_id="ack_scope_test")
    session.total_prechecks = 10
    session.ack_successes = 9
    params = {"command": "echo test"}
    with patch("guardian.risk.compute_risk", return_value=0.7):
        result = precheck_call(session, "guardian_run_bash", params)

    token = result["ack_token"]
    assert precheck_call(session, "guardian_run_bash", {"command": "echo changed", "_ack": token})["error_type"] == "ack_scope_mismatch"
    assert precheck_call(session, "guardian_write_file", {"path": "a.txt", "content": "x", "_ack": token})["error_type"] == "ack_scope_mismatch"
    assert precheck_call(session, "guardian_run_bash", {"command": "echo test", "_ack": token}) is None


def test_sanitize_params_redacts_secret_like_keys_and_text_fields():
    params = sanitize_params({"api_key": "abc", "content": "secret", "command": "deploy token=abc", "nested": {"password": "p"}, "items": [{"token": "t"}]})

    assert params["api_key"] == "[REDACTED]"
    assert params["content"] == "[REDACTED_TEXT length=6]"
    assert params["command"] == "deploy token=[REDACTED]"
    assert params["nested"]["password"] == "[REDACTED]"
    assert params["items"][0]["token"] == "[REDACTED]"
