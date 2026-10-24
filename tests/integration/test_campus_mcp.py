import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_campus_stdio_has_real_tools_and_rejects_fabricated_approval(tmp_path: Path) -> None:
    # Given a fresh campus server with no account grants.
    async def check() -> None:
        params = StdioServerParameters(
            command=os.environ.get("TUM_MCP_TEST_PYTHON", sys.executable),
            args=["-I", "-m", "tum_mcp", "serve"],
            env={
                **os.environ,
                "TUM_MCP_DATA_DIR": str(tmp_path / "data"),
                "TUM_MCP_CONFIG_DIR": str(tmp_path / "config"),
                "TUM_MOODLE_DATA_DIR": str(tmp_path / "moodle"),
            },
        )
        async with (
            stdio_client(params) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()
            # When the actual MCP protocol lists tools and receives an attempted bypass.
            listing = await client.list_tools()
            status = await client.call_tool("tum_status")
            rejected = await client.call_tool(
                "artemis_prepare_submission", {"workspace": str(tmp_path), "approved": True}
            )
            denied = await client.call_tool(
                "zulip_search_messages", {"account_id": "missing", "search": {"channel_id": 42}}
            )
            # Then legacy compatibility and backend policy hold without any skill being loaded.
            names = {tool.name for tool in listing.tools}
            assert {
                "moodle_read_material",
                "moodle_list_courses",
                "zulip_search_messages",
                "artemis_get_feedback",
                "artemis_prepare_workspace",
                "tum_run_tests",
            } <= names
            assert "artemis_submit" not in names
            assert "artemis_start_exercise" not in names
            assert not status.is_error
            assert status.structured_content["accounts"] == []
            assert rejected.is_error
            assert denied.is_error
            assert "AUTH_REQUIRED" in denied.content[0].text

    anyio.run(check)
