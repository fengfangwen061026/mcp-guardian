import json

import pytest

from guardian.bash_classifier import classify_command
from guardian.dispatch import dispatch
from guardian.persist import OffsetStore
from guardian.policy_loader import PolicyConfigError, load_policy
from guardian.roots import configured_roots
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="policy_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


def write_policy(root, data, local=None):
    policy_dir = root / ".guardian"
    policy_dir.mkdir()
    (policy_dir / "policy.json").write_text(json.dumps(data), encoding="utf-8")
    if local is not None:
        (policy_dir / "policy.local.json").write_text(json.dumps(local), encoding="utf-8")


def test_defaults_without_policy_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GUARDIAN_ROOTS", raising=False)
    monkeypatch.delenv("GUARDIAN_ROOT", raising=False)

    policy = load_policy(tmp_path)

    assert policy.roots == ()
    assert policy.sensitive_rules == ()
    assert policy.bash_rules == ()


def test_policy_json_configures_roots(monkeypatch, tmp_path):
    write_policy(tmp_path, {"roots": ["src"]})
    monkeypatch.chdir(tmp_path)

    assert configured_roots() == [(tmp_path / "src").resolve()]


def test_env_roots_override_policy(monkeypatch, tmp_path):
    env_root = tmp_path / "env"
    write_policy(tmp_path, {"roots": ["src"]})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GUARDIAN_ROOTS", str(env_root))

    assert configured_roots() == [env_root.resolve()]


@pytest.mark.asyncio
async def test_policy_can_override_sensitive_ask(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"sensitive_paths": {"ask": ["*.secret"]}})
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.secret"
    target.write_text("x", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["error_type"] == "SensitivePathApprovalRequired"


@pytest.mark.asyncio
async def test_policy_local_overrides_policy(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"sensitive_paths": {"ask": ["*.secret"]}}, {"sensitive_paths": {"allow": ["*.secret"]}})
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.secret"
    target.write_text("x", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["success"] is True


@pytest.mark.asyncio
async def test_policy_allow_cannot_override_hard_sensitive_deny(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"sensitive_paths": {"allow": ["*.pem"]}})
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "key.pem"
    target.write_text("secret", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["error_type"] == "SensitivePathBlocked"


@pytest.mark.asyncio
async def test_sensitive_deny_wins_over_allow(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"sensitive_paths": {"allow": ["*.secret"], "deny": ["*.secret"]}})
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.secret"
    target.write_text("x", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["error_type"] == "SensitivePathBlocked"


@pytest.mark.asyncio
async def test_sensitive_list_form_deny_wins_over_earlier_allow(session, store, monkeypatch, tmp_path):
    write_policy(
        tmp_path,
        {"sensitive_paths": [
            {"action": "allow", "patterns": ["*.secret"]},
            {"action": "deny", "patterns": ["*.secret"]},
        ]},
    )
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "file.secret"
    target.write_text("x", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["error_type"] == "SensitivePathBlocked"


def test_bash_policy_can_override_allow(monkeypatch, tmp_path):
    write_policy(tmp_path, {"bash": {"deny": ["echo *"]}})
    monkeypatch.chdir(tmp_path)

    decision = classify_command("echo hello")

    assert decision.decision == "deny"
    assert decision.category == "POLICY"


def test_bash_policy_can_override_ask(monkeypatch, tmp_path):
    write_policy(tmp_path, {"bash": {"ask": [{"patterns": ["python scripts/*"], "risk": 0.7, "reasons": ["custom ask"]}]}})
    monkeypatch.chdir(tmp_path)

    decision = classify_command("python scripts/deploy.py")

    assert decision.decision == "ask"
    assert decision.reasons == ["custom ask"]


@pytest.mark.asyncio
async def test_run_bash_uses_cwd_policy(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"bash": {"deny": ["echo *"]}})
    monkeypatch.chdir(tmp_path.parent)

    result = await dispatch(session, "guardian_run_bash", {"command": "echo hello", "cwd": str(tmp_path)}, store)

    assert result["error_type"] == "BashPolicyDenied"


@pytest.mark.asyncio
async def test_bash_policy_cannot_override_handler_security(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"bash": {"allow": ["sudo *"]}})
    monkeypatch.chdir(tmp_path)

    result = await dispatch(session, "guardian_run_bash", {"command": "sudo apt install x", "cwd": str(tmp_path)}, store)

    assert result["error_type"] == "SecurityError"


@pytest.mark.asyncio
async def test_invalid_bash_policy_returns_structured_error(session, store, monkeypatch, tmp_path):
    write_policy(tmp_path, {"bash": {"ask": [{"patterns": ["echo *"], "risk": "bad"}]}})
    monkeypatch.chdir(tmp_path)

    result = await dispatch(session, "guardian_run_bash", {"command": "echo hello", "cwd": str(tmp_path)}, store)

    assert result["error_type"] == "PolicyConfigError"
    assert "PolicyConfigError" in result["error"]


@pytest.mark.asyncio
async def test_invalid_policy_returns_structured_error(session, store, monkeypatch, tmp_path):
    policy_dir = tmp_path / ".guardian"
    policy_dir.mkdir()
    (policy_dir / "policy.json").write_text("{bad", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["success"] is False
    assert result["error_type"] == "PolicyConfigError"


def test_invalid_policy_raises_for_direct_loader(monkeypatch, tmp_path):
    policy_dir = tmp_path / ".guardian"
    policy_dir.mkdir()
    (policy_dir / "policy.json").write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(PolicyConfigError):
        load_policy(tmp_path)
