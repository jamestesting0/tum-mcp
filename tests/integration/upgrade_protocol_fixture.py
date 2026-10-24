# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run via: npm run test:upgrade (supplies the installed private interpreter).
"""Real MCP startup after a registry-version upgrade, using synthetic empty accounts."""

import os
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tum_mcp.client_config import client_config_path, read_client_config


async def check() -> None:
    entry = read_client_config(client_config_path("claude", Path.home())).mcpServers["tum"]
    parameters = StdioServerParameters(**(entry | {"env": {**os.environ, **entry.get("env", {})}}))
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        inventory = await client.list_tools()
        assert len(inventory.tools) == 36
        assert not {"artemis_submit", "artemis_start_exercise"} & {
            tool.name for tool in inventory.tools
        }
        status = await client.call_tool("tum_status")
        assert not status.is_error and status.structured_content["accounts"] == []


anyio.run(check)
