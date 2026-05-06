import pytest

from guardian.circuit import CircuitState, check_and_maybe_auto_unlock, force_half_open, record_result
from guardian.state import SessionState


@pytest.mark.asyncio
async def test_hard_trip_and_signature_unlock():
    session = SessionState("circuit")
    for _ in range(4):
        await record_result(session, "guardian_edit_file", False, "sig-a", "old_string_not_found")
    assert await check_and_maybe_auto_unlock(session, "guardian_edit_file", "sig-a") == CircuitState.TRIPPED
    assert await check_and_maybe_auto_unlock(session, "guardian_edit_file", "sig-b") == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_success_closes_and_failure_trips():
    session = SessionState("circuit")
    await force_half_open(session, "guardian_edit_file")
    await record_result(session, "guardian_edit_file", True, "sig-a")
    assert session.get_state("guardian_edit_file").circuit_state == CircuitState.CLOSED.value
    await force_half_open(session, "guardian_edit_file")
    await record_result(session, "guardian_edit_file", False, "sig-b", "x")
    assert session.get_state("guardian_edit_file").circuit_state == CircuitState.TRIPPED.value


@pytest.mark.asyncio
async def test_failure_signatures_limited():
    session = SessionState("circuit")
    for i in range(20):
        await record_result(session, "guardian_edit_file", False, f"sig-{i}", "x")
    assert len(session.get_state("guardian_edit_file").failure_signatures) <= 10
