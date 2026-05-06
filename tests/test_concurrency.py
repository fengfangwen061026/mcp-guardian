import asyncio

import pytest

from guardian.circuit import record_result
from guardian.state import SessionState


@pytest.mark.asyncio
async def test_record_result_concurrent_counting():
    session = SessionState("concurrency")
    await asyncio.gather(*[record_result(session, "guardian_edit_file", True, f"s{i}") for i in range(100)])
    state = session.get_state("guardian_edit_file")
    assert state.total_calls == 100
    assert state.total_successes == 100


@pytest.mark.asyncio
async def test_mixed_concurrent_results_counting():
    session = SessionState("concurrency")
    calls = [record_result(session, "guardian_run_bash", False, f"f{i}", "x") for i in range(5)]
    calls += [record_result(session, "guardian_run_bash", True, f"s{i}") for i in range(5)]
    await asyncio.gather(*calls)
    state = session.get_state("guardian_run_bash")
    assert state.total_calls == 10
    assert state.total_successes == 5
