from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ..roots import check_path_allowed
from ..sensitive import check_sensitive_path

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}


async def execute_grep(
    pattern: str,
    path: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    context_lines: int = 0,
    literal: bool = False,
    case_sensitive: bool = True,
    max_matches: int = 100,
) -> dict:
    if not pattern:
        return {"success": False, "error": "pattern 不能为空", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    if context_lines < 0:
        return {"success": False, "error": "context_lines 不能为负数", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}
    if max_matches < 1:
        return {"success": False, "error": "max_matches 必须大于 0", "error_class": "MODEL_ERROR", "error_type": "ValidationError"}

    base = Path(path or ".").resolve()
    if violation := check_path_allowed(base, "base path"):
        return violation
    if not base.exists():
        return {"success": False, "error": f"搜索目录不存在:{base}", "error_class": "ENV_ERROR", "error_type": "FileNotFoundError"}

    files_result = _safe_files(base, include, exclude)
    if isinstance(files_result, dict):
        return files_result
    if shutil.which("rg"):
        return _grep_rg(pattern, base, files_result, context_lines, literal, case_sensitive, max_matches)
    return _grep_python(pattern, base, files_result, context_lines, literal, case_sensitive, max_matches)


def _grep_rg(pattern: str, base: Path, files: list[Path], context_lines: int, literal: bool, case_sensitive: bool, max_matches: int) -> dict:
    if not files:
        return {"success": True, "backend": "rg", "matches": [], "count": 0}
    args = ["rg", "--json", "--line-number", "--max-count", str(max_matches)]
    if literal:
        args.append("--fixed-strings")
    if not case_sensitive:
        args.append("--ignore-case")
    if context_lines:
        args.extend(["--context", str(context_lines)])
    args.append(pattern)
    args.extend(str(path) for path in files)

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    except OSError:
        return _grep_python(pattern, base, files, context_lines, literal, case_sensitive, max_matches, backend="python")
    except subprocess.TimeoutExpired:
        return {"success": False, "backend": "rg", "error": "搜索超时", "error_class": "TRANSIENT", "error_type": "TimeoutError"}

    if proc.returncode not in {0, 1}:
        return {"success": False, "backend": "rg", "error": proc.stderr.strip() or "rg 搜索失败", "error_class": "MODEL_ERROR", "error_type": "SearchError"}

    return _parse_rg_output(proc.stdout, base, context_lines, max_matches)


def _grep_python(
    pattern: str,
    base: Path,
    files: list[Path],
    context_lines: int,
    literal: bool,
    case_sensitive: bool,
    max_matches: int,
    backend: str = "python",
) -> dict:
    try:
        regex = _compile_pattern(pattern, literal, case_sensitive)
    except re.error as exc:
        return {"success": False, "backend": backend, "error": f"正则编译失败:{exc}", "error_class": "MODEL_ERROR", "error_type": "regex_error", "hint": "使用 Python re 兼容语法,或设置 literal=true"}

    matches: list[dict] = []
    truncated = False
    for fpath in files:
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            if not regex.search(line):
                continue
            matches.append(_match_entry(base, fpath, index, line, lines, context_lines))
            if len(matches) >= max_matches:
                truncated = True
                break
        if truncated:
            break

    result = {"success": True, "backend": backend, "matches": matches, "count": len(matches)}
    if truncated:
        result["truncated_results"] = f"超过 {max_matches} 处匹配,缩小 pattern 或调整 max_matches"
    return result


def _parse_rg_output(output: str, base: Path, context_lines: int, max_matches: int) -> dict:
    matches: list[dict] = []
    before_by_file: dict[str, list[dict]] = {}
    last_match: dict | None = None
    truncated = False
    rel_base = base.parent if base.is_file() else base
    for raw in output.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        data = event.get("data") or {}
        path = data.get("path", {}).get("text")
        if kind == "context" and path:
            context = {"line": data.get("line_number"), "content": data.get("lines", {}).get("text", "").rstrip("\n")[:200]}
            if last_match and last_match["file"] == str(Path(path).relative_to(rel_base)) and data.get("line_number", 0) > last_match["line"]:
                last_match.setdefault("context_after", []).append(context)
            else:
                before_by_file.setdefault(path, []).append(context)
            continue
        if kind != "match" or not path:
            continue
        rel = str(Path(path).relative_to(rel_base))
        entry = {"file": rel, "line": data.get("line_number"), "content": data.get("lines", {}).get("text", "").rstrip("\n")[:200]}
        if context_lines:
            entry["context_before"] = before_by_file.get(path, [])[-context_lines:]
            entry["context_after"] = []
        matches.append(entry)
        last_match = entry
        if len(matches) >= max_matches:
            truncated = True
            break
    result = {"success": True, "backend": "rg", "matches": matches, "count": len(matches)}
    if truncated:
        result["truncated_results"] = f"超过 {max_matches} 处匹配,缩小 pattern 或调整 max_matches"
    return result


def _compile_pattern(pattern: str, literal: bool, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(re.escape(pattern) if literal else pattern, flags)


def _safe_files(base: Path, include: str | None, exclude: str | None) -> list[Path] | dict:
    files: list[Path] = []
    for fpath in _iter_files(base, include, exclude):
        try:
            resolved = fpath.resolve()
        except OSError:
            continue
        if violation := check_path_allowed(resolved, "search file"):
            if violation.get("error_type") == "PathOutsideRoot":
                continue
            return violation
        sensitive = check_sensitive_path(resolved, "grep")
        if sensitive:
            if sensitive.get("error_type") == "PolicyConfigError":
                return sensitive
            continue
        try:
            with open(fpath, "rb") as fh:
                if b"\x00" in fh.read(512):
                    continue
        except OSError:
            continue
        files.append(fpath)
    return files


def _iter_files(base: Path, include: str | None, exclude: str | None):
    if base.is_file():
        if _file_allowed(base, base, include, exclude):
            yield base
        return
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not (exclude and fnmatch.fnmatch(d, exclude))]
        for fname in files:
            fpath = Path(root) / fname
            if _file_allowed(base, fpath, include, exclude):
                yield fpath


def _file_allowed(base: Path, path: Path, include: str | None, exclude: str | None) -> bool:
    rel = path.relative_to(base.parent if base.is_file() else base).as_posix()
    if include and not (fnmatch.fnmatch(path.name, include) or fnmatch.fnmatch(rel, include)):
        return False
    if exclude and (fnmatch.fnmatch(path.name, exclude) or fnmatch.fnmatch(rel, exclude)):
        return False
    return True


def _match_entry(base: Path, fpath: Path, index: int, line: str, lines: list[str], context_lines: int) -> dict:
    rel_base = base.parent if base.is_file() else base
    entry = {"file": str(fpath.relative_to(rel_base)), "line": index + 1, "content": line[:200]}
    if context_lines:
        before_start = max(0, index - context_lines)
        after_end = min(len(lines), index + context_lines + 1)
        entry["context_before"] = [{"line": i + 1, "content": lines[i][:200]} for i in range(before_start, index)]
        entry["context_after"] = [{"line": i + 1, "content": lines[i][:200]} for i in range(index + 1, after_end)]
    return entry
