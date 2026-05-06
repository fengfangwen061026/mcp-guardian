from __future__ import annotations

from enum import Enum

from .state import SessionState, ToolState


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    WARNING = "WARNING"
    HALF_OPEN = "HALF_OPEN"
    TRIPPED = "TRIPPED"


CIRCUIT_CONFIG = {
    "guardian_edit_file": {"soft_trip": 2, "hard_trip": 4},
    "guardian_run_bash": {"soft_trip": 2, "hard_trip": 4},
    "_default": {"soft_trip": 3, "hard_trip": 5},
}


async def record_result(
    session: SessionState,
    tool_name: str,
    success: bool,
    params_sig: str,
    error_type: str = "",
) -> None:
    async with session.get_lock(tool_name):
        state = session.get_state(tool_name)
        state.total_calls += 1
        state.last_signature = params_sig
        previous_state = CircuitState(state.circuit_state)
        if success:
            state.consecutive_failures = 0
            state.failure_signatures.clear()
            state.total_successes += 1
            state.circuit_state = CircuitState.CLOSED.value
            return

        state.consecutive_failures += 1
        state.failure_signatures.append(params_sig)
        state.failure_signatures = state.failure_signatures[-10:]
        if error_type:
            state.error_type_counts[error_type] += 1
            session.knowledge_hits[f"{tool_name}:{error_type}"] += 1

        cfg = CIRCUIT_CONFIG.get(tool_name, CIRCUIT_CONFIG["_default"])
        if previous_state == CircuitState.HALF_OPEN:
            state.circuit_state = CircuitState.TRIPPED.value
        elif state.consecutive_failures >= cfg["hard_trip"]:
            state.circuit_state = CircuitState.TRIPPED.value
        elif state.consecutive_failures >= cfg["soft_trip"]:
            state.circuit_state = CircuitState.WARNING.value
        else:
            state.circuit_state = CircuitState.CLOSED.value


async def check_and_maybe_auto_unlock(session: SessionState, tool_name: str, params_sig: str) -> CircuitState:
    async with session.get_lock(tool_name):
        state = session.get_state(tool_name)
        current = CircuitState(state.circuit_state)
        if current == CircuitState.TRIPPED:
            if params_sig not in state.failure_signatures:
                state.circuit_state = CircuitState.HALF_OPEN.value
                return CircuitState.HALF_OPEN
            return CircuitState.TRIPPED
        return current


async def check_circuit(session: SessionState, tool_name: str, params_sig: str) -> str:
    state = await check_and_maybe_auto_unlock(session, tool_name, params_sig)
    if state == CircuitState.TRIPPED:
        return "hard"
    if state == CircuitState.WARNING:
        return "soft"
    return "open"


async def force_half_open(session: SessionState, tool_name: str) -> None:
    async with session.get_lock(tool_name):
        state = session.get_state(tool_name)
        state.circuit_state = CircuitState.HALF_OPEN.value
        state.consecutive_failures = 0
