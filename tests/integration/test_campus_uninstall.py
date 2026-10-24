import json
from pathlib import Path

import pytest

from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError
from tum_mcp.settings import config_dir
from tum_mcp.uninstall import uninstall_client


def test_claude_uninstall_preserves_unrelated_user_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a synthetic profile containing this integration and unrelated settings.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    home.mkdir()
    config = home / ".claude.json"
    config.write_text(
        json.dumps({"customSetting": 42, "mcpServers": {"other": {"command": "keep"}}})
    )
    install_client("claude", home)
    # When the integration is removed twice.
    uninstall_client("claude", home)
    uninstall_client("claude", home)
    # Then only its managed registration/skills disappear and the profile remains intact.
    assert json.loads(config.read_text()) == {
        "customSetting": 42,
        "mcpServers": {"other": {"command": "keep"}},
    }
    assert not (home / ".claude/skills/tum-artemis").exists()


def test_generic_setup_and_uninstall_preserve_unrelated_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    target = config_dir() / "mcp.json"
    original = {"extra": 42, "mcpServers": {"other": {"command": "keep"}}}
    target.write_text(json.dumps(original))
    install_client("generic")
    assert json.loads(target.read_text())["mcpServers"]["other"] == {"command": "keep"}
    uninstall_client("generic")
    assert json.loads(target.read_text()) == original
    customized = {"mcpServers": {"tum": {"command": "custom"}}}
    target.write_text(json.dumps(customized))
    with pytest.raises(CampusError, match="customized"):
        install_client("generic")
    with pytest.raises(CampusError, match="customized"):
        uninstall_client("generic")
    assert json.loads(target.read_text()) == customized
