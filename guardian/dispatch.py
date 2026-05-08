from __future__ import annotations

import inspect

from .approvals import attach_pending_approval, requires_approval
from .budget import enforce_budget
from .circuit import CircuitState, check_and_maybe_auto_unlock, force_half_open, record_result
from .handlers.edit_file import handle_edit_file
from .handlers.glob_grep import execute_glob, execute_grep
from .handlers.read_file import execute_read_file
from .handlers.run_bash import execute_run_argv, execute_run_bash, get_adjusted_timeout, pre_validate_argv, pre_validate_bash
from .file_version import remember_read
from .handlers.write_file import execute_write_file
from .intercept import detect_mode, precheck_call
from .knowledge import KNOWLEDGE_BY_ERROR, KNOWLEDGE_BY_TOOL, get_static_guidance, select_guidance
from .persist import OffsetStore
from .roots import check_path_allowed, roots_status
from .signature import extract_signature
from .state import SessionState


TOOL_NAMES = {
    "guardian_read_file",
    "guardian_write_file",
    "guardian_edit_file",
    "guardian_run_bash",
    "guardian_glob",
    "guardian_grep",
    "guardian_get_spec",
    "guardian_pending_approvals",
    "guardian_status",
}


def _make_offset_lookup(store: OffsetStore):
    def lookup(entry_id: str) -> float:
        try:
            value = store.get_offset(entry_id)
            if inspect.isawaitable(value):
                value.close()
                return 0.0
            return float(value)
        except Exception:
            return 0.0
    return lookup


def _get_static_guidance(tool_name: str, error_type: str, store: OffsetStore, max_tokens: int = 150) -> list[dict]:
    return select_guidance(tool_name, error_type, offset_lookup=_make_offset_lookup(store), max_tokens=max_tokens)


async def dispatch(session: SessionState, tool_name: str, params: dict, store: OffsetStore | None = None) -> dict:
    store = store or OffsetStore()
    params = dict(params or {})
    params_sig = extract_signature(tool_name, params)

    if tool_name not in TOOL_NAMES:
        return {"success": False, "error": f"未知工具:{tool_name}", "error_class": "MODEL_ERROR", "error_type": "unknown_tool"}

    if tool_name == "guardian_get_spec":
        return enforce_budget(await handle_get_spec(session, params.get("tool_name", ""), store), "guardian_get_spec")
    if tool_name == "guardian_pending_approvals":
        return enforce_budget(await handle_pending_approvals(session, store), "guardian_pending_approvals")
    if tool_name == "guardian_status":
        return enforce_budget(await handle_status(session), "guardian_status")

    result: dict
    if tool_name == "guardian_run_bash":
        fail = _pre_validate_run_bash(params)
        if fail:
            if requires_approval(fail):
                fail = await attach_pending_approval(store, session, tool_name, params, fail)
            await _record(session, store, tool_name, False, params_sig, fail)
            return enforce_budget(fail, tool_name)

    intercept = precheck_call(session, tool_name, params) if tool_name in {"guardian_edit_file", "guardian_write_file"} else None
    if intercept:
        if requires_approval(intercept):
            intercept = await attach_pending_approval(store, session, tool_name, params, intercept)
        await _record(session, store, tool_name, False, params_sig, intercept)
        return enforce_budget(intercept, tool_name)

    if tool_name in {"guardian_edit_file", "guardian_run_bash"}:
        circuit = await check_and_maybe_auto_unlock(session, tool_name, params_sig)
        if circuit == CircuitState.TRIPPED:
            resp = await _build_hard_blocked(session, tool_name, store)
            await _record(session, store, tool_name, False, params_sig, resp)
            return enforce_budget(resp, tool_name)
    else:
        circuit = CircuitState.CLOSED

    if tool_name == "guardian_edit_file":
        result = await handle_edit_file(session, params.get("path", ""), params.get("old_str", ""), params.get("new_str", ""), params.get("expected_read_id"), params.get("expected_file_hash"))
    elif tool_name == "guardian_run_bash":
        result = await _execute_run_bash(params)
    elif tool_name == "guardian_read_file":
        result = await execute_read_file(params.get("path", ""), params.get("start_line"), params.get("end_line"))
        if result.get("success"):
            result["read_id"] = remember_read(session, params.get("path", ""), result["file_hash"], result["size"], result["mtime_ns"])
    elif tool_name == "guardian_write_file":
        result = await execute_write_file(params.get("path", ""), params.get("content", ""), params.get("mode", "create_only"), params.get("expected_file_hash"), bool(params.get("dry_run", False)), bool(params.get("backup", True)))
    elif tool_name == "guardian_glob":
        result = await execute_glob(params.get("pattern", ""), params.get("path"))
    else:
        result = await execute_grep(params.get("pattern", ""), params.get("path"), params.get("include"))

    if requires_approval(result):
        result = await attach_pending_approval(store, session, tool_name, params, result)

    success = result.get("success", False)
    if tool_name in {"guardian_edit_file", "guardian_run_bash"}:
        await record_result(session, tool_name, success, params_sig, "" if success else result.get("error_type", ""))
        if not success and circuit == CircuitState.WARNING:
            state = session.get_state(tool_name)
            result["warning"] = f"该工具已连续失败 {state.consecutive_failures} 次,必须调整参数后再试"

    await _record(session, store, tool_name, success, params_sig, result)
    await _adjust_guidance(store, tool_name, result)
    if not success:
        error_type = result.get("error_type", "")
        mode = detect_mode(session)
        if result.get("error_class") in {"MODEL_ERROR", "TRANSIENT", "ENV_ERROR"}:
            result["guidance"] = _get_static_guidance(tool_name, error_type, store, max_tokens=150 if mode.value != "PASSIVE" else 220)
    return enforce_budget(result, tool_name)


