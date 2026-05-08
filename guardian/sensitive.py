from __future__ import annotations

from pathlib import Path

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


def _is_git_config(path: Path) -> bool:
    return path.name == "config" and any(part == ".git" for part in path.parts)
