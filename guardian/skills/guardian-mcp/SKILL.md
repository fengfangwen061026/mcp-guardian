---
name: guardian-mcp
description: Use this skill whenever working in a project configured with the Guardian MCP server, especially for file reads, file creation, edits, searches, shell commands, Guardian tool failures, or HARD_BLOCKED responses. This skill teaches Claude to prefer mcp__guardian__guardian_* tools, use argv for safer commands, follow read-before-edit and exact old_str protocols, respect optional roots limits, and recover from MCP errors without repeated failed calls.
---

# Guardian MCP

Use Guardian as the preferred local execution layer when Guardian MCP tools are available. Guardian wraps file, search, edit, and shell operations with safety checks, structured results, roots-aware path handling, and recovery guidance.

## Tool selection

Prefer these Guardian tools over native tools for matching operations:

- Read files with `mcp__guardian__guardian_read_file`.
- Create or fully overwrite files with `mcp__guardian__guardian_write_file`.
- Edit existing files with `mcp__guardian__guardian_edit_file` after reading the target file.
- Search file paths with `mcp__guardian__guardian_glob`.
- Search file contents with `mcp__guardian__guardian_grep`.
- Run commands with `mcp__guardian__guardian_run_bash`.
- Query exact tool rules with `mcp__guardian__guardian_get_spec` when blocked, uncertain, or recovering from repeated failures.
- Use `mcp__guardian__guardian_status` to inspect circuit breaker and roots state.

Use native Claude Code tools only when Guardian lacks the needed capability, another project instruction explicitly requires a native tool, or the Guardian tool itself is unavailable.

## Editing protocol

Follow this sequence for every local file edit:

1. Read the file with `guardian_read_file` before editing.
2. Copy `old_str` from actual file content, not from memory.
3. Remove Guardian line-number prefixes from `old_str`; `guardian_read_file` returns lines like `12: actual text`, but `old_str` must contain only `actual text`.
4. Preserve exact whitespace, indentation, and line breaks in `old_str`.
5. Use `guardian_edit_file` for local modifications.
6. Use `guardian_write_file` only for new files, generated files, or deliberate full-file rewrites.
7. Re-read or otherwise verify the changed region after editing when correctness matters.

Do not retry the same failed edit with identical parameters. If an edit fails and returns `file_content`, copy the corrected `old_str` from that returned content, again removing line-number prefixes.

## Command protocol

Use `guardian_run_bash` for shell commands.

- Prefer `argv` for user input or dynamic arguments, for example `{ "argv": ["python3", "script.py"] }`.
- Use `command` only when shell syntax is needed, such as pipes, redirects, or glob expansion.
- Prefer the `cwd` parameter over `cd ... && ...`.
- Set explicit `timeout` for long-running commands: installs and builds generally need 180000-600000 ms; tests often need 120000-300000 ms.
- Use non-interactive flags for commands that may wait for input.
- Avoid destructive or broad commands; if Guardian blocks a command, read `error` and `guidance` and reformulate safely.

## Error recovery

Guardian responses are structured. On failure:

1. Read `error` to understand what failed.
2. Read `error_class` and `error_type` to distinguish model, environment, security, and transient failures.
3. Read `guidance` for the intended fix.
4. Change the approach before retrying; do not repeat identical parameters after a warning or failure.
5. On `HARD_BLOCKED`, change parameter shape or call `guardian_get_spec(tool_name)` before trying again.
6. For missing files, use `guardian_glob` to confirm the path and case sensitivity before creating or editing.
7. For `PathOutsideRoot`, stay inside the configured roots or ask the user whether roots should be changed.

## When to query specs

Call `guardian_get_spec` when any of these apply:

- A Guardian tool returns `HARD_BLOCKED`.
- A Guardian edit, read, write, glob, grep, or shell call fails twice in the same workflow.
- The exact parameter convention is unclear.
- The task depends on details such as line numbering, full overwrite behavior, timeouts, blocked command categories, or roots behavior.
