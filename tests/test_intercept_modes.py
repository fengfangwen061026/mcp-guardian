from unittest.mock import patch

from guardian.intercept import InterceptionMode, detect_mode, precheck_call
from guardian.state import SessionState


def test_detect_mode_thresholds():
    session = SessionState("modes")
    assert detect_mode(session) == InterceptionMode.ADAPTIVE
    session.total_prechecks = 10
    session.ack_successes = 9
    assert detect_mode(session) == InterceptionMode.STRICT
    session.ack_successes = 5
    assert detect_mode(session) == InterceptionMode.ADAPTIVE
    session.ack_successes = 3
    assert detect_mode(session) == InterceptionMode.PASSIVE


def test_strict_medium_risk_requires_model_ack():
    session = SessionState("modes")
    session.total_prechecks = 10
    session.ack_successes = 9
    with patch("guardian.risk.compute_risk", return_value=0.7):
        result = precheck_call(session, "guardian_run_bash", {"command": "echo test"})
    assert result["error"] == "MODEL_ACK_REQUIRED"
    assert result["ack_token"] in session.pending_fallbacks


def test_strict_high_risk_requires_approval():
    session = SessionState("modes")
    session.total_prechecks = 10
    session.ack_successes = 9
    result = precheck_call(session, "guardian_write_file", {"path": "/etc/app.conf", "content": "x"})
    assert result["error"] == "APPROVAL_REQUIRED"
    assert "ack_token" not in result


def test_adaptive_medium_risk_note_and_passive_allows():
    session = SessionState("modes")
    params = {"path": "project.txt", "content": "x"}
    assert precheck_call(session, "guardian_write_file", params) is None
    session.total_prechecks = 10
    session.ack_successes = 1
    assert precheck_call(session, "guardian_write_file", {"path": "/etc/app.conf", "content": "x"}) is None
