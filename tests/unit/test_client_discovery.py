import json
import os
from pathlib import Path
from shutil import which

import pytest
from typer.testing import CliRunner

from tum_mcp import client_discovery, diagnostics
from tum_mcp.cli import app
from tum_mcp.client_hosts import ClientHost
from tum_mcp.client_installs import ClientName
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.platforms import System
from tum_mcp.ui import State


@pytest.fixture
def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "data/config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(client_discovery, "system", lambda: System.MACOS)
    monkeypatch.setattr(client_discovery, "MAC_APPLICATIONS", tmp_path / "Applications")
    monkeypatch.setattr(client_discovery, "LINUX_APPLICATIONS", ())
    monkeypatch.setattr(client_discovery.shutil, "which", lambda name: None)
    monkeypatch.setattr(diagnostics, "discover_browsers", lambda: ())
    monkeypatch.setattr(diagnostics, "is_wsl", lambda: False)
    return home


@pytest.mark.parametrize("name", ["codex", "cursor", "antigravity"])
@pytest.mark.parametrize("user_install", [False, True])
def test_mac_app_bundles_identify_clients_without_cli_commands(
    profile: Path, name: ClientName, user_install: bool
) -> None:
    root = profile / "Applications" if user_install else client_discovery.MAC_APPLICATIONS
    (root / f"{name.title()}.app").mkdir(parents=True)
    assert client_discovery.client_installed(name, profile, ClientHost.LOCAL)


def test_claude_desktop_is_not_mistaken_for_claude_code(profile: Path) -> None:
    (profile / "Applications/Claude.app").mkdir(parents=True)
    assert not client_discovery.client_installed("claude", profile, ClientHost.LOCAL)


def test_leftover_configuration_is_not_an_installed_client(profile: Path) -> None:
    path = profile / ".gemini/config/mcp_config.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"mcpServers":{"unrelated":{"command":"example"}}}', encoding="utf-8")
    report = diagnostics.collect_diagnostics(home=profile)
    assert report.clients == ()
    assert json.loads(path.read_text())["mcpServers"]["unrelated"]["command"] == "example"


def test_no_clients_or_state_are_created_by_doctor(profile: Path, tmp_path: Path) -> None:
    report = diagnostics.collect_diagnostics(home=profile)
    assert report.clients == ()
    assert not profile.exists() and not (tmp_path / "data").exists()


def test_setup_still_offers_generic_when_no_supported_apps_are_installed(profile: Path) -> None:
    checks = diagnostics.available_client_checks(home=profile, include_generic=True)
    assert [(name, check.state) for name, check in checks] == [("generic", State.UNCONFIGURED)]


def test_configured_client_is_shown_even_without_installation_evidence(profile: Path) -> None:
    config = profile / ".cursor/mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"mcpServers":{"tum":{"command":"custom-launcher"}}}', encoding="utf-8")
    report = diagnostics.collect_diagnostics(home=profile)
    assert [(check.label, check.state) for check in report.clients] == [
        ("Cursor", State.CONFIGURED)
    ]


@pytest.mark.parametrize("host", [ClientHost.LOCAL, ClientHost.WINDOWS])
def test_native_and_wsl_windows_discover_gui_installations(
    profile: Path, host: ClientHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        client_discovery,
        "system",
        lambda: System.WINDOWS if host == ClientHost.LOCAL else System.LINUX,
    )
    binary = profile / "AppData/Local/Programs/Antigravity/Antigravity.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic installation marker")
    assert client_discovery.client_installed("antigravity", profile, host)


def test_windows_host_does_not_use_a_linux_cli_as_installation_evidence(
    profile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_discovery, "system", lambda: System.LINUX)
    monkeypatch.setattr(
        client_discovery.shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None
    )
    assert client_discovery.client_installed("codex", profile, ClientHost.LOCAL)
    assert not client_discovery.client_installed("codex", profile, ClientHost.WINDOWS)


def test_cli_installations_on_path_are_detected(
    profile: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    binary.parent.mkdir()
    binary.write_bytes(b"synthetic installation marker")
    binary.chmod(0o700)
    monkeypatch.setattr(client_discovery.shutil, "which", which)
    monkeypatch.setenv("PATH", str(binary.parent))
    assert which("claude") is not None
    assert client_discovery.client_installed("claude", profile, ClientHost.LOCAL)


def test_doctor_contains_extensions_without_duplicating_runtime_entries(
    profile: Path, tmp_path: Path
) -> None:
    config = tmp_path / "data/config"
    config.mkdir(parents=True)
    (config / "extensions.json").write_text(
        '{"schema_version":1,"audio_notes":true}', encoding="utf-8"
    )
    result = CliRunner().invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    states = {check["label"]: check["state"] for check in report["extensions"]}
    assert states == {
        "Lecture": "Disabled",
        "Audio Notes": "Enabled",
        "Video Notes": "Disabled",
        "Course Memory": "Disabled",
    }
    assert all(check["label"] != "Audio Notes" for check in report["runtime"])


@pytest.mark.parametrize("name", ["login", "connect"])
def test_login_and_its_compatibility_alias_use_the_same_safe_terminal_boundary(
    profile: Path, name: str
) -> None:
    result = CliRunner().invoke(app, [name])
    assert isinstance(result.exception, CampusError)
    assert result.exception.code == Code.ACTION_REQUIRED


def test_public_help_lists_one_diagnostic_and_login_command(profile: Path) -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    commands = {line.split()[0] for line in result.output.splitlines() if line.strip()}
    assert {"doctor", "login", "logout"} <= commands
    assert not {"connect", "status"} & commands


def test_status_alias_preserves_script_output_and_uses_doctor_for_people(profile: Path) -> None:
    runner = CliRunner()
    legacy = runner.invoke(app, ["status", "--json"])
    assert legacy.exit_code == 0
    assert json.loads(legacy.output)["extensions"] == {
        "lecture": False,
        "audio-notes": False,
        "video-notes": False,
        "course-memory": False,
    }
    human = runner.invoke(app, ["status"])
    assert human.exit_code == 0, human.output
    assert human.output == runner.invoke(app, ["doctor"]).output
