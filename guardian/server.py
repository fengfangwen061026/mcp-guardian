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
from mcp.types import TextContent, Tool

from .dispatch import dispatch
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

TOOL_DEFINITIONS = [
    Tool(name="guardian_read_file", description="读取文件内容,返回带行号前缀的纯文本。", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}),
    Tool(name="guardian_write_file", description="创建或完全覆写文件。父目录不存在时自动创建。", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}),
    Tool(name="guardian_edit_file", description="精确字符串替换。old_str 必须从文件实际内容中精确复制。", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}, "_ack": {"type": "string"}}, "required": ["path", "old_str", "new_str"]}),
    Tool(name="guardian_run_bash", description="执行 shell 命令,包含安全检查和超时控制。", inputSchema={"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout": {"type": "integer"}, "_ack": {"type": "string"}}, "required": ["command"]}),
    Tool(name="guardian_glob", description="按 glob 模式搜索文件。", inputSchema={"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}),
    Tool(name="guardian_grep", description="在文件内容中搜索 Python 兼容正则。", inputSchema={"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "include": {"type": "string"}}, "required": ["pattern"]}),
    Tool(name="guardian_get_spec", description="查询某个 guardian 工具的规范和最佳实践。", inputSchema={"type": "object", "properties": {"tool_name": {"type": "string"}, "error_history": {"type": "array", "items": {"type": "object"}}}, "required": ["tool_name"]}),
    Tool(name="guardian_status", description="查看当前 Guardian session 的模式、熔断和计数状态。", inputSchema={"type": "object", "properties": {}}),
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
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            session = self._get_or_create_session()
            log.info("tool call: %s args_keys=%s", name, list((arguments or {}).keys()))
            try:
                result = await dispatch(session, name, arguments or {}, self.store)
            except Exception as e:
                log.exception("dispatch error in %s", name)
                result = {"success": False, "error": f"Guardian 内部错误:{type(e).__name__}: {e}", "error_class": "TRANSIENT", "error_type": type(e).__name__}
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

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
