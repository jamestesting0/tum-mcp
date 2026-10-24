import io
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app, main
from tum_mcp.credentials import Credential, Vault
from tum_mcp.diagnostics import collect_diagnostics
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Account, Provider, save_account
from tum_mcp.ui import State
from tum_moodle import auth


def test_doctor_is_local_only_and_does_not_create_state_or_access_keychain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "missing data"
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(data))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(data / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(
        auth, "system_keyring", lambda: pytest.fail("doctor must not access Keychain")
    )
    report = collect_diagnostics(home=tmp_path / "profile")
    assert report.live_authentication == "not_checked"
    assert {item.label for item in report.services} == {"Moodle", "Artemis", "Zulip"}
    assert not any(item.state == State.READY for item in report.services)
    assert not data.exists()
    assert not (tmp_path / "moodle").exists()
    assert report.remote_actions == "disabled"


def test_doctor_json_contains_no_ansi_and_does_not_claim_saved_sessions_are_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    result = CliRunner().invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    assert '"schema_version": 1' in result.output
    assert '"live_authentication": "not_checked"' in result.output
    assert "\x1b[" not in result.output


def test_connect_in_a_pipe_returns_an_actionable_error_without_opening_chrome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tum_mcp.connect.connect_services", lambda *a, **k: pytest.fail("no browser")
    )
    result = CliRunner().invoke(app, ["connect"])
    assert result.exit_code != 0
    assert "interactive terminal" in str(result.exception)


@pytest.mark.parametrize("expired", [False, True])
def test_live_doctor_verifies_identity_without_reading_course_content(
    expired: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    account = Account(
        provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7", courses=(1,)
    )
    save_account(account)
    Vault().save(account, Credential(account_id=account.id))
    calls = []

    def identity(self: object) -> None:
        calls.append("identity")
        if expired:
            raise CampusError(Code.AUTH_REQUIRED, "Reconnect this account.")

    monkeypatch.setattr("tum_mcp.artemis.Artemis.identity", identity)
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No native-store reads"))
    local = collect_diagnostics(home=tmp_path)
    assert calls == []
    assert (
        next(item for item in local.services if item.label == "Artemis").state == State.CONFIGURED
    )
    live = collect_diagnostics(live=True, home=tmp_path)
    checked = next(item for item in live.services if item.label == "Artemis")
    assert checked.state == (State.ACTION if expired else State.READY)
    assert calls == ["identity"]


def test_doctor_reports_invalid_client_entries_without_overwriting_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    target = tmp_path / ".cursor/mcp.json"
    target.parent.mkdir()
    original = '{"mcpServers":{"tum":42}}'
    target.write_text(original)
    result = collect_diagnostics(home=tmp_path)
    assert next(item for item in result.clients if item.label == "Cursor").state == State.FAILED
    assert target.read_text() == original


def test_windows_cli_uses_utf8_even_when_redirected_from_a_legacy_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = io.BytesIO()
    output = io.TextIOWrapper(buffer, encoding="cp1252")
    errors = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    with monkeypatch.context() as context:
        context.setattr(sys, "platform", "win32")
        context.setattr(sys, "stdout", output)
        context.setattr(sys, "stderr", errors)
        context.setattr("tum_mcp.cli.app", lambda: print("München 漢字"))
        main()
        output.flush()
        assert buffer.getvalue().decode("utf-8").strip() == "München 漢字"


def test_doctor_survives_an_incomplete_custom_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    (tmp_path / "campus/config/skills/tum-zulip-research").mkdir(parents=True)
    report = collect_diagnostics(home=tmp_path)
    assert (
        next(item for item in report.runtime if item.label == "Workflow skills").state
        == State.FAILED
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["artemis"],
        ["zulip"],
        ["campus"],
        ["moodle"],
        ["--service", "zulip"],
        ["--auth", "api-key"],
    ],
)
def test_connect_rejects_all_legacy_selection_arguments_before_opening_a_browser(
    arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tum_moodle.browsers.discover_browsers", lambda: pytest.fail("No browser discovery")
    )
    result = CliRunner().invoke(app, ["connect", *arguments])
    assert result.exit_code == 2


def test_all_campus_authentication_tools_direct_users_to_the_same_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tum_mcp.server import tum_connect
    from tum_moodle.server import moodle_login

    monkeypatch.setenv("TUM_MOODLE_SESSION_STORAGE", "file")
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No native store"))
    monkeypatch.setattr(
        "tum_moodle.server.subprocess.Popen",
        lambda *args, **kwargs: pytest.fail("No background browser"),
    )
    assert "tum-mcp connect" in tum_connect()
    result = moodle_login()
    assert result["command"] == "tum-mcp connect" and result["state"] == "ACTION_REQUIRED"


def test_wsl_doctor_reports_both_client_profiles_without_creating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import diagnostics

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(diagnostics, "is_wsl", lambda: True)
    windows = tmp_path / "Windows user"
    monkeypatch.setattr(diagnostics, "client_home", lambda host: windows)
    monkeypatch.setattr(diagnostics, "discover_browsers", lambda: ())
    target = windows / ".cursor/mcp.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"mcpServers":{"tum":{"command":"wsl.exe","args":[]}}}')
    report = diagnostics.collect_diagnostics(home=tmp_path / "Linux user")
    clients = {item.label: item for item in report.clients}
    assert clients["Cursor (Windows)"].state == State.CONFIGURED
    assert clients["Cursor"].state == State.UNCONFIGURED
    assert "--host windows" in clients["Claude (Windows)"].detail
    assert not (tmp_path / "data").exists()
