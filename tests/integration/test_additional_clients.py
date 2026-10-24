import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tum_mcp.clients import client_config_path, install_client
from tum_mcp.errors import CampusError
from tum_mcp.uninstall import uninstall_client


@pytest.mark.parametrize("name", ["cursor", "antigravity"])
def test_additional_client_setup_is_idempotent_and_preserves_other_entries(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "client profile"
    path = client_config_path(name, home)
    path.parent.mkdir(parents=True)
    original = {"customSetting": "München 漢字", "mcpServers": {"other": {"command": "keep"}}}
    path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    install_client(name, home)
    install_client(name, home)
    configured = json.loads(path.read_text(encoding="utf-8"))
    assert configured["customSetting"] == original["customSetting"]
    assert configured["mcpServers"]["other"] == {"command": "keep"}
    assert configured["mcpServers"]["tum"] == {
        "command": sys.executable,
        "args": ["-I", "-m", "tum_mcp", "serve"],
    }
    uninstall_client(name, home)
    assert json.loads(path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize("name", ["cursor", "antigravity"])
def test_additional_client_setup_preserves_a_conflicting_custom_entry(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    path = client_config_path(name, tmp_path)
    path.parent.mkdir(parents=True)
    before = json.dumps({"mcpServers": {"tum": {"command": "custom-private-launcher"}}})
    path.write_text(before, encoding="utf-8")
    with pytest.raises(CampusError, match="customized"):
        install_client(name, tmp_path)
    assert path.read_text(encoding="utf-8") == before


def test_antigravity_reuses_existing_legacy_config_without_creating_a_competing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    legacy = tmp_path / ".gemini/antigravity/mcp_config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"mcpServers": {}}')
    install_client("antigravity", tmp_path)
    assert "tum" in json.loads(legacy.read_text())["mcpServers"]
    assert not (tmp_path / ".gemini/config/mcp_config.json").exists()


@pytest.mark.parametrize("name", ["generic", "claude", "cursor", "antigravity"])
def test_setup_and_uninstall_preserve_invalid_configuration_with_a_clear_error(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    path = client_config_path(name, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"mcpServers": { invalid-json-to-preserve'
    path.write_bytes(original)
    with pytest.raises(CampusError, match="configuration is invalid"):
        install_client(name, tmp_path)
    with pytest.raises(CampusError, match="configuration is invalid"):
        uninstall_client(name, tmp_path)
    assert path.read_bytes() == original


def test_symbolic_client_configuration_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    path = client_config_path("cursor", tmp_path)
    path.parent.mkdir()
    original = tmp_path / "dotfiles.json"
    original.write_text('{"mcpServers":{}}')
    try:
        path.symlink_to(original)
    except OSError:
        pytest.skip("This profile cannot create symlinks.")
    with pytest.raises(CampusError, match="symbolic link"):
        install_client("cursor", tmp_path)
    with pytest.raises(CampusError, match="symbolic link"):
        uninstall_client("cursor", tmp_path)
    assert path.is_symlink() and original.read_text() == '{"mcpServers":{}}'


@pytest.mark.parametrize("name", ["cursor", "antigravity"])
def test_generated_client_command_starts_the_real_mcp_server(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    install_client(name, tmp_path)
    config = json.loads(client_config_path(name, tmp_path).read_text(encoding="utf-8"))
    entry = config["mcpServers"]["tum"]

    async def check() -> None:
        parameters = StdioServerParameters(**entry, env=dict(os.environ))
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert len(tools.tools) == 36
                assert {"moodle_list_courses", "zulip_search_messages"} <= {
                    tool.name for tool in tools.tools
                }
                status = await client.call_tool("tum_status")
                assert not status.is_error
                assert status.structured_content["accounts"] == []

    anyio.run(check)
