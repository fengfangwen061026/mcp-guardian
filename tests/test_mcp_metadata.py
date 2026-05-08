import jsonschema
import pytest
from mcp.types import CallToolRequest, TextContent

from guardian.dispatch import TOOL_NAMES, dispatch
from guardian.persist import OffsetStore
from guardian.server import TOOL_DEFINITIONS, GuardianServer
from guardian.state import SessionState


def test_all_tools_have_annotations():
    assert {tool.name for tool in TOOL_DEFINITIONS} == TOOL_NAMES
    for tool in TOOL_DEFINITIONS:
        assert tool.annotations is not None
        assert tool.annotations.destructiveHint is not None
        assert tool.annotations.idempotentHint is not None
        assert tool.annotations.openWorldHint is not None
        assert tool.annotations.readOnlyHint is not None


def test_schema_properties_have_descriptions():
    for tool in TOOL_DEFINITIONS:
        assert tool.inputSchema.get("additionalProperties") is False
        for schema in tool.inputSchema.get("properties", {}).values():
            assert "description" in schema


def test_get_spec_enum_covers_all_tools():
    get_spec = next(tool for tool in TOOL_DEFINITIONS if tool.name == "guardian_get_spec")
    enum = get_spec.inputSchema["properties"]["tool_name"]["enum"]
    assert set(enum) == TOOL_NAMES


@pytest.mark.asyncio
async def test_dispatch_output_satisfies_tool_output_schema(tmp_path):
    session = SessionState(session_id="schema_test")
    store = OffsetStore(tmp_path / "events.db")
    status_tool = next(tool for tool in TOOL_DEFINITIONS if tool.name == "guardian_status")

    result = await dispatch(session, "guardian_status", {}, store)

    jsonschema.validate(instance=result, schema=status_tool.outputSchema)


@pytest.mark.asyncio
async def test_call_tool_returns_text_and_structured_content():
    guardian = GuardianServer()
    handler = guardian.server.request_handlers[CallToolRequest]
    call_tool = handler.__closure__[0].cell_contents

    result = await call_tool("guardian_status", {})

    content, structured = result
    assert isinstance(content[0], TextContent)
    assert structured["success"] is True
