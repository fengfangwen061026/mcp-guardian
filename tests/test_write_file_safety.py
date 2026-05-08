import pytest

from guardian.dispatch import dispatch
from guardian.persist import OffsetStore
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="write_safety_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_create_only_new_file_success(session, store, tmp_path):
    target = tmp_path / "new.txt"

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "hello"}, store)

    assert result["success"] is True
    assert result["mode"] == "create_only"
    assert target.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_create_only_existing_file_fails(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "new"}, store)

    assert result["success"] is False
    assert result["error_type"] == "file_exists"
    assert target.read_text(encoding="utf-8") == "old"


@pytest.mark.asyncio
async def test_overwrite_requires_hash(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "new", "mode": "overwrite"}, store)

    assert result["success"] is False
    assert result["error_type"] == "expected_file_hash_required"


@pytest.mark.asyncio
async def test_overwrite_hash_mismatch_fails(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "new", "mode": "overwrite", "expected_file_hash": "sha256:nope"}, store)

    assert result["success"] is False
    assert result["error_type"] == "file_hash_mismatch"


@pytest.mark.asyncio
async def test_overwrite_dry_run_returns_diff_without_writing(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    read = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "new\n", "mode": "overwrite", "expected_file_hash": read["file_hash"], "dry_run": True}, store)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert "-old" in result["diff"]
    assert "+new" in result["diff"]
    assert target.read_text(encoding="utf-8") == "old\n"


@pytest.mark.asyncio
async def test_overwrite_creates_backup(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    read = await dispatch(session, "guardian_read_file", {"path": str(target)}, store)

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "new", "mode": "overwrite", "expected_file_hash": read["file_hash"]}, store)

    assert result["success"] is True
    assert "backup_path" in result
    assert target.read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_append_requires_hash_for_existing_file(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")

    result = await dispatch(session, "guardian_write_file", {"path": str(target), "content": "new", "mode": "append"}, store)

    assert result["success"] is False
    assert result["error_type"] == "expected_file_hash_required"
