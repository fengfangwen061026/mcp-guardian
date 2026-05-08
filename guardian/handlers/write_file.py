from __future__ import annotations

from ..exec_io import write_atomic
from ..roots import check_path_allowed


async def execute_write_file(path: str, content: str) -> dict:
    if content is None:
        return {"success": False, "error": "content 不能为 null/undefined,创建空文件请传空字符串", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    if violation := check_path_allowed(path):
        return violation
    try:
        write_atomic(path, content)
    except PermissionError:
        return {"success": False, "error": f"无写入权限:{path}", "error_class": "ENV_ERROR", "error_type": "PermissionError"}
    except OSError as e:
        return {"success": False, "error": f"写入失败:{e}", "error_class": "ENV_ERROR", "error_type": type(e).__name__}
    return {"success": True, "path": path, "bytes_written": len(content.encode("utf-8"))}
