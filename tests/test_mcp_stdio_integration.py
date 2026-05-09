import asyncio

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER = ".venv/bin/guardian-mcp"


async def _with_session(coro):
    params = StdioServerParameters(command=SERVER)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await coro(session)


@pytest.mark.asyncio
async def test_stdio_lists_claude_code_safe_tools():
    async def run(session):
        result = await session.list_tools()
        assert len(result.tools) == 9
        for tool in result.tools:
            assert "oneOf" not in tool.inputSchema
            assert "anyOf" not in tool.inputSchema
            assert "allOf" not in tool.inputSchema
            assert tool.annotations is not None

    await _with_session(run)


@pytest.mark.asyncio
async def test_stdio_smoke_calls_readonly_tools(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("hello\nworld\n", encoding="utf-8")

    async def run(session):
        status = await session.call_tool("guardian_status", {})
        assert status.structuredContent["success"] is True

        read = await session.call_tool("guardian_read_file", {"path": str(sample)})
        assert read.structuredContent["success"] is True
        assert "hello" in read.structuredContent["content"]

        glob = await session.call_tool("guardian_glob", {"pattern": "*.txt", "path": str(tmp_path)})
        assert glob.structuredContent["success"] is True
        assert glob.structuredContent["count"] == 1

        grep = await session.call_tool("guardian_grep", {"pattern": "hello", "path": str(tmp_path)})
        assert grep.structuredContent["success"] is True
        assert grep.structuredContent["count"] == 1

        spec = await session.call_tool("guardian_get_spec", {"tool_name": "guardian_read_file"})
        assert spec.structuredContent["success"] is True

    await _with_session(run)


@pytest.mark.asyncio
async def test_stdio_run_bash_validation_and_argv_mode():
    async def run(session):
        missing = await session.call_tool("guardian_run_bash", {})
        missing_text = missing.content[0].text
        assert '"success": false' in missing_text
        assert '"error_type": "ValidationError"' in missing_text

        both = await session.call_tool("guardian_run_bash", {"command": "echo x", "argv": ["echo", "x"]})
        both_text = both.content[0].text
        assert '"success": false' in both_text
        assert '"error_type": "ValidationError"' in both_text

        argv = await session.call_tool("guardian_run_bash", {"argv": ["python3", "-c", "print('ok')"]})
        argv_text = argv.content[0].text
        assert '"success": true' in argv_text
        assert '"execution_mode": "argv"' in argv_text
        assert "ok" in argv_text

    await _with_session(run)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stdio_multiple_clients_can_run_concurrently():
    async def one(index):
        async def run(session):
            result = await session.call_tool("guardian_status", {})
            assert result.structuredContent["success"] is True
            tools = await session.list_tools()
            assert len(tools.tools) == 9
            return index
        return await _with_session(run)

    results = await asyncio.gather(*(one(i) for i in range(8)))
    assert sorted(results) == list(range(8))
