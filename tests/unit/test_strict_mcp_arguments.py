import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from tum_mcp.moodle.protocol import StrictMCPServer


def test_invalid_arguments_name_fields_without_echoing_values() -> None:
    # A trial agent sent `limit` to a tool without that field and had to guess the fix.
    server = StrictMCPServer("Synthetic")

    @server.tool()
    def list_courses(course_id: int) -> str:
        return str(course_id)

    async def exercise() -> None:
        with pytest.raises(ToolError) as unexpected:
            await server.call_tool("list_courses", {"course_id": 1, "limit": 100})
        assert "limit" in str(unexpected.value) and "course_id" in str(unexpected.value)
        with pytest.raises(ToolError) as missing:
            await server.call_tool("list_courses", {})
        assert "course_id" in str(missing.value)
        with pytest.raises(ToolError) as wrong:
            await server.call_tool("list_courses", {"course_id": "private-value"})
        assert "course_id" in str(wrong.value)
        assert "private-value" not in str(wrong.value)

    anyio.run(exercise)
