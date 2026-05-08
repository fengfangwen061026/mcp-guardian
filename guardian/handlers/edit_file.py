from __future__ import annotations

from ..file_version import invalidate_path_reads, validate_edit_precondition
from ..exec_io import write_atomic
from ..roots import check_path_allowed
from ..sensitive import check_sensitive_path
from ..state import SessionState


async def handle_edit_file(
    session: SessionState | None,
    path: str,
    old_str: str,
    new_str: str,
    expected_read_id: str | None = None,
    expected_file_hash: str | None = None,
) -> dict:
    if not old_str:
        return {"success": False, "error": "old_str 不能为空", "error_class": "MODEL_ERROR", "error_type": "empty_old_str"}
    if violation := check_path_allowed(path):
        return violation
    if sensitive := check_sensitive_path(path, "edit"):
        return sensitive
    if precondition := validate_edit_precondition(session, path, expected_read_id, expected_file_hash):
        return precondition
    try:
        with open(path, encoding="utf-8") as f:
            raw_content = f.read()
    except FileNotFoundError:
        return {"success": False, "error": f"文件不存在:{path}", "error_class": "ENV_ERROR", "error_type": "FileNotFoundError", "hint": "先用 guardian_glob 确认路径"}
    except UnicodeDecodeError:
        return {"success": False, "error": "文件非 UTF-8 编码,无法编辑", "error_class": "ENV_ERROR", "error_type": "UnicodeDecodeError", "hint": "使用 guardian_run_bash 配合 sed/iconv 处理"}
    except PermissionError:
        return {"success": False, "error": f"无读取权限:{path}", "error_class": "ENV_ERROR", "error_type": "PermissionError"}

    candidates = [
        (raw_content, old_str),
        (raw_content.replace("\r\n", "\n"), old_str.replace("\r\n", "\n")),
    ]
    matched_content: str | None = None
    matched_old: str | None = None
    match_count = 0
    for content_variant, old_variant in candidates:
        if old_variant not in content_variant:
            continue
        matched_content = content_variant
        matched_old = old_variant
        match_count = content_variant.count(old_variant)
        break

    if matched_content is None:
        lines = raw_content.split("\n")
        preview_end = min(50, len(lines))
        return {
            "success": False,
            "error": "old_str 在文件中不存在",
            "error_class": "MODEL_ERROR",
            "error_type": "old_string_not_found",
            "hint": "从下方 file_content 中精确复制需修改的片段,不要手动输入",
            "file_content": "\n".join(f"{i + 1}: {l}" for i, l in enumerate(lines[:preview_end])),
            "total_lines": len(lines),
            "truncated": len(lines) > preview_end,
        }
    if match_count > 1:
        return {"success": False, "error": f"old_str 匹配到 {match_count} 处,需更多上下文唯一定位", "error_class": "MODEL_ERROR", "error_type": "appears_multiple_times", "hint": "扩展 old_str,加入前后各 2-3 行代码直到唯一"}

    new_content = matched_content.replace(matched_old, new_str, 1)
    write_atomic(path, new_content)
    invalidate_path_reads(session, path)
    result: dict = {"success": True, "path": path}
    if matched_old != old_str:
        result["note"] = "已自动归一化 CRLF→LF"
    return result
