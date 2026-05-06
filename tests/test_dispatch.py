import pytest

from guardian.dispatch import dispatch
from guardian.persist import OffsetStore
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="dispatch_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(session, store):
    result = await dispatch(session, "guardian_nope", {}, store)
    assert result["success"] is False
    assert result["error_type"] == "unknown_tool"


@pytest.mark.asyncio
async def test_dispatch_status(session, store):
    result = await dispatch(session, "guardian_status", {}, store)
    assert result["success"] is True
    assert result["session_id"] == "dispatch_test"
