import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_stdio_server_reports_login_required(tmp_path: Path) -> None:
    async def check() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tum_mcp.moodle", "serve"],
            env={**os.environ, "TUM_MOODLE_DATA_DIR": str(tmp_path)},
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert "moodle_auth_status" in {tool.name for tool in tools.tools}
                result = await client.call_tool("moodle_auth_status")
                assert not result.is_error
                assert result.structured_content["state"] == "AUTH_REQUIRED"
                failure = await client.call_tool("moodle_read_material", {"material_id": "unknown"})
                assert failure.is_error
                assert "AUTH_REQUIRED" in failure.content[0].text

    anyio.run(check)
