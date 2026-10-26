import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_enabled_tools_and_runtime_removal(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    selection = config / "extensions.json"
    selection.write_text('{"schema_version":1,"studocu":true}')

    async def check() -> None:
        params = StdioServerParameters(
            command=os.environ.get("TUM_MCP_TEST_PYTHON", sys.executable),
            args=["-I", "-m", "tum_mcp", "serve"],
            env={
                **os.environ,
                "TUM_MCP_DATA_DIR": str(tmp_path / "data"),
                "TUM_MCP_CONFIG_DIR": str(config),
                "TUM_MOODLE_DATA_DIR": str(tmp_path / "moodle"),
            },
        )
        async with (
            stdio_client(params) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()
            registered = (await client.list_tools()).tools
            names = {tool.name for tool in registered}
            assert {
                "studocu_get_access",
                "studocu_search_courses",
                "studocu_search_materials",
                "studocu_get_document",
                "studocu_download_document",
                "studocu_import_document",
                "tumonline_status",
                "tumonline_list_courses",
                "tumonline_list_studies",
                "tumonline_course_curriculum",
            } <= names
            for tool in registered:
                if tool.name in {
                    "studocu_get_document",
                    "studocu_download_document",
                    "studocu_import_document",
                }:
                    assert tool.input_schema["properties"]["document_id"]["type"] == "integer"
            access = await client.call_tool("studocu_get_access", {})
            assert not access.is_error
            assert access.structured_content["remote_original_file"] == "unavailable"
            selection.write_text('{"schema_version":1,"studocu":false}')
            denied = await client.call_tool("studocu_get_access", {})
            assert denied.is_error
            assert not (await client.call_tool("tum_status", {})).is_error

    anyio.run(check)


@pytest.mark.parametrize("selection", [None, '{"schema_version":1,"studocu":"yes"}', "invalid"])
def test_disabled_or_malformed_optional_state_preserves_campus_server(
    tmp_path: Path, selection: str | None
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    if selection is not None:
        (config / "extensions.json").write_text(selection)

    async def check() -> None:
        params = StdioServerParameters(
            command=os.environ.get("TUM_MCP_TEST_PYTHON", sys.executable),
            args=["-I", "-m", "tum_mcp", "serve"],
            env={
                **os.environ,
                "TUM_MCP_DATA_DIR": str(tmp_path / "data"),
                "TUM_MCP_CONFIG_DIR": str(config),
                "TUM_MOODLE_DATA_DIR": str(tmp_path / "moodle"),
            },
        )
        async with (
            stdio_client(params) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert "moodle_list_courses" in names
            assert "tumonline_status" in names
            assert not any(name.startswith("studocu_") for name in names)

    anyio.run(check)
