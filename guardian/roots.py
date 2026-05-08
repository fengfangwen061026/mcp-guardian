from __future__ import annotations

import os
from pathlib import Path


def configured_roots() -> list[Path]:
    raw = os.environ.get("GUARDIAN_ROOTS") or os.environ.get("GUARDIAN_ROOT", "")
    roots = []
    for item in raw.split(os.pathsep):
        if item.strip():
            roots.append(Path(item).expanduser().resolve())
    return roots


def roots_status() -> dict:
    roots = configured_roots()
    return {"enabled": bool(roots), "allowed_roots": [str(root) for root in roots]}


def check_path_allowed(path: str | Path, label: str = "path") -> dict | None:
    roots = configured_roots()
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
