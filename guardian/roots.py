from __future__ import annotations

from pathlib import Path

from .policy_loader import PolicyConfigError, load_policy, policy_error


def configured_roots(start_path: str | Path | None = None) -> list[Path]:
    return list(load_policy(start_path).roots)


def roots_status() -> dict:
    try:
        roots = configured_roots()
    except PolicyConfigError as exc:
        return {"enabled": False, "allowed_roots": [], "policy_error": str(exc)}
    return {"enabled": bool(roots), "allowed_roots": [str(root) for root in roots]}


def check_path_allowed(path: str | Path, label: str = "path") -> dict | None:
    try:
        roots = configured_roots(path)
    except PolicyConfigError as exc:
        return policy_error(exc)
    if not roots:
        return None
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError as e:
        return {"success": False, "error": f"路径解析失败:{path}: {e}", "error_class": "ENV_ERROR", "error_type": type(e).__name__}
    if any(_is_relative_to(resolved, root) for root in roots):
        return None
    return {
        "success": False,
        "error": f"{label} 超出 GUARDIAN_ROOTS 允许范围:{resolved}",
        "error_class": "SECURITY",
        "error_type": "PathOutsideRoot",
        "allowed_roots": [str(root) for root in roots],
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
