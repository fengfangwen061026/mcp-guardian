from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool, ToolAnnotations

from .dispatch import TOOL_NAMES, dispatch
from .persist import OffsetStore, flush_session
from .state import SessionState

LOG_DIR = Path.home() / ".claude" / "guardian" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / f"guardian-{int(time.time())}.log")],
)
log = logging.getLogger("guardian")

READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE_FILE_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
EDIT_FILE_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
RUN_BASH_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)

BASE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether the Guardian tool completed the requested operation."},
        "error": {"type": "string", "description": "Human-readable error summary when success is false."},
        "error_class": {"type": "string", "description": "Broad error category such as MODEL_ERROR, ENV_ERROR, SECURITY, or TRANSIENT."},
        "error_type": {"type": "string", "description": "Specific machine-readable error type."},
        "guidance": {"type": "array", "description": "Optional recovery guidance entries for the model.", "items": {"type": "object"}},
    },
    "required": ["success"],
    "additionalProperties": True,
}


def _object_schema(properties: dict, required: list[str] | None = None, **extra: object) -> dict:
    schema = {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}
    schema.update(extra)
    return schema


def _tool(name: str, description: str, input_schema: dict, annotations: ToolAnnotations) -> Tool:
    return Tool(name=name, description=description, inputSchema=input_schema, annotations=annotations)


TOOL_DEFINITIONS = [
    _tool(
        "guardian_read_file",
        "读取文件内容,返回带行号前缀的纯文本。",
        _object_schema(
            {
                "path": {"type": "string", "minLength": 1, "description": "File path to read."},
                "start_line": {"type": "integer", "minimum": 1, "description": "Optional 1-based first line to include."},
                "end_line": {"type": "integer", "minimum": 1, "description": "Optional 1-based final line to include."},
            },
            ["path"],
        ),
        READ_ONLY_ANNOTATIONS,
    ),
    _tool(
        "guardian_write_file",
        "安全创建、覆盖或追加 UTF-8 文件；默认 create_only，覆盖已有文件必须提供 expected_file_hash。",
        _object_schema(
            {
                "path": {"type": "string", "minLength": 1, "description": "Target file path to create, overwrite, or append."},
                "content": {"type": "string", "description": "UTF-8 file content to write or append; use an empty string for an empty file."},
                "mode": {"type": "string", "enum": ["create_only", "overwrite", "append"], "description": "Write mode; defaults to create_only."},
                "expected_file_hash": {"type": "string", "minLength": 1, "description": "Required when overwriting or appending to an existing file."},
                "dry_run": {"type": "boolean", "description": "Return a diff without writing."},
                "backup": {"type": "boolean", "description": "Create a backup before overwriting or appending; defaults to true."},
                "_ack": {"type": "string", "minLength": 1, "description": "Acknowledgement token required only after MODEL_ACK_REQUIRED."},
            },
            ["path", "content"],
        ),
        WRITE_FILE_ANNOTATIONS,
    ),
    _tool(
        "guardian_edit_file",
        "精确字符串替换。old_str 必须从文件实际内容中精确复制。",
        _object_schema(
            {
                "path": {"type": "string", "minLength": 1, "description": "File path to edit."},
                "old_str": {"type": "string", "minLength": 1, "description": "Exact existing text copied from the file without Guardian line prefixes."},
                "new_str": {"type": "string", "description": "Replacement text."},
                "expected_read_id": {"type": "string", "minLength": 1, "description": "read_id returned by guardian_read_file for this file."},
                "expected_file_hash": {"type": "string", "minLength": 1, "description": "file_hash returned by guardian_read_file for this file."},
                "_ack": {"type": "string", "minLength": 1, "description": "Acknowledgement token required only after MODEL_ACK_REQUIRED."},
            },
            ["path", "old_str", "new_str"],
        ),
        EDIT_FILE_ANNOTATIONS,
    ),
    _tool(
        "guardian_run_bash",
        "执行 shell 命令或 argv 命令,包含安全检查和超时控制。",
        _object_schema(
            {
                "command": {"type": "string", "minLength": 1, "description": "Shell command string. Provide either command or argv, not both. Use only when shell features such as pipes or redirects are needed."},
                "argv": {"type": "array", "minItems": 1, "description": "Safer argument-vector mode. Provide either argv or command, not both. Prefer this for user input or dynamic arguments.", "items": {"type": "string", "minLength": 1}},
                "cwd": {"type": "string", "minLength": 1, "description": "Optional working directory for the command."},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 600000, "description": "Timeout in milliseconds."},
                "description": {"type": "string", "minLength": 1, "description": "Human-readable purpose; required for high-risk commands."},
                "_ack": {"type": "string", "minLength": 1, "description": "Acknowledgement token reserved for risky operations."},
            },
            [],
        ),
        RUN_BASH_ANNOTATIONS,
    ),
    _tool(
        "guardian_glob",
        "按 glob 模式搜索文件。",
        _object_schema(
            {
                "pattern": {"type": "string", "minLength": 1, "description": "Glob pattern such as *.py or **/*.md."},
                "path": {"type": "string", "minLength": 1, "description": "Optional base directory; defaults to current working directory."},
            },
            ["pattern"],
        ),
        READ_ONLY_ANNOTATIONS,
    ),
    _tool(
        "guardian_grep",
        "在文件内容中搜索,优先使用 rg,失败时回退 Python。",
        _object_schema(
            {
                "pattern": {"type": "string", "minLength": 1, "description": "Pattern to search for; Python regex by default, literal text when literal=true."},
                "path": {"type": "string", "minLength": 1, "description": "Optional base directory or file; defaults to current working directory."},
                "include": {"type": "string", "minLength": 1, "description": "Optional filename/path glob filter such as *.py or src/**/*.py."},
                "exclude": {"type": "string", "minLength": 1, "description": "Optional filename/path glob exclusion."},
                "context_lines": {"type": "integer", "minimum": 0, "maximum": 20, "description": "Number of surrounding lines before and after each match."},
                "literal": {"type": "boolean", "description": "Treat pattern as literal text instead of regex."},
                "case_sensitive": {"type": "boolean", "description": "Whether matching is case-sensitive; defaults to true."},
                "max_matches": {"type": "integer", "minimum": 1, "maximum": 1000, "description": "Maximum matches to return; defaults to 100."},
            },
            ["pattern"],
        ),
        READ_ONLY_ANNOTATIONS,
    ),
    _tool(
        "guardian_get_spec",
        "查询某个 guardian 工具的规范和最佳实践。",
        _object_schema(
            {
                "tool_name": {"type": "string", "enum": sorted(TOOL_NAMES), "description": "Guardian tool name to inspect and unlock."},
                "error_history": {"type": "array", "description": "Optional recent errors for future clients; currently ignored.", "items": {"type": "object"}},
            },
            ["tool_name"],
        ),
        READ_ONLY_ANNOTATIONS,
    ),
    _tool(
        "guardian_pending_approvals",
        "只读列出当前 session 待人工审批的高风险操作。",
        _object_schema({}),
        READ_ONLY_ANNOTATIONS,
    ),
    _tool(
        "guardian_status",
        "查看当前 Guardian session 的模式、熔断和计数状态。",
        _object_schema({}),
        READ_ONLY_ANNOTATIONS,
    ),
]


