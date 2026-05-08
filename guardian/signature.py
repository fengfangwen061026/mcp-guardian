from __future__ import annotations

import hashlib


def _stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:8]


def _bucket(value: int, thresholds: list[int]) -> str:
    for i, t in enumerate(thresholds):
        if value <= t:
            return str(i)
    return str(len(thresholds))


def extract_signature(tool_name: str, params: dict) -> str:
    # Six dimensions: target kind, size bucket, structural flags, line/token bucket, operation flags, path depth/scope.
    if tool_name == "guardian_edit_file":
        old_str = params.get("old_str", "") or ""
        path = params.get("path", "") or ""
        ext = path.rsplit(".", 1)[-1] if "." in path else "none"
        return (
            f"ext={ext}"
            f":old_len={_bucket(len(old_str), [10, 30, 80, 200])}"
            f":has_indent={old_str[:1] in (' ', chr(9))}"
            f":has_newline={chr(10) in old_str}"
            f":line_count={_bucket(old_str.count(chr(10)), [0, 1, 5, 20])}"
            f":path_depth={_bucket(path.count('/'), [1, 3, 6])}"
            f":sig={_stable_hash(path + chr(0) + old_str)}"
        )

    if tool_name == "guardian_run_bash":
        if params.get("argv") is not None:
            argv = params.get("argv") or []
            cmd_repr = "\0".join(argv)
            prefix = argv[0] if argv else ""
            return (
                "mode=argv"
                f":cmd={prefix}"
                f":argc={_bucket(len(argv), [1, 3, 8, 20])}"
                f":has_pipe={False}"
                f":has_redirect={False}"
                f":has_semicolon={False}"
                f":sig={_stable_hash(cmd_repr)}"
            )
        cmd = params.get("command", "") or ""
        tokens = cmd.split()
        prefix = tokens[0] if tokens else ""
        return (
            "mode=command"
            f":cmd={prefix}"
            f":token_count={_bucket(len(tokens), [1, 3, 8, 20])}"
            f":has_pipe={'|' in cmd}"
            f":has_redirect={'>' in cmd or '>>' in cmd}"
            f":has_semicolon={';' in cmd}"
            f":has_subshell={'$(' in cmd or '`' in cmd}"
            f":sig={_stable_hash(cmd)}"
        )

    if tool_name == "guardian_glob":
        pattern = params.get("pattern", "") or ""
        path = params.get("path", "") or ""
        return (
            f"kind=glob"
            f":pattern_len={_bucket(len(pattern), [5, 20, 80])}"
            f":has_doublestar={'**' in pattern}"
            f":has_braces={'{' in pattern}"
            f":ext_filter={pattern.rsplit('.', 1)[-1] if '.' in pattern else 'none'}"
            f":path_depth={_bucket(path.count('/'), [1, 3, 6])}"
        )

    if tool_name == "guardian_grep":
        pattern = params.get("pattern", "") or ""
        path = params.get("path", "") or ""
        return (
            f"kind=grep"
            f":pattern_len={_bucket(len(pattern), [5, 20, 50])}"
            f":has_quantifier={any(c in pattern for c in '+*?')}"
            f":has_group={'(' in pattern}"
            f":has_include={bool(params.get('include'))}"
            f":path_depth={_bucket(path.count('/'), [1, 3, 6])}"
        )

    if tool_name == "guardian_read_file":
        path = params.get("path", "") or ""
        return (
            f"kind=read"
            f":ext={path.rsplit('.', 1)[-1] if '.' in path else 'none'}"
            f":path_depth={_bucket(path.count('/'), [1, 3, 6])}"
            f":has_range={bool(params.get('start_line') or params.get('end_line'))}"
            f":start_bucket={_bucket(int(params.get('start_line') or 0), [0, 100, 1000])}"
            f":end_bucket={_bucket(int(params.get('end_line') or 0), [0, 100, 1000])}"
        )

    if tool_name == "guardian_write_file":
        path = params.get("path", "") or ""
        content_len = len(params.get("content", "") or "")
        return (
            f"kind=write"
            f":ext={path.rsplit('.', 1)[-1] if '.' in path else 'none'}"
            f":content_len={_bucket(content_len, [100, 1000, 10000])}"
            f":has_newline={chr(10) in (params.get('content', '') or '')}"
            f":path_depth={_bucket(path.count('/'), [1, 3, 6])}"
            f":abs_path={path.startswith('/')}"
        )

    return f"tool={tool_name}:generic"
