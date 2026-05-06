from __future__ import annotations

import secrets
from enum import Enum

from .risk import compute_risk
from .state import SessionState


class InterceptionMode(str, Enum):
    STRICT = "STRICT"
    ADAPTIVE = "ADAPTIVE"
    PASSIVE = "PASSIVE"


def detect_mode(session: SessionState) -> InterceptionMode:
    if session.total_prechecks == 0:
        return InterceptionMode.ADAPTIVE
    rate = session.ack_successes / session.total_prechecks
    if rate > 0.8:
        return InterceptionMode.STRICT
    if rate > 0.3:
        return InterceptionMode.ADAPTIVE
    return InterceptionMode.PASSIVE


def precheck_call(session: SessionState, tool_name: str, params: dict) -> dict | None:
    risk = compute_risk(tool_name, params)
    mode = detect_mode(session)
    ack = params.get("_ack")
    if ack and ack in session.pending_fallbacks:
        session.ack_successes += 1
        session.pending_fallbacks.pop(ack, None)
        return None
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
    return {"success": False, "error": "PRE_CHECK_REQUIRED", "error_class": "pre_fail", "error_type": "PRE_CHECK_REQUIRED", "ack_token": token, "risk": risk, "mode": mode.value, "hint": "确认风险后以 _ack 传回 ack_token 重试。"}
