from __future__ import annotations

import json
import re
import time
from typing import Any

APPROVAL_TTL_SECONDS = 900
_SECRET_KEY_PARTS = ("api_key", "apikey", "token", "secret", "password", "credential", "authorization")
_LARGE_TEXT_KEYS = {"content", "old_str", "new_str"}
_SECRET_ASSIGNMENT_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[^\s,'\"]+")


def requires_approval(result: dict | None) -> bool:
    return bool(result and result.get("status") == "APPROVAL_REQUIRED")


async def attach_pending_approval(store, session, tool_name: str, params: dict, result: dict) -> dict:
    if result.get("approval_id"):
        return result
    approval = await store.create_approval(
        session_id=session.session_id,
        tool_name=tool_name,
        params_json=json.dumps(sanitize_params(params), ensure_ascii=False, sort_keys=True),
        risk=float(result.get("risk", 0.9)),
        reasons_json=json.dumps(result.get("reasons") or [result.get("error", "需要人工审批")], ensure_ascii=False),
        ttl_seconds=APPROVAL_TTL_SECONDS,
    )
    enriched = dict(result)
    enriched["approval_id"] = approval["approval_id"]
    enriched["expires_at"] = approval["expires_at"]
    enriched.pop("ack_token", None)
    enriched["hint"] = "该操作需要外部人工审批；模型不能通过 _ack 自批准。"
    return enriched


def sanitize_params(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize_value(str(k), v) for k, v in value.items() if k != "_ack"}
    if isinstance(value, list):
        return [sanitize_params(item) for item in value]
    return value


def _sanitize_value(key: str, value: Any) -> Any:
    lower_key = key.lower()
    if any(part in lower_key for part in _SECRET_KEY_PARTS):
        return "[REDACTED]"
    if lower_key in _LARGE_TEXT_KEYS and isinstance(value, str):
        return f"[REDACTED_TEXT length={len(value)}]"
    if isinstance(value, str):
        redacted = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
        if len(redacted) > 1000:
            return redacted[:1000] + f"... [truncated {len(redacted) - 1000} chars]"
        return redacted
    return sanitize_params(value)
