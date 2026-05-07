from __future__ import annotations

import secrets
import time
from enum import Enum

from . import risk as risk_module
from .state import SessionState


class InterceptionMode(str, Enum):
    STRICT = "STRICT"
    ADAPTIVE = "ADAPTIVE"
    PASSIVE = "PASSIVE"


def detect_mode(session: SessionState) -> InterceptionMode:
    explicit = getattr(session, "_mode", None)
    if explicit in {"STRICT", "ADAPTIVE", "PASSIVE"}:
        return InterceptionMode(explicit)
    if session.total_prechecks == 0:
        return InterceptionMode.ADAPTIVE
    rate = session.ack_successes / session.total_prechecks
    if rate > 0.8:
        return InterceptionMode.STRICT
    if rate > 0.3:
        return InterceptionMode.ADAPTIVE
    return InterceptionMode.PASSIVE


def precheck_call(session: SessionState, tool_name: str, params: dict) -> dict | None:
    now = time.time()
    ack = params.get("_ack")
    if ack:
        if ack in session.pending_fallbacks:
            session.ack_successes += 1
            session.pending_fallbacks.pop(ack, None)
            return None
        token_data = session.ack_tokens.get(ack)
        if token_data is not None:
            expires_at = token_data[2] if len(token_data) > 2 else 0
            if expires_at < now:
                session.ack_tokens.pop(ack, None)
                return {"success": False, "error": "ack_token 已过期或无效", "error_class": "pre_fail", "error_type": "invalid_ack"}
            session.ack_successes += 1
            session.ack_tokens.pop(ack, None)
            return None
        return {"success": False, "error": "ack_token 已过期或无效", "error_class": "pre_fail", "error_type": "invalid_ack"}
    risk = risk_module.compute_risk(tool_name, params)
    mode = detect_mode(session)
    if mode == InterceptionMode.PASSIVE:
        return None
    if mode == InterceptionMode.STRICT and risk > 0.6:
        return _ack_response(session, tool_name, risk, mode)
    if mode == InterceptionMode.ADAPTIVE and risk > 0.85:
        return _ack_response(session, tool_name, risk, mode)
    if mode == InterceptionMode.ADAPTIVE and risk > 0.6:
        params["_guardian_note"] = "Guardian allowed this medium-risk call in ADAPTIVE mode."
    return None


def _ack_response(session: SessionState, tool_name: str, risk: float, mode: InterceptionMode) -> dict:
    session.total_prechecks += 1
    token = secrets.token_urlsafe(12)
    session.pending_fallbacks[token] = {"tool_name": tool_name, "risk": risk}
    session.ack_tokens[token] = (tool_name, {}, time.time() + 300)
    return {"success": False, "status": "PRE_CHECK_REQUIRED", "error": "PRE_CHECK_REQUIRED", "error_class": "pre_fail", "error_type": "PRE_CHECK_REQUIRED", "ack_token": token, "risk": risk, "mode": mode.value, "hint": "确认风险后以 _ack 传回 ack_token 重试。"}


async def execute_with_fallback(session: SessionState, tool_name: str, params: dict, db=None) -> dict:
    from .dispatch import dispatch

    return await dispatch(session, tool_name, params)


async def intercept(session: SessionState, tool_name: str, params: dict, db=None) -> dict:
    params = dict(params or {})
    precheck = precheck_call(session, tool_name, params)
    if precheck:
        return precheck
    return await execute_with_fallback(session, tool_name, params, db)
