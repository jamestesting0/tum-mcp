import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tum_mcp.ui import State

pytestmark = pytest.mark.skipif(os.name == "nt", reason="PTY keyboard QA uses POSIX terminal APIs.")


def run_selector(
    tmp_path: Path,
    keys: bytes,
    *,
    terminal: str = "xterm-256color",
    no_color: bool = False,
    browser_keys: bytes | None = None,
    columns: int = 80,
    checks: tuple[tuple[str, State], ...] = (),
    command: str = "login",
) -> tuple[int, str]:
    import pty

    driver = tmp_path / "driver.py"
    driver.write_text(
        "import sys\n"
        "from tum_mcp import connect\n"
        "from tum_mcp import diagnostics\n"
        "from tum_mcp.diagnostics import Check, ServiceReport\n"
        "from tum_mcp.connect import ConnectionResult\n"
        + (
            "diagnostics.collect_services=lambda **kwargs:ServiceReport(services=tuple("
            "Check(label=label,state=state,detail='synthetic') for label,state in "
            f"{tuple((label, state.value) for label, state in checks)!r}"
            "),issues=(),needs_connection=True)\n"
            if checks
            else ""
        )
        + "import tum_mcp.moodle.browsers as browsers\n"
        "browsers.discover_browsers=lambda:(browsers.BrowserChoice('First browser','first'),"
        + ("browsers.BrowserChoice('Second browser','second')," if browser_keys else "")
        + ")\n"
        "def connected(services,on_connected=None,browser=None):\n"
        " print('SELECTED='+','.join(service.value for service in services))\n"
        " print('BROWSER='+browser.executable)\n"
        " results=tuple(ConnectionResult(service) for service in services)\n"
        " for result in results:\n"
        "  if on_connected: on_connected(result)\n"
        " return results\n"
        "connect.connect_services=connected\n"
        f"sys.argv=['tum-mcp',{command!r}]\n"
        "from tum_mcp.cli import main\nmain()\n",
        encoding="utf-8",
    )
    master, slave = pty.openpty()
    env = {**os.environ, "TERM": terminal, "COLUMNS": str(columns), "LINES": "30"}
    if no_color:
        env["NO_COLOR"] = ""
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, str(driver)], stdin=slave, stdout=slave, stderr=slave, env=env
    )
    os.close(slave)
    captured = bytearray()
    sent = False
    browser_sent = False
    cancel_started: float | None = None
    cancel_elapsed: float | None = None
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                captured.extend(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
                plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", bytes(captured))
                if cancel_started is not None and cancel_elapsed is None and b"Cancelled" in plain:
                    cancel_elapsed = time.monotonic() - cancel_started
                ready = (
                    b"Selection" in plain and b": " in plain
                    if terminal == "dumb"
                    else (b"Choose connections" if command == "logout" else b"TUMonline") in plain
                    and b"\x1b[?25l" in captured
                )
                if not sent and ready:
                    if keys == b"\x1b":
                        cancel_started = time.monotonic()
                    os.write(master, keys)
                    sent = True
                elif (
                    sent
                    and not browser_sent
                    and browser_keys
                    and (b"Browser number:" if terminal == "dumb" else b"Browser") in plain
                ):
                    if browser_keys == b"\x1b":
                        cancel_started = time.monotonic()
                    os.write(master, browser_keys)
                    browser_sent = True
            if process.poll() is not None:
                break
        else:
            pytest.fail("Service selector did not complete within its terminal QA budget.")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        os.close(master)
    output = bytes(captured).decode("utf-8", errors="replace")
    if cancel_started is not None:
        assert cancel_elapsed is not None and cancel_elapsed < 0.4, (
            f"Escape cancellation took {cancel_elapsed!r} seconds.\n{output}"
        )
    if destination := os.environ.get("TUM_MCP_TERMINAL_QA"):
        Path(destination).mkdir(parents=True, exist_ok=True)
        (Path(destination) / f"selector-{terminal}-{columns}-{keys.hex()}.ansi").write_text(
            output, encoding="utf-8"
        )
    return process.returncode, output


def test_real_terminal_selection_connects_only_the_checked_services(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b" \x1b[B\x1b[B \r")
    assert code == 0, output
    assert "SELECTED=moodle,zulip" in output
    assert "SELECTED=moodle,artemis,zulip" not in output


@pytest.mark.parametrize("keys", [b"\x03", b"\x1b"])
@pytest.mark.parametrize("terminal", ["xterm-256color", "dumb"])
def test_real_terminal_cancellation_restores_cursor_and_never_connects(
    tmp_path: Path, keys: bytes, terminal: str
) -> None:
    code, output = run_selector(tmp_path, keys, terminal=terminal)
    assert code == 130, output
    assert "SELECTED=" not in output
    assert "Cancelled" in output
    if terminal != "dumb":
        assert "\x1b[?25h" in output


def test_dumb_terminal_uses_a_numbered_prompt(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b"1,3\n", terminal="dumb")
    assert code == 0, output
    assert "SELECTED=moodle,zulip" in output
    assert "\x1b[" not in output


def test_dumb_terminal_selects_both_campus_services_when_lecture_enabled(
    tmp_path: Path, lecture_extension: Path
) -> None:
    code, output = run_selector(tmp_path, b"4,5\n", terminal="dumb")
    assert code == 0, output
    assert "SELECTED=tumonline,tum_live" in output


def test_narrow_terminal_selects_tumonline_when_lecture_enabled(
    tmp_path: Path, lecture_extension: Path
) -> None:
    code, output = run_selector(tmp_path, b"\x1b[B\x1b[B\x1b[B \r", columns=40)
    assert code == 0, output
    assert "SELECTED=tumonline" in output


def test_empty_no_color_variable_disables_selector_color(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b" \r", no_color=True)
    assert code == 0, output
    assert "SELECTED=moodle" in output
    for sequence in re.findall(r"\x1b\[([\d;]*)m", output):
        assert not any(
            30 <= int(value) <= 49 or 90 <= int(value) <= 107
            for value in sequence.split(";")
            if value
        )


def test_real_browser_picker_uses_the_chosen_browser_at_narrow_width(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b" \r", browser_keys=b"\x1b[B\r", columns=40)
    assert code == 0, output
    assert "SELECTED=moodle" in output and "BROWSER=second" in output


@pytest.mark.parametrize("keys", [b"\x03", b"\x1b"])
@pytest.mark.parametrize("terminal", ["xterm-256color", "dumb"])
def test_cancelling_browser_picker_does_not_connect(
    tmp_path: Path, keys: bytes, terminal: str
) -> None:
    code, output = run_selector(
        tmp_path, b"1\n" if terminal == "dumb" else b" \r", browser_keys=keys, terminal=terminal
    )
    assert code == 130, output
    assert "SELECTED=" not in output and "No browser was opened" in output


def test_dumb_terminal_browser_picker(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b"1,2\n", browser_keys=b"2\n", terminal="dumb")
    assert code == 0, output
    assert "SELECTED=moodle,artemis" in output and "BROWSER=second" in output


@pytest.mark.parametrize("terminal", ["xterm-256color", "dumb"])
@pytest.mark.parametrize("override", [False, True])
def test_login_defaults_to_action_needed_services_and_allows_changes(
    tmp_path: Path, terminal: str, override: bool
) -> None:
    checks = (
        ("Moodle", State.ACTION),
        ("Artemis 1", State.READY),
        ("Artemis 2", State.ACTION),
        ("Zulip", State.CONFIGURED),
        ("TUMonline", State.UNCONFIGURED),
    )
    keys = b"\r"
    if override:
        keys = b"3\n" if terminal == "dumb" else b" \x1b[B \x1b[B \r"
    code, output = run_selector(tmp_path, keys, terminal=terminal, checks=checks)
    assert code == 0, output
    selected = re.search(r"SELECTED=([^\r\n]+)", output)
    assert selected and selected[1] == ("zulip" if override else "moodle,artemis"), output


@pytest.mark.parametrize("terminal", ["xterm-256color", "dumb"])
@pytest.mark.parametrize("cancel", [False, True])
def test_logout_picker_removes_only_selected_connection_or_cancels(
    tmp_path: Path, terminal: str, cancel: bool
) -> None:
    from tum_mcp.credentials import Credential, Vault
    from tum_mcp.moodle.auth import Session, SessionStore
    from tum_mcp.moodle.config import Paths
    from tum_mcp.settings import Account, Provider, save_account

    store = SessionStore(Paths.default(), storage="file")
    store.save(Session(generation=store.begin_login(), cookies=[], verified_at=0))
    account = Account(provider=Provider.ARTEMIS, origin="https://example.invalid", principal="keep")
    save_account(account)
    vault = Vault()
    vault.save(account, Credential(account_id=account.id))
    keys = b"\x1b" if cancel else b"1\n" if terminal == "dumb" else b" \r"
    code, output = run_selector(
        tmp_path,
        keys,
        terminal=terminal,
        command="logout",
        checks=(("Moodle", State.ACTION), ("Artemis", State.READY)),
    )
    assert code == (130 if cancel else 0), output
    assert store.file("session.enc").exists() is cancel
    assert vault.load(account).account_id == account.id
