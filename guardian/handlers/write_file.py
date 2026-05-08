from __future__ import annotations

from pathlib import Path

from ..backups import create_backup
from ..diffing import unified_diff
from ..exec_io import write_atomic
from ..file_version import hash_text, snapshot_file
from ..roots import check_path_allowed
from ..sensitive import check_sensitive_path

_VALID_MODES = {"create_only", "overwrite", "append"}


async def execute_write_file(
    path: str,
    content: str,
    mode: str = "create_only",
    expected_file_hash: str | None = None,
    dry_run: bool = False,
    backup: bool = True,
) -> dict:
    if content is None:
        return {"success": False, "error": "content 不能为 null/undefined,创建空文件请传空字符串", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    if mode not in _VALID_MODES:
        return {"success": False, "error": f"mode 必须是 {sorted(_VALID_MODES)} 之一", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    if violation := check_path_allowed(path):
        return violation
    if sensitive := check_sensitive_path(path, "write"):
        return sensitive

    target = Path(path)
    exists = target.exists()

    if mode == "create_only" and exists:
        return {"success": False, "error": f"文件已存在:{path}", "error_class": "MODEL_ERROR", "error_type": "file_exists", "hint": "如确需覆盖，先 read 获取 file_hash，再用 mode=overwrite。"}
    if mode in {"overwrite", "append"} and exists and not expected_file_hash:
        return {"success": False, "error": "覆盖或追加已有文件必须提供 expected_file_hash", "error_class": "MODEL_ERROR", "error_type": "expected_file_hash_required"}

    old_content = ""
    old_hash = None
    if exists:
        try:
            old_content = target.read_text(encoding="utf-8")
            old_hash = snapshot_file(target)["file_hash"]
        except UnicodeDecodeError:
            return {"success": False, "error": "文件非 UTF-8 编码,无法安全写入", "error_class": "ENV_ERROR", "error_type": "UnicodeDecodeError"}
        except PermissionError:
            return {"success": False, "error": f"无读取权限:{path}", "error_class": "ENV_ERROR", "error_type": "PermissionError"}
        if expected_file_hash and old_hash != expected_file_hash:
            return {"success": False, "error": "文件 hash 与 expected_file_hash 不一致", "error_class": "MODEL_ERROR", "error_type": "file_hash_mismatch", "current_file_hash": old_hash, "expected_file_hash": expected_file_hash}

    new_content = old_content + content if mode == "append" and exists else content
    diff = unified_diff(path, old_content, new_content)
    if dry_run:
        return {"success": True, "path": path, "dry_run": True, "diff": diff, "bytes_written": 0, "file_hash": hash_text(new_content)}

    backup_path = None
    if exists and mode in {"overwrite", "append"} and backup:
        backup_path = create_backup(target)

    try:
        write_atomic(path, new_content)
    except PermissionError:
        return {"success": False, "error": f"无写入权限:{path}", "error_class": "ENV_ERROR", "error_type": "PermissionError"}
    except OSError as e:
        return {"success": False, "error": f"写入失败:{e}", "error_class": "ENV_ERROR", "error_type": type(e).__name__}

    result = {"success": True, "path": path, "mode": mode, "bytes_written": len(new_content.encode("utf-8")), "file_hash": hash_text(new_content)}
    if backup_path:
        result["backup_path"] = backup_path
    return result
