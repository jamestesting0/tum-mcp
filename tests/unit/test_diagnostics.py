import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app, main
from tum_mcp.connect import ServiceChoice
from tum_mcp.credentials import Credential, Vault
from tum_mcp.diagnostics import collect_diagnostics
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle import auth
from tum_mcp.settings import Account, Provider, save_account
from tum_mcp.ui import State


@pytest.fixture(params=tuple(ServiceChoice))
def saved_service(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lecture_extension: Path,
) -> tuple[ServiceChoice, Path, Path]:
    """Save synthetic sessions and replace only the remote identity probes."""
    from tum_mcp.moodle.config import Paths
    from tum_mcp.settings import TUM_LIVE, data_path
    from tum_mcp.tumonline.policy import PolicyStore

    service = ServiceChoice(request.param)
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr("tum_mcp.diagnostics.time.time", lambda: 100_000)
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No Keychain access"))
    for method in (
        "tum_mcp.moodle.http_client.MoodleHTTP.get",
        "tum_mcp.artemis.Artemis.identity",
        "tum_mcp.zulip.Zulip.identity",
        "tum_mcp.tum_live.TumLive.identity",
        "tum_mcp.tumonline.study_service.StudyService.verify",
    ):
        monkeypatch.setattr(method, lambda *args, **kwargs: None)
    if service == ServiceChoice.MOODLE:
        store = auth.SessionStore(Paths(tmp_path / "moodle"), storage="file")
        store.save(auth.Session(generation=store.begin_login(), cookies=[], verified_at=0))
        return service, store.file("session.enc"), store.file("session.key")
    if service == ServiceChoice.TUMONLINE:
        from tum_mcp.tumonline.identity import AccountRef

        owner = AccountRef(account_id="a" * 64)
        PolicyStore().create(owner.id)
    else:
        owner = Account(
            provider=Provider(service.value),
            origin=TUM_LIVE if service == ServiceChoice.TUM_LIVE else "https://example.invalid",
            principal="synthetic",
        )
        save_account(owner)
    Vault().save(owner, Credential(account_id=owner.id, authentication="browser_session"))
    root = data_path() / "credentials/local"
    return service, root / f"{owner.id}.enc", root / "session.key"