def _pre_validate_run_bash(params: dict) -> dict | None:
    has_command = "command" in params and params.get("command") is not None
    has_argv = "argv" in params and params.get("argv") is not None
    if has_command and has_argv:
        return {"success": False, "error": "command 和 argv 只能二选一", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    if params.get("cwd"):
        if violation := check_path_allowed(params["cwd"], "cwd"):
            return violation
    policy_path = params.get("cwd")
    if has_argv:
        argv = params.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            return {"success": False, "error": "argv 必须是字符串数组", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
        return pre_validate_argv(argv, params.get("description"), policy_path)
    return pre_validate_bash(params.get("command", ""), params.get("timeout", 30_000), params.get("description"), policy_path)


async def _execute_run_bash(params: dict) -> dict:
    timeout = params.get("timeout", 30_000)
    if "argv" in params and params.get("argv") is not None:
        return await execute_run_argv(params["argv"], params.get("cwd"), timeout)
    command = params["command"]
    adjusted_timeout = get_adjusted_timeout(command, timeout)
    return await execute_run_bash(command, params.get("cwd"), adjusted_timeout)


async def _record(session: SessionState, store: OffsetStore, tool_name: str, success: bool, params_sig: str, result: dict) -> None:
    await store.record_event(session.session_id, tool_name, success, params_sig, result)


async def _adjust_guidance(store: OffsetStore, tool_name: str, result: dict) -> None:
    if result.get("success"):
        await store.adjust_on_success([e.id for e in KNOWLEDGE_BY_TOOL.get(tool_name, [])])
        return
    error_type = result.get("error_type", "")
    related_ids = [e.id for e in KNOWLEDGE_BY_ERROR.get((tool_name, error_type), [])]
    if related_ids:
        await store.adjust_on_error(related_ids)


async def _build_hard_blocked(session: SessionState, tool_name: str, store: OffsetStore) -> dict:
    state = session.get_state(tool_name)
    top_error = max(state.error_type_counts, key=state.error_type_counts.get) if state.error_type_counts else ""
    inline_spec = _get_static_guidance(tool_name, top_error, store, max_tokens=220)
    return {
        "success": False,
        "circuit_breaker": "HARD_BLOCKED",
        "error_class": "hard_blocked",
        "error_type": "HARD_BLOCKED",
        "error": f"{tool_name} 连续失败 {state.consecutive_failures} 次,且参数模式重复",
        "top_error": top_error,
        "guidance": inline_spec,
        "inline_spec": inline_spec,
        "unlock_hint": "修改参数签名后会自动 HALF_OPEN；也可调用 guardian_get_spec(tool_name) 主动解锁。",
    }


async def handle_get_spec(session: SessionState, tool_name: str, store: OffsetStore) -> dict:
    if tool_name not in KNOWLEDGE_BY_TOOL:
        return {"success": False, "error": f"未知工具:{tool_name}", "error_class": "MODEL_ERROR", "error_type": "unknown_tool"}
    spec = select_guidance(tool_name, error_type=None, offset_lookup=_make_offset_lookup(store), max_tokens=600, max_entries=5)
    await force_half_open(session, tool_name)
    return {"success": True, "tool_name": tool_name, "spec": spec, "note": "调用 get_spec 后熔断器已切换为 HALF_OPEN,允许重新尝试。"}


async def handle_pending_approvals(session: SessionState, store: OffsetStore) -> dict:
    approvals = await store.list_pending_approvals(session.session_id)
    summaries = [
        {
            "approval_id": item["approval_id"],
            "session_id": item["session_id"],
            "tool_name": item["tool_name"],
            "risk": item["risk"],
            "reasons": item["reasons"],
            "status": item["status"],
            "created_at": item["created_at"],
            "expires_at": item["expires_at"],
        }
        for item in approvals
    ]
    return {"success": True, "session_id": session.session_id, "approvals": summaries, "count": len(summaries)}


async def handle_status(session: SessionState) -> dict:
    tools = {}
    for tool_name, state in session._tools.items():
        tools[tool_name] = {
            "circuit_state": state.circuit_state,
            "total_calls": state.total_calls,
            "total_successes": state.total_successes,
            "consecutive_failures": state.consecutive_failures,
            "failure_signatures": len(state.failure_signatures),
        }
    return {"success": True, "session_id": session.session_id, "mode": detect_mode(session).value, "tools": tools, "roots": roots_status()}
