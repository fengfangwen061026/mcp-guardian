from __future__ import annotations

import secrets
import time
from enum import Enum

from . import risk as risk_module
from .signature import extract_signature
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
        token_data = session.ack_tokens.get(ack)
        if token_data is None:
            session.pending_fallbacks.pop(ack, None)
            return {"success": False, "error": "ack_token 已过期或无效", "error_class": "pre_fail", "error_type": "invalid_ack"}
        expected_tool, expected_sig, expires_at = token_data
        current_sig = extract_signature(tool_name, params)
        if expires_at < now:
            session.ack_tokens.pop(ack, None)
            session.pending_fallbacks.pop(ack, None)
            return {"success": False, "error": "ack_token 已过期或无效", "error_class": "pre_fail", "error_type": "invalid_ack"}
        if expected_tool != tool_name or expected_sig != current_sig:
            return {"success": False, "error": "ack_token 与当前工具或参数不匹配", "error_class": "pre_fail", "error_type": "ack_scope_mismatch"}
        session.ack_successes += 1
        session.ack_tokens.pop(ack, None)
        session.pending_fallbacks.pop(ack, None)
        return None
    risk = risk_module.compute_risk(tool_name, params)
    mode = detect_mode(session)
    if risk > 0.85:
        return _approval_response(tool_name, risk, mode)
    if mode == InterceptionMode.PASSIVE:
        return None
    if mode == InterceptionMode.STRICT and risk > 0.6:
        return _ack_response(session, tool_name, params, risk, mode)
    if mode == InterceptionMode.ADAPTIVE and risk > 0.6:
        params["_guardian_note"] = "Guardian allowed this medium-risk call in ADAPTIVE mode."
    return None


def _approval_response(tool_name: str, risk: float, mode: InterceptionMode) -> dict:
    return {"success": False, "status": "APPROVAL_REQUIRED", "error": "APPROVAL_REQUIRED", "error_class": "SECURITY", "error_type": "APPROVAL_REQUIRED", "risk": risk, "mode": mode.value, "reasons": [f"{tool_name} 风险分数超过人工审批阈值"]}


def _ack_response(session: SessionState, tool_name: str, params: dict, risk: float, mode: InterceptionMode) -> dict:
    session.total_prechecks += 1
    token = secrets.token_urlsafe(12)
    params_sig = extract_signature(tool_name, {k: v for k, v in params.items() if k != "_ack"})
    session.pending_fallbacks[token] = {"tool_name": tool_name, "risk": risk, "params_sig": params_sig}
    session.ack_tokens[token] = (tool_name, params_sig, time.time() + 300)
    return {"success": False, "status": "MODEL_ACK_REQUIRED", "error": "MODEL_ACK_REQUIRED", "error_class": "pre_fail", "error_type": "MODEL_ACK_REQUIRED", "ack_token": token, "risk": risk, "mode": mode.value, "hint": "确认中风险后以 _ack 传回 ack_token 重试。"}


async def execute_with_fallback(session: SessionState, tool_name: str, params: dict, db=None) -> dict:
    from .dispatch import dispatch

    return await dispatch(session, tool_name, params)


async def intercept(session: SessionState, tool_name: str, params: dict, db=None) -> dict:
    params = dict(params or {})
    precheck = precheck_call(session, tool_name, params)
    if precheck:
        return precheck
    return await execute_with_fallback(session, tool_name, params, db)
