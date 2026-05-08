from __future__ import annotations

import fnmatch
from pathlib import Path

from .policy_loader import PolicyConfigError, load_policy, policy_error

_DENY_SUFFIXES = (".pem", ".key")
_DENY_NAMES = {"id_rsa", "id_ed25519", "config"}
_ASK_NAMES = {".env", ".npmrc", ".pypirc", "credentials.json"}


def check_sensitive_path(path: str | Path, operation: str) -> dict | None:
    resolved = Path(path).expanduser()
    parts = set(resolved.parts)
    name = resolved.name
    suffix = resolved.suffix

    if ".ssh" in parts or suffix in _DENY_SUFFIXES or name in {"id_rsa", "id_ed25519"} or _is_git_config(resolved):
        return {
            "success": False,
            "error_class": "SECURITY",
            "error_type": "SensitivePathBlocked",
            "error": f"{operation} 命中高敏感路径策略:{path}",
            "hint": "不要让模型读取或修改私钥、证书或 Git 凭据配置。",
        }

    if policy_decision := _policy_decision(resolved, operation, path):
        return policy_decision

    if name in _ASK_NAMES or name.startswith(".env."):
        return {
            "success": False,
            "status": "APPROVAL_REQUIRED",
            "error_class": "SECURITY",
            "error_type": "SensitivePathApprovalRequired",
            "error": f"{operation} 需要审批:{path}",
            "risk": 0.86,
            "reasons": ["目标文件疑似环境变量或凭据配置"],
        }

    return None


def _policy_decision(resolved: Path, operation: str, original_path: str | Path) -> dict | None:
    try:
        policy = load_policy(resolved)
    except PolicyConfigError as exc:
        return policy_error(exc)
    normalized = str(resolved)
    matched = [rule for rule in policy.sensitive_rules if any(fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(resolved.name, pattern) for pattern in rule.patterns)]
    for action in ("deny", "ask", "allow"):
        for rule in matched:
            if rule.action != action:
                continue
            if action == "deny":
                return {"success": False, "error_class": "SECURITY", "error_type": "SensitivePathBlocked", "error": f"{operation} 命中项目敏感路径 deny 策略:{original_path}", "reasons": list(rule.reasons) or ["项目 policy deny"]}
            if action == "ask":
                return {"success": False, "status": "APPROVAL_REQUIRED", "error_class": "SECURITY", "error_type": "SensitivePathApprovalRequired", "error": f"{operation} 需要审批:{original_path}", "risk": rule.risk, "reasons": list(rule.reasons) or ["项目 policy ask"]}
            return None
    return None


def _is_git_config(path: Path) -> bool:
    return path.name == "config" and any(part == ".git" for part in path.parts)
