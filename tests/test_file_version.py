import pytest

from guardian.dispatch import dispatch
from guardian.persist import OffsetStore
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="file_version_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_read_returns_read_id_and_file_hash(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello\n", encoding="utf-8")

    result = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    assert result["success"] is True
    assert result["read_id"].startswith("read_")
    assert result["file_hash"].startswith("sha256:")
    assert result["size"] == target.stat().st_size
    assert isinstance(result["mtime_ns"], int)


@pytest.mark.asyncio
async def test_edit_requires_read_id_or_hash(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello\n", encoding="utf-8")

    result = await dispatch(session, "guardian_edit_file", {"path": str(target), "old_str": "hello", "new_str": "hi"}, store)

    assert result["success"] is False
    assert result["error_type"] == "expected_file_version_required"


@pytest.mark.asyncio
async def test_edit_with_read_id_success_and_invalidates_old_read(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello\n", encoding="utf-8")
    read = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    result = await dispatch(session, "guardian_edit_file", {"path": str(target), "old_str": "hello", "new_str": "hi", "expected_read_id": read["read_id"]}, store)

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "hi\n"
    assert read["read_id"] not in session.read_versions


@pytest.mark.asyncio
async def test_edit_detects_file_changed_since_read(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello\n", encoding="utf-8")
    read = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)
    target.write_text("hello outside\n", encoding="utf-8")

    result = await dispatch(session, "guardian_edit_file", {"path": str(target), "old_str": "hello", "new_str": "hi", "expected_read_id": read["read_id"]}, store)

    assert result["success"] is False
    assert result["error_type"] == "file_changed_since_read"


@pytest.mark.asyncio
async def test_edit_with_file_hash_success(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello\n", encoding="utf-8")
    read = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    result = await dispatch(session, "guardian_edit_file", {"path": str(target), "old_str": "hello", "new_str": "hi", "expected_file_hash": read["file_hash"]}, store)

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "hi\n"
