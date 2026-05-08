from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from .state import SessionState


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def snapshot_file(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    data = resolved.read_bytes()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "file_hash": hash_bytes(data),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def remember_read(session: SessionState, path: str | Path, file_hash: str, size: int, mtime_ns: int) -> str:
    resolved = str(Path(path).expanduser().resolve())
    seed = f"{session.session_id}\0{resolved}\0{file_hash}\0{size}\0{mtime_ns}\0{time.time_ns()}"
    read_id = "read_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    session.read_versions[read_id] = {
        "path": resolved,
        "file_hash": file_hash,
        "size": size,
        "mtime_ns": mtime_ns,
    }
    return read_id


def validate_edit_precondition(
    session: SessionState | None,
    path: str | Path,
    expected_read_id: str | None = None,
    expected_file_hash: str | None = None,
) -> dict | None:
    require_read = os.environ.get("GUARDIAN_REQUIRE_READ_FOR_EDIT", "1") != "0"
    if require_read and not expected_read_id and not expected_file_hash:
        return {
            "success": False,
            "error": "edit_file 默认要求 expected_read_id 或 expected_file_hash",
            "error_class": "MODEL_ERROR",
            "error_type": "expected_file_version_required",
            "hint": "先调用 guardian_read_file，使用返回的 read_id 或 file_hash 重试。",
        }

    if not expected_read_id and not expected_file_hash:
        return None

    try:
        current = snapshot_file(path)
    except FileNotFoundError:
        return {"success": False, "error": f"文件不存在:{path}", "error_class": "ENV_ERROR", "error_type": "FileNotFoundError", "hint": "先用 guardian_glob 确认路径"}
    except PermissionError:
        return {"success": False, "error": f"无读取权限:{path}", "error_class": "ENV_ERROR", "error_type": "PermissionError"}
    except OSError as e:
        return {"success": False, "error": f"读取文件版本失败:{e}", "error_class": "ENV_ERROR", "error_type": type(e).__name__}

    if expected_file_hash and current["file_hash"] != expected_file_hash:
        return {
            "success": False,
            "error": "文件 hash 与 expected_file_hash 不一致",
            "error_class": "MODEL_ERROR",
            "error_type": "file_hash_mismatch",
            "current_file_hash": current["file_hash"],
            "expected_file_hash": expected_file_hash,
        }

    if expected_read_id:
        if session is None:
            return {"success": False, "error": "expected_read_id 需要 session 状态", "error_class": "MODEL_ERROR", "error_type": "read_id_session_required"}
        previous = session.read_versions.get(expected_read_id)
        if previous is None:
            return {
                "success": False,
                "error": "expected_read_id 不存在或已失效",
                "error_class": "MODEL_ERROR",
                "error_type": "unknown_read_id",
                "hint": "重新调用 guardian_read_file 获取新的 read_id。",
            }
        if previous["path"] != current["path"]:
            return {"success": False, "error": "expected_read_id 对应的不是当前文件", "error_class": "MODEL_ERROR", "error_type": "read_id_path_mismatch"}
        if previous["file_hash"] != current["file_hash"] or previous["size"] != current["size"] or previous["mtime_ns"] != current["mtime_ns"]:
            return {
                "success": False,
                "error": "文件在 read 后已变化",
                "error_class": "MODEL_ERROR",
                "error_type": "file_changed_since_read",
                "current_file_hash": current["file_hash"],
                "read_file_hash": previous["file_hash"],
                "hint": "重新读取文件后再编辑。",
            }

    return None


def invalidate_path_reads(session: SessionState | None, path: str | Path) -> None:
    if session is None:
        return
    resolved = str(Path(path).expanduser().resolve())
    for read_id, snapshot in list(session.read_versions.items()):
        if snapshot.get("path") == resolved:
            session.read_versions.pop(read_id, None)