def test_live_result_survives_in_doctor_json_and_login_selector_without_remote_calls(
    saved_service: tuple[ServiceChoice, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a service freshly checked through the CLI.
    from tum_mcp import ui

    service, session, _ = saved_service
    runner = CliRunner()
    live = runner.invoke(app, ["doctor", "--live", "--json"])
    assert live.exit_code == 0, live.output
    record = json.loads(session.with_suffix(".verification.json").read_bytes())
    assert record["checked_at"] == 100_000 and record["succeeded"]
    monkeypatch.setattr(Vault, "load", lambda *args: pytest.fail("No credential decryption"))
    for method in (
        "tum_mcp.moodle.http_client.MoodleHTTP.get",
        "tum_mcp.artemis.Artemis.identity",
        "tum_mcp.zulip.Zulip.identity",
        "tum_mcp.tum_live.TumLive.identity",
        "tum_mcp.tumonline.study_service.StudyService.verify",
    ):
        monkeypatch.setattr(method, lambda *args, **kwargs: pytest.fail("No remote checks"))
    choices = []

    def select(title, rows):
        choices.extend(rows)
        return None

    monkeypatch.setattr(ui, "select_many", select)
    # When independent doctor and login status readers run without --live.
    local = runner.invoke(app, ["doctor", "--json"])
    ui.select_services()
    # Then both retain the verified service status.
    assert local.exit_code == 0, local.output
    checked = next(s for s in json.loads(local.output)["services"] if s["label"] == service.label)
    assert checked["state"] == State.READY
    assert next(row[2] for row in choices if row[0] == service) == State.READY


@pytest.mark.parametrize("age", [43_199, 43_200, 43_201, -1])
def test_saved_live_verification_expires_at_twelve_hours(
    saved_service: tuple[ServiceChoice, Path, Path], monkeypatch: pytest.MonkeyPatch, age: int
) -> None:
    # Given a successful check at a fixed time.
    from tum_mcp.diagnostics import collect_services

    service, _, _ = saved_service
    collect_services(live=True)
    monkeypatch.setattr("tum_mcp.diagnostics.time.time", lambda: 100_000 + age)
    # When local status reads the result at the expiry boundary.
    result = next(s for s in collect_services().services if s.label == service.label)
    # Then an expired (or future-dated) result is unverified, not disconnected.
    assert result.state == (State.READY if 0 <= age < 43_200 else State.CONFIGURED)


def test_failed_live_check_replaces_saved_success(
    saved_service: tuple[ServiceChoice, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an earlier successful check and a newly rejected remote identity.
    from tum_mcp.diagnostics import collect_services

    service, session, _ = saved_service
    collect_services(live=True)

    def rejected(*args, **kwargs):
        raise CampusError(Code.AUTH_REQUIRED, "synthetic rejection")

    for method in (
        "tum_mcp.moodle.http_client.MoodleHTTP.get",
        "tum_mcp.artemis.Artemis.identity",
        "tum_mcp.zulip.Zulip.identity",
        "tum_mcp.tum_live.TumLive.identity",
        "tum_mcp.tumonline.study_service.StudyService.verify",
    ):
        monkeypatch.setattr(method, rejected)
    # When a fresh live check fails.
    collect_services(live=True)
    # Then subsequent local status cannot reuse the old success or persist response text.
    result = next(s for s in collect_services().services if s.label == service.label)
    assert result.state == State.ACTION
    assert b"synthetic rejection" not in session.with_suffix(".verification.json").read_bytes()


@pytest.mark.parametrize("change", ["login", "key", "logout"])
def test_session_changes_invalidate_saved_live_verification(
    saved_service: tuple[ServiceChoice, Path, Path], change: str
) -> None:
    # Given a successful result for the original session.
    from tum_mcp.diagnostics import collect_services
    from tum_mcp.moodle.config import Paths, private_write
    from tum_mcp.tumonline.identity import AccountRef

    service, session, key = saved_service
    collect_services(live=True)
    # When credentials are replaced or removed.
    if change == "key":
        private_write(key, b"replacement")
    elif service == ServiceChoice.MOODLE:
        store = auth.SessionStore(Paths(session.parent.parent), storage="file")
        if change == "logout":
            store.logout()
        else:
            store.save(auth.Session(generation=store.begin_login(), cookies=[], verified_at=0))
    else:
        owner = AccountRef(account_id=session.stem)
        if change == "logout":
            Vault().logout(owner)
        else:
            Vault().replace_login(owner, Credential(account_id=owner.id))
    # Then local status no longer claims verification of the old credentials.
    result = next(s for s in collect_services().services if s.label == service.label)
    assert result.state != State.READY
    if change != "logout":
        assert result.state == State.CONFIGURED


def test_cookie_refresh_preserves_live_verification(
    saved_service: tuple[ServiceChoice, Path, Path],
) -> None:
    # Given verification of the current login.
    from tum_mcp.diagnostics import collect_services
    from tum_mcp.moodle.config import Paths
    from tum_mcp.tumonline.identity import AccountRef

    service, session, _ = saved_service
    collect_services(live=True)
    # When ordinary reads save rotated cookies without replacing the login.
    cookies = (auth.Cookie(name="synthetic", value="rotated", domain="example.invalid"),)
    if service == ServiceChoice.MOODLE:
        store = auth.SessionStore(Paths(session.parent.parent), storage="file")
        store.save(store.load().model_copy(update={"cookies": list(cookies)}))
    else:
        Vault().refresh_browser_session(
            AccountRef(account_id=session.stem), lambda credential, checkpoint: (cookies, None)
        )
    # Then the recently verified identity remains ready.
    result = next(s for s in collect_services().services if s.label == service.label)
    assert result.state == State.READY


def test_corrupt_verification_record_does_not_hide_saved_session(
    saved_service: tuple[ServiceChoice, Path, Path],
) -> None:
    # Given an unreadable verification record beside valid credentials.
    from tum_mcp.diagnostics import collect_services

    service, session, _ = saved_service
    record = session.with_suffix(".verification.json")
    record.write_bytes(b"invalid json")
    # When local status reads the session.
    result = next(s for s in collect_services().services if s.label == service.label)
    # Then it reports unverified without overwriting the damaged record.
    assert result.state == State.CONFIGURED
    assert record.read_bytes() == b"invalid json"


@pytest.fixture(autouse=True)
def no_live_github_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default diagnostics tests must never use the developer's GitHub account."""
    original = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "gh" else original(name))


def test_doctor_reports_optional_github_without_running_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an installed CLI, with subprocess execution forbidden.
    from tum_mcp.diagnostics import github_check

    monkeypatch.setattr(shutil, "which", lambda name: "/synthetic/gh")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("Local doctor must not authenticate")
    )
    # When default diagnostics inspect the optional publisher.
    result = github_check(live=False)
    # Then availability is configured, without claiming verified authentication.
    assert result.state == State.CONFIGURED and result.location == "/synthetic/gh"


@pytest.mark.parametrize("authenticated", [True, False])
def test_live_doctor_checks_github_without_exposing_cli_errors(
    monkeypatch: pytest.MonkeyPatch,
    authenticated: bool,
) -> None:
    # Given a synthetic GitHub identity endpoint, including a secret-bearing failure.
    from tum_mcp.diagnostics import github_check

    monkeypatch.setattr(shutil, "which", lambda name: "/synthetic/gh")
    calls: list[list[str]] = []

    def run(arguments: list[str], **kwargs: str) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments)
        return subprocess.CompletedProcess(
            arguments,
            0 if authenticated else 1,
            b'{"login":"synthetic-student"}',
            b"synthetic-secret (HTTP 401)",
        )

    monkeypatch.setattr(subprocess, "run", run)
    # When live authentication is explicitly requested.
    result = github_check(live=True)
    # Then only the account identity is checked and no credentials appear in output.
    assert result.state == (State.READY if authenticated else State.ACTION)
    assert len(calls) == 1 and calls[0][-1] == "user"
    assert "synthetic-secret" not in result.model_dump_json()


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
    assert {item.label for item in report.services} == {"Moodle", "Artemis", "Zulip", "TUMonline"}
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
    result = CliRunner().invoke(app, ["login"])
    assert result.exit_code != 0
    assert "interactive terminal" in str(result.exception)


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("provider", [Provider.ARTEMIS, Provider.ZULIP])
def test_live_doctor_verifies_identity_without_reading_course_content(
    expired: bool, provider: Provider, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    account = Account(
        provider=provider, origin=f"https://{provider.value}.example.invalid", principal="7"
    )
    save_account(account)
    Vault().save(account, Credential(account_id=account.id))
    calls = []

    def identity(self: object) -> None:
        calls.append("identity")
        if expired:
            raise CampusError(Code.AUTH_REQUIRED, "Reconnect this account.")

    identity_method = (
        "tum_mcp.artemis.Artemis.identity"
        if provider == Provider.ARTEMIS
        else "tum_mcp.zulip.Zulip.identity"
    )
    monkeypatch.setattr(identity_method, identity)
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No native-store reads"))
    local = collect_diagnostics(home=tmp_path)
    assert calls == []
    assert (
        next(item for item in local.services if item.label == provider.value.title()).state
        == State.CONFIGURED
    )
    live = collect_diagnostics(live=True, home=tmp_path)
    checked = next(item for item in live.services if item.label == provider.value.title())
    assert checked.state == (State.ACTION if expired else State.READY)
    assert calls == ["identity"]
    cached = collect_diagnostics(home=tmp_path)
    assert (
        next(item for item in cached.services if item.label == provider.value.title()).state
        == checked.state
    )
    assert calls == ["identity"]


def test_doctor_reports_invalid_client_entries_without_overwriting_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    target = tmp_path / ".cursor/mcp.json"
    target.parent.mkdir()
    original = '{"mcpServers":{"tum":42}}'
    target.write_text(original, encoding="utf-8")
    result = collect_diagnostics(home=tmp_path)
    assert next(item for item in result.clients if item.label == "Cursor").state == State.FAILED
    assert target.read_text(encoding="utf-8") == original


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
        context.setattr("tum_mcp.cli.app", lambda **kwargs: print("München 漢字"))
        main()
        output.flush()
        assert buffer.getvalue().decode("utf-8").strip() == "München 漢字"


def test_doctor_survives_an_incomplete_custom_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "campus"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    (tmp_path / "campus/config/skills/read-content").mkdir(parents=True)
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
        "tum_mcp.moodle.browsers.discover_browsers", lambda: pytest.fail("No browser discovery")
    )
    result = CliRunner().invoke(app, ["login", *arguments])
    assert result.exit_code == 2


def test_all_campus_authentication_tools_direct_users_to_the_same_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tum_mcp.moodle.server import moodle_login
    from tum_mcp.server import tum_connect

    monkeypatch.setenv("TUM_MOODLE_SESSION_STORAGE", "file")
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No native store"))
    monkeypatch.setattr(
        "tum_mcp.moodle.server.subprocess.Popen",
        lambda *args, **kwargs: pytest.fail("No background browser"),
    )
    assert "tum-mcp login" in tum_connect()
    result = moodle_login()
    assert result["command"] == "tum-mcp login" and result["state"] == "ACTION_REQUIRED"


def test_wsl_doctor_reports_both_client_profiles_without_creating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import client_discovery, diagnostics
    from tum_mcp.moodle.platforms import System

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(diagnostics, "is_wsl", lambda: True)
    windows = tmp_path / "Windows user"
    monkeypatch.setattr(diagnostics, "client_home", lambda host: windows)
    monkeypatch.setattr(diagnostics, "discover_browsers", lambda: ())
    monkeypatch.setattr(client_discovery, "system", lambda: System.LINUX)
    monkeypatch.setattr(client_discovery.shutil, "which", lambda name: None)
    monkeypatch.setattr(client_discovery, "LINUX_APPLICATIONS", ())
    launcher = tmp_path / "Linux user/.local/share/applications/cursor.desktop"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("[Desktop Entry]\nName=Cursor\n", encoding="utf-8")
    binary = windows / ".local/bin/claude.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic installation marker")
    target = windows / ".cursor/mcp.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"mcpServers":{"tum":{"command":"wsl.exe","args":[]}}}', encoding="utf-8")
    report = diagnostics.collect_diagnostics(home=tmp_path / "Linux user")
    clients = {item.label: item for item in report.clients}
    assert clients["Cursor (Windows)"].state == State.CONFIGURED
    assert clients["Cursor"].state == State.UNCONFIGURED
    assert "--host windows" in clients["Claude (Windows)"].detail
    assert not (tmp_path / "data").exists()
