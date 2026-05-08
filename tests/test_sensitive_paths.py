import pytest

from guardian.dispatch import dispatch
from guardian.persist import OffsetStore
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="sensitive_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_read_env_requires_approval(session, store, tmp_path):
    target = tmp_path / ".env"
    target.write_text("TOKEN=x", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["success"] is False
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["error_type"] == "SensitivePathApprovalRequired"


@pytest.mark.asyncio
async def test_write_env_requires_approval(session, store, tmp_path):
    target = tmp_path / ".env"

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "TOKEN=x"}, store)

    assert result["success"] is False
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["error_type"] == "SensitivePathApprovalRequired"


@pytest.mark.asyncio
async def test_read_private_key_denied(session, store, tmp_path):
    target = tmp_path / "id_rsa"
    target.write_text("secret", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["success"] is False
    assert result["error_type"] == "SensitivePathBlocked"


@pytest.mark.asyncio
async def test_write_pem_denied(session, store, tmp_path):
    target = tmp_path / "cert.pem"

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "secret"}, store)

    assert result["success"] is False
    assert result["error_type"] == "SensitivePathBlocked"


@pytest.mark.asyncio
async def test_plain_code_file_allowed(session, store, tmp_path):
    target = tmp_path / "app.py"

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "print(1)\n"}, store)

    assert result["success"] is True