class GuardianServer:
    def __init__(self):
        self.server: Server = Server("guardian-mcp")
        self._sessions = {}
        self.session: SessionState | None = None
        self.store: OffsetStore = OffsetStore()
        self._register_handlers()

    def _get_or_create_session(self) -> SessionState:
        if self.session is None:
            session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
            self.session = SessionState(session_id=session_id, model_hint=os.environ.get("GUARDIAN_MODEL_HINT", "_default"))
            self._sessions[session_id] = self.session
            log.info("session created: %s (model_hint=%s)", self.session.session_id, self.session.model_hint)
        return self.session

    def _register_handlers(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return TOOL_DEFINITIONS

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> tuple[list[TextContent], dict]:
            session = self._get_or_create_session()
            log.info("tool call: %s args_keys=%s", name, list((arguments or {}).keys()))
            try:
                result = await dispatch(session, name, arguments or {}, self.store)
            except Exception as e:
                log.exception("dispatch error in %s", name)
                result = {"success": False, "error": f"Guardian 内部错误:{type(e).__name__}: {e}", "error_class": "TRANSIENT", "error_type": type(e).__name__}
            content = [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            return content, result

    async def run(self) -> None:
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(read_stream, write_stream, self.server.create_initialization_options())
        finally:
            if self.session is not None:
                asyncio.create_task(flush_session(self.session))


def main() -> None:
    asyncio.run(GuardianServer().run())


if __name__ == "__main__":
    main()
