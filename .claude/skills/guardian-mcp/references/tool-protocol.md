# Guardian MCP Tool Protocol

## Read before edit

1. Read the file:
   - `mcp__guardian__guardian_read_file({"path":"/absolute/path"})`
2. Build `old_str` from the returned content after removing `N: ` line prefixes.
3. Edit with exact strings:
   - `mcp__guardian__guardian_edit_file({"path":"/absolute/path","old_str":"...","new_str":"..."})`
4. If the edit fails and returns `file_content`, copy the current text from `file_content`, not from the original attempt.

## Create or overwrite files

Use `guardian_write_file` for new generated files or intentional full-file rewrites. It overwrites the complete file with UTF-8 content, so read first when preserving existing content matters.

## Search workflow

- Known name or extension: `guardian_glob({"path":"/project/root","pattern":"**/*.py"})`
- Known symbol or phrase: `guardian_grep({"path":"/project/root","pattern":"functionName"})`
- Too many matches: narrow `path`, add an extension, or query `guardian_get_spec` for the relevant tool.

## Shell workflow

- Run in a directory with `cwd` rather than shell `cd`.
- Add explicit `timeout` for tests, installs, builds, and package manager commands.
- Prefer narrow, inspectable commands over broad destructive commands.

Example:

```json
{
  "command": ".venv/bin/python -m pytest tests/ -v",
  "cwd": "/home/ffw/Desktop/工作室/guardian",
  "timeout": 120000
}
```

## Recovery checklist

- `file_not_found`: check path with `guardian_glob`, confirm case, then create only if intended.
- `old_str` mismatch: re-read, remove line prefixes, copy exact whitespace.
- `HARD_BLOCKED`: call `guardian_get_spec(tool_name)` or change parameters.
- Repeated failure: change strategy before retrying.
