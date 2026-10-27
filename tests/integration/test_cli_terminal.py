import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="PTY keyboard QA uses POSIX terminal APIs.")


def run_selector(
    tmp_path: Path,
    keys: bytes,
    *,
    terminal: str = "xterm-256color",
    no_color: bool = False,
    browser_keys: bytes | None = None,
    columns: int = 80,
) -> tuple[int, str]:
    import pty

    driver = tmp_path / "driver.py"
    driver.write_text(
        "import sys\n"
        "from tum_mcp import connect\n"
        "from tum_mcp.connect import ConnectionResult\n"
        "import tum_mcp.moodle.browsers as browsers\n"
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
        "sys.argv=['tum-mcp','login']\n"
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
                ready = (
                    b"Selection: " in plain
                    if terminal == "dumb"
                    else b"TUMonline" in plain and b"\x1b[?25l" in captured
                )
                if not sent and ready:
                    os.write(master, keys)
                    sent = True
                elif sent and not browser_sent and browser_keys and b"Browser" in plain:
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
    if destination := os.environ.get("TUM_MCP_TERMINAL_QA"):
        Path(destination).mkdir(parents=True, exist_ok=True)
        (Path(destination) / f"selector-{keys.hex()}.ansi").write_text(output, encoding="utf-8")
    return process.returncode, output


def test_real_terminal_selection_connects_only_the_checked_services(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b" \x1b[B\x1b[B \r")
    assert code == 0, output
    assert "SELECTED=moodle,zulip" in output
    assert "SELECTED=moodle,artemis,zulip" not in output


def test_real_terminal_cancellation_restores_cursor_and_never_connects(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b"\x03")
    assert code == 130, output
    assert "SELECTED=" not in output
    assert "Cancelled" in output
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


def test_cancelling_browser_picker_does_not_connect(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b" \r", browser_keys=b"\x03")
    assert code == 130, output
    assert "SELECTED=" not in output and "No browser was opened" in output


def test_dumb_terminal_browser_picker(tmp_path: Path) -> None:
    code, output = run_selector(tmp_path, b"1,2\n", browser_keys=b"2\n", terminal="dumb")
    assert code == 0, output
    assert "SELECTED=moodle,artemis" in output and "BROWSER=second" in output
