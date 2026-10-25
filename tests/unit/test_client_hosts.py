import json
import os
import sys
from pathlib import Path

import pytest

from tum_mcp import client_hosts
from tum_mcp.client_hosts import ClientHost, StdioLaunch
from tum_mcp.clients import client_config_path, install_client
from tum_mcp.errors import CampusError
from tum_mcp.moodle.browsers import BrowserSetupError
from tum_mcp.uninstall import uninstall_client


def test_windows_registration_requires_wsl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_hosts, "is_wsl", lambda: False)
    with pytest.raises(BrowserSetupError, match="WSL"):
        client_hosts.client_home(ClientHost.WINDOWS)
    with pytest.raises(BrowserSetupError, match="WSL"):
        client_hosts.client_launch(ClientHost.WINDOWS)


@pytest.mark.skipif(os.name == "nt", reason="WSL client builder runs in Linux.")
def test_windows_launch_pins_distro_user_runtime_and_shared_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(client_hosts, "is_wsl", lambda: True)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu fixture")
    for variable in ("TUM_MCP_DATA_DIR", "TUM_MCP_CONFIG_DIR", "TUM_MOODLE_DATA_DIR"):
        monkeypatch.setenv(variable, str(tmp_path / variable))
    launch = client_hosts.client_launch(ClientHost.WINDOWS)
    assert launch.command == "wsl.exe"
    assert launch.arguments[:2] == ("--distribution", "Ubuntu fixture")
    assert launch.arguments[-5:] == (sys.executable, "-I", "-m", "tum_mcp", "serve")
    assert f"TUM_MCP_DATA_DIR={tmp_path / 'TUM_MCP_DATA_DIR'}" in launch.arguments
    assert launch.arguments[4:6] == ("--exec", "/usr/bin/env")
    monkeypatch.delenv("WSL_DISTRO_NAME")
    with pytest.raises(BrowserSetupError, match="WSL_DISTRO_NAME"):
        client_hosts.client_launch(ClientHost.WINDOWS)


@pytest.mark.parametrize("name", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_windows_profile_registration_is_repeatable_and_conflict_safe(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tum_mcp import clients, uninstall

    profile = tmp_path / "Windows profile 漢字"
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    launch = StdioLaunch(
        "wsl.exe", ("--distribution", "Fixture", "--exec", "python", "-m", "tum_mcp", "serve")
    )
    monkeypatch.setattr(clients, "client_home", lambda host, home: profile)
    monkeypatch.setattr(clients, "client_launch", lambda host: launch)
    monkeypatch.setattr(uninstall, "client_home", lambda host, home: profile)
    monkeypatch.setattr(uninstall, "client_launch", lambda host: launch)
    path = client_config_path(name, profile, host=ClientHost.WINDOWS)
    if name != "codex":
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"custom": "München", "mcpServers": {"other": {"command": "keep"}}}),
            encoding="utf-8",
        )
    install_client(name, host=ClientHost.WINDOWS)
    before = path.read_bytes()
    install_client(name, host=ClientHost.WINDOWS)
    assert path.read_bytes() == before
    entry = json.loads(before)["mcpServers"]["tum"]
    assert entry["command"] == "wsl.exe" and entry["args"] == list(launch.arguments)
    if name == "codex":
        assert not (path.parent / "scripts").exists()
    else:
        changed = json.loads(before)
        changed["mcpServers"]["tum"]["command"] = "custom-launcher"
        path.write_text(json.dumps(changed))
        with pytest.raises(CampusError, match="preserve|customized|different|Customized|changed"):
            install_client(name, host=ClientHost.WINDOWS)
        path.write_bytes(before)
        uninstall_client(name, host=ClientHost.WINDOWS)
        remaining = json.loads(path.read_bytes())
        assert remaining["custom"] == "München"
        assert remaining["mcpServers"] == {"other": {"command": "keep"}}


def test_legacy_windows_registration_can_gain_download_path_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from tum_mcp.legacy_clients import legacy_installation

    # Given a real-shaped old runtime and the former three-path WSL entry.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    runtime = tmp_path / "data/runtimes" / ("a" * 64)
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"synthetic-not-executed")
    (runtime / ".tum-mcp-ready").write_text("a" * 64)
    old_args = [
        "--distribution",
        "Fixture",
        "--exec",
        "/usr/bin/env",
        "TUM_MCP_DATA_DIR=fixture",
        str(python),
        "-I",
        "-m",
        "tum_mcp",
        "serve",
    ]
    old = {"command": "wsl.exe", "args": old_args}
    new = {
        "command": "wsl.exe",
        "args": old_args[:-5]
        + ["TUM_MOODLE_DOWNLOAD_DIR=fixture-downloads"]
        + ["next-python", "-I", "-m", "tum_mcp", "serve"],
    }
    # When the unchanged legacy entry is recognized for migration.
    record = legacy_installation("cursor", ClientHost.WINDOWS, tmp_path, old, new)
    # Then its original managed entry is adopted for a safe update.
    assert record is not None and record.server == old
