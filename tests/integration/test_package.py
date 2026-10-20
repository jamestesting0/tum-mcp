import json
import os
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_installed_launcher_works_outside_the_checkout(tmp_path: Path) -> None:
    configured = os.environ.get("TUM_MOODLE_PACKAGED")
    if configured is None:
        pytest.skip("Set TUM_MOODLE_PACKAGED to the installed plugin launcher.")

    package_root = Path(configured).resolve().parents[1]
    server = json.loads((package_root / "mcp.json").read_text())["mcpServers"]["moodle"]
    command = server["command"]
    assert command == Path(command).name, "Portable plugin commands must use a bare executable name"
    arguments = [arg.replace("${PLUGIN_ROOT}", str(package_root)) for arg in server["args"]]

    async def check() -> None:
        params = StdioServerParameters(
            command=command,
            args=arguments,
            cwd=str(tmp_path),
            env={**os.environ, "TUM_MOODLE_DATA_DIR": str(tmp_path / "private")},
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert len(names) == 16
                assert {
                    "moodle_read_material",
                    "moodle_download_material",
                    "moodle_list_downloads",
                    "moodle_read_discussion",
                    "moodle_read_personal_record",
                } <= names
                result = await session.call_tool("moodle_auth_status")
                assert not result.is_error
                assert result.structured_content["state"] == "AUTH_REQUIRED"
                unknown = await session.call_tool("moodle_auth_status", {"unexpected": True})
                assert unknown.is_error
                cursor_error = await session.call_tool("moodle_list_downloads", {"cursor": "²"})
                assert cursor_error.is_error
                assert "Invalid pagination cursor" in cursor_error.content[0].text

    anyio.run(check)
