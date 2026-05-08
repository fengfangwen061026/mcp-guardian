from __future__ import annotations

import json

BUDGET: dict[tuple, int] = {
    ("guardian_read_file", True): 2000,
    ("guardian_run_bash", True): 700,
    ("guardian_edit_file", True): 80,
    ("guardian_write_file", True): 400,
    ("guardian_glob", True): 500,
    ("guardian_grep", True): 600,
    ("guardian_get_spec", True): 800,
    ("guardian_status", True): 300,
    ("_any", "pre_fail"): 400,
    ("_any", "MODEL_ERROR"): 300,
    ("_any", "ENV_ERROR"): 150,
    ("_any", "SECURITY"): 80,
    ("_any", "TRANSIENT"): 120,
    ("_any", "hard_blocked"): 300,
}

CORE_FIELDS = {"success", "error", "error_class", "error_type", "hint", "exit_code", "path", "note", "circuit_breaker", "warning", "total_lines", "truncated", "shown_lines", "bytes_written", "count", "ack_token", "risk", "mode", "session_id", "execution_mode", "allowed_roots", "read_id", "file_hash", "size", "mtime_ns", "current_file_hash", "expected_file_hash", "dry_run", "backup_path", "status", "decision", "category", "safer_alternative"}
SUCCESS_FIELDS: dict[str, list[str]] = {
    "guardian_read_file": ["content"],
    "guardian_run_bash": ["stdout", "stderr"],
    "guardian_edit_file": [],
    "guardian_write_file": ["diff"],
    "guardian_glob": ["matches", "truncated_results"],
    "guardian_grep": ["matches", "truncated_results"],
    "guardian_get_spec": ["spec"],
    "guardian_status": ["tools", "roots"],
}
ERROR_FIELDS = ["guidance", "file_content", "stderr", "unlock_hint", "top_error", "targeted_advice", "inline_spec"]


def _estimate_tokens(obj) -> int:
    try:
        s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
        return max(1, len(s) // 4)
    except Exception:
        return 50


def _truncate_to_tokens(obj, max_tokens: int):
    max_chars = max_tokens * 4
    if isinstance(obj, str):
        if len(obj) <= max_chars:
            return obj
        return obj[: max_chars - 20] + "\n... [truncated]"
    if isinstance(obj, list):
        out = []
        marker = "... [truncated]"
        for item in obj:
            candidate = out + [item]
            if len(json.dumps(candidate, ensure_ascii=False)) > max_chars:
                if len(json.dumps(out + [marker], ensure_ascii=False)) <= max_chars:
                    out.append(marker)
                break
            out.append(item)
        return out
    return obj


_truncate = _truncate_to_tokens


def _get_budget(tool_name: str, success: bool, error_class: str = "") -> int:
    if success:
        return BUDGET.get((tool_name, True), 200)
    return BUDGET.get(("_any", error_class), BUDGET[("_any", "MODEL_ERROR")])


def enforce_budget(response: dict, tool_name: str) -> dict:
    success = response.get("success", False)
    error_class = response.get("error_class", "MODEL_ERROR")
    if not success and "file_content" in response:
        error_class = "pre_fail"
    budget = _get_budget(tool_name, success, error_class)
    result = {k: v for k, v in response.items() if k in CORE_FIELDS}
    used = _estimate_tokens(result)
    ext_fields = SUCCESS_FIELDS.get(tool_name, []) if success else ERROR_FIELDS
    for field in ext_fields:
        if field not in response:
            continue
        val = response[field]
        tokens = _estimate_tokens(val)
        remaining = budget - used
        if remaining < 20:
            break
        if tokens <= remaining:
            result[field] = val
            used += tokens
        else:
            result[field] = _truncate_to_tokens(val, remaining)
            break
    return result
