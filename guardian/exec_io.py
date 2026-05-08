from __future__ import annotations

import fnmatch
import os
import re
import tempfile
from pathlib import Path

from .file_version import snapshot_file
from .roots import check_path_allowed
from .sensitive import check_sensitive_path


def write_atomic(path: str, content: str) -> None:
    if violation := check_path_allowed(path):
        raise PermissionError(violation["error"])
    abs_path = os.path.abspath(path)
    dir_name = os.path.dirname(abs_path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, abs_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def execute_read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    if violation := check_path_allowed(path):
        return violation
    if sensitive := check_sensitive_path(path, "read"):
        return sensitive
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        snapshot = snapshot_file(path)
    except FileNotFoundError:
        return {"success": False, "error": f"文件不存在:{path}", "error_class": "ENV_ERROR", "error_type": "FileNotFoundError", "hint": "先用 guardian_glob 确认路径"}
    except UnicodeDecodeError:
        return {"success": False, "error": "文件非 UTF-8 编码", "error_class": "ENV_ERROR", "error_type": "UnicodeDecodeError", "hint": "使用 guardian_run_bash 配合 file/xxd 查看编码"}
    except PermissionError:
        return {"success": False, "error": f"无读取权限:{path}", "error_class": "ENV_ERROR", "error_type": "PermissionError"}

    lines = raw.split("\n")
    total = len(lines)
    s = max(0, (start_line - 1) if start_line else 0)
    e = min(total, end_line if end_line else total)
    selected = lines[s:e]
    content = "\n".join(f"{s + i + 1}: {l}" for i, l in enumerate(selected))
    return {"success": True, "content": content, "total_lines": total, "shown_lines": f"{s + 1}-{e}", "truncated": (e - s) < total, **snapshot}



async def execute_glob(pattern: str, path: str | None = None) -> dict:
    if not pattern:
        return {"success": False, "error": "pattern 不能为空", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    base = Path(path or ".").resolve()
    if violation := check_path_allowed(base, "base path"):
        return violation
    if not base.exists():
        return {"success": False, "error": f"搜索目录不存在:{base}", "error_class": "ENV_ERROR", "error_type": "FileNotFoundError"}
    try:
        matches = sorted(str(p) for p in base.glob(pattern) if p.is_file())
    except Exception as e:
        return {"success": False, "error": f"glob 失败:{e}", "error_class": "MODEL_ERROR", "error_type": type(e).__name__, "hint": "确认 pattern 是 glob 语法(* / **)而非正则"}
    truncated_count = 0
    if len(matches) > 200:
        truncated_count = len(matches) - 200
        matches = matches[:200]
    result = {"success": True, "matches": matches, "count": len(matches)}
    if truncated_count:
        result["truncated_results"] = f"还有 {truncated_count} 个未显示,请缩小 pattern"
    return result


async def execute_grep(pattern: str, path: str | None = None, include: str | None = None) -> dict:
    if not pattern:
        return {"success": False, "error": "pattern 不能为空", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"success": False, "error": f"正则编译失败:{e}", "error_class": "MODEL_ERROR", "error_type": "regex_error", "hint": "使用 Python re 兼容语法"}
    base = Path(path or ".").resolve()
    if violation := check_path_allowed(base, "base path"):
        return violation
    if not base.exists():
        return {"success": False, "error": f"搜索目录不存在:{base}", "error_class": "ENV_ERROR", "error_type": "FileNotFoundError"}

    matches: list[dict] = []
    truncated = False
    max_matches = 100
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if include and not fnmatch.fnmatch(fname, include):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "rb") as f:
                    if b"\x00" in f.read(512):
                        continue
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            matches.append({"file": os.path.relpath(fpath, base), "line": lineno, "content": line.rstrip("\n")[:200]})
                            if len(matches) >= max_matches:
                                truncated = True
                                break
            except (OSError, UnicodeDecodeError):
                continue
            if truncated:
                break
        if truncated:
            break
    result = {"success": True, "matches": matches, "count": len(matches)}
    if truncated:
        result["truncated_results"] = f"超过 {max_matches} 处匹配,缩小 pattern 或加 include"
    return result
