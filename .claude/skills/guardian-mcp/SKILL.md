---
name: guardian-mcp
description: Use this skill whenever working with the self-built Guardian MCP or the mcp-guardian repository, especially for file reads, file creation, edits, searches, shell commands, tool failures, or HARD_BLOCKED responses. This skill teaches Claude to prefer mcp__guardian__guardian_* tools, follow Guardian's read-before-edit and exact old_str protocols, recover from MCP errors correctly, and avoid repeated blocked calls.
---

# Guardian MCP

Use Guardian as the preferred local execution layer when Guardian MCP tools are available. Guardian wraps file, search, edit, and shell operations with safety checks and structured recovery guidance.

## Tool selection

Prefer these Guardian tools over native tools for matching operations:

- Read files with `mcp__guardian__guardian_read_file`.
- Create or fully overwrite files with `mcp__guardian__guardian_write_file`.
- Edit existing files with `mcp__guardian__guardian_edit_file` after reading the target file.
- Search file paths with `mcp__guardian__guardian_glob`.
- Search file contents with `mcp__guardian__guardian_grep`.
- Run shell commands with `mcp__guardian__guardian_run_bash`.
- Query exact tool rules with `mcp__guardian__guardian_get_spec` when blocked, uncertain, or recovering from repeated failures.

Use native Claude Code tools only when Guardian lacks the needed capability, when another project instruction explicitly requires a native tool, or when the Guardian tool itself is unavailable.

## Editing protocol

Follow this sequence for every local file edit:

1. Read the file with `guardian_read_file` before editing.
2. Copy `old_str` from the actual file content, not from memory.
3. Remove Guardian line-number prefixes from `old_str`; `guardian_read_file` returns lines like `12: actual text`, but `old_str` must contain only `actual text`.
4. Preserve exact whitespace, indentation, and line breaks in `old_str`.
5. Use `guardian_edit_file` for local modifications.
6. Use `guardian_write_file` only for new files, generated files, or deliberate full-file rewrites.
7. Re-read or otherwise verify the changed region after editing when correctness matters.

Do not retry the same failed edit with identical parameters. If an edit fails and returns `file_content`, copy the corrected `old_str` from that returned content, again removing line-number prefixes.

## Command protocol

Use `guardian_run_bash` for shell commands.

- Prefer the `cwd` parameter over `cd ... && ...`.
- Set explicit `timeout` for long-running commands: installs and builds generally need 180000-600000 ms; tests often need 120000-300000 ms.
- Use non-interactive flags for commands that may wait for input.
- Avoid destructive or broad commands; if Guardian blocks a command, read the `error` and `guidance` fields and reformulate the command safely.

## Error recovery

Guardian responses are structured. On failure:

1. Read `error` to understand what failed.
2. Read `guidance` for the intended fix.
3. Change the approach before retrying; do not repeat identical parameters after a warning or failure.
4. On `HARD_BLOCKED`, change parameter shape or call `guardian_get_spec(tool_name)` before trying again.
5. For missing files, use `guardian_glob` to confirm the path and case sensitivity before creating or editing.
6. For permission errors, stay inside the project directory instead of bypassing permissions.

## When to query specs

Call `guardian_get_spec` when any of these apply:

- A Guardian tool returns `HARD_BLOCKED`.
- A Guardian edit, read, write, glob, grep, or shell call fails twice in the same workflow.
- The exact parameter convention is unclear.
- The task depends on details such as line numbering, full overwrite behavior, timeouts, or blocked command categories.

## Reference

Read `references/tool-protocol.md` for compact examples of common Guardian workflows and recovery patterns.
