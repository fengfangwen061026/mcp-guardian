import pytest

from guardian.dispatch import dispatch
from guardian.persist import OffsetStore
from guardian.roots import roots_status
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="roots_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_roots_default_disabled(monkeypatch, session, store, tmp_path):
    monkeypatch.delenv("GUARDIAN_ROOTS", raising=False)
    monkeypatch.delenv("GUARDIAN_ROOT", raising=False)
    target = tmp_path / "a.txt"
    target.write_text("ok", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["success"] is True
    assert roots_status()["enabled"] is False


@pytest.mark.asyncio
async def test_roots_block_read_outside(monkeypatch, session, store, tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.txt"
    allowed.mkdir()
    outside.write_text("no", encoding="utf-8")
    monkeypatch.setenv("GUARDIAN_ROOTS", str(allowed))

    result = await dispatch(session, "guardian_read_file", {"path": str(outside)}, store)

    assert result["success"] is False
    assert result["error_class"] == "SECURITY"
    assert result["error_type"] == "PathOutsideRoot"


@pytest.mark.asyncio
async def test_roots_allow_write_inside(monkeypatch, session, store, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("GUARDIAN_ROOTS", str(allowed))

    result = await dispatch(session, "guardian_write_file", {"path": str(allowed / "a.txt"), "content": "ok"}, store)

    assert result["success"] is True


@pytest.mark.asyncio
async def test_roots_block_bash_cwd_outside(monkeypatch, session, store, tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("GUARDIAN_ROOTS", str(allowed))

    result = await dispatch(session, "guardian_run_bash", {"command": "echo x", "cwd": str(outside)}, store)

    assert result["success"] is False
    assert result["error_type"] == "PathOutsideRoot"


@pytest.mark.asyncio
async def test_status_reports_roots(monkeypatch, session, store, tmp_path):
    monkeypatch.setenv("GUARDIAN_ROOT", str(tmp_path))

    result = await dispatch(session, "guardian_status", {}, store)

    assert result["success"] is True
    assert result["roots"]["enabled"] is True
    assert result["roots"]["allowed_roots"] == [str(tmp_path.resolve())]
