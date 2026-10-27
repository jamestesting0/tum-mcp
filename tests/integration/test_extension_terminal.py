import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Real keyboard QA uses POSIX PTYs.")


def run_removal(
    tmp_path: Path,
    keys: bytes,
    *,
    enabled: tuple[str, ...] = ("lecture", "studocu"),
    terminal: str = "xterm-256color",
    no_color: bool = False,
    columns: int = 80,
    mode: str = "uninstall",
    launcher: bool = False,
) -> tuple[int, str, dict[str, bool]]:
    import fcntl
    import pty
    import struct
    import termios

    config = tmp_path / "config"
    config.mkdir()
    if "lecture" in enabled:
        (config / "lecture-extension.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "enabled": True,
                    "installed_at": "2026-10-27T00:00:00Z",
                    "package_version": "fixture",
                    "asr_requested": False,
                }
            ),
            encoding="utf-8",
        )
    (config / "extensions.json").write_text(
        json.dumps({"schema_version": 1, "studocu": "studocu" in enabled}), encoding="utf-8"
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "from pathlib import Path\n"
        f"Path.home = classmethod(lambda cls: Path({str(tmp_path / 'profile')!r}))\n"
        "from tum_mcp.cli import main\nmain()\n",
        encoding="utf-8",
    )
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, columns, 0, 0))
    env = {
        **os.environ,
        "TERM": terminal,
        "COLUMNS": str(columns),
        "LINES": "35",
        "TUM_MCP_DATA_DIR": str(tmp_path / "data"),
        "TUM_MCP_CONFIG_DIR": str(config),
        "TUM_MOODLE_DATA_DIR": str(tmp_path / "moodle"),
    }
    if no_color:
        env["NO_COLOR"] = ""
    else:
        env.pop("NO_COLOR", None)
    if launcher:
        env["TUM_MCP_NPM_LAUNCHER"] = "1"
    if mode == "setup":
        executables = tmp_path / "bin"
        executables.mkdir()
        for name in ("codex", "claude"):
            marker = executables / name
            marker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            marker.chmod(0o700)
        env["PATH"] = str(executables) + os.pathsep + env.get("PATH", "")
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, str(driver), mode, *(["--no-asr"] if mode == "install" else [])],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
    )
    os.close(slave)
    captured = bytearray()
    sent = False
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                captured.extend(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
                plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", bytes(captured))
                ready = (
                    b"Selection: " in plain
                    if terminal == "dumb"
                    else (
                        (b"Generic" if mode == "setup" else b"Studocu") in plain
                        and b"\x1b[?25l" in captured
                    )
                )
                if not sent and ready:
                    if destination := os.environ.get("TUM_MCP_TERMINAL_QA"):
                        folder = Path(destination)
                        folder.mkdir(parents=True, exist_ok=True)
                        (
                            folder
                            / f"remove-{terminal}-{columns}-{no_color}-{keys.hex()}-initial.ansi"
                        ).write_bytes(captured)
                    os.write(master, keys)
                    sent = True
            if process.poll() is not None:
                break
        else:
            pytest.fail("Extension picker did not complete within its terminal budget.")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        os.close(master)
    output = bytes(captured).decode("utf-8", errors="replace")
    if destination := os.environ.get("TUM_MCP_TERMINAL_QA"):
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"remove-{terminal}-{columns}-{no_color}-{keys.hex()}.ansi").write_text(
            output, encoding="utf-8"
        )
    lecture = config / "lecture-extension.json"
    state = {
        "lecture": lecture.exists() and json.loads(lecture.read_text())["enabled"],
        "studocu": json.loads((config / "extensions.json").read_text())["studocu"],
    }
    return process.returncode, output, state


@pytest.mark.parametrize("columns", [40, 80, 100])
def test_keyboard_removal_changes_only_the_checked_extension(tmp_path: Path, columns: int) -> None:
    code, output, state = run_removal(tmp_path, b" \r", columns=columns)
    assert code == 0, output
    assert state == {"lecture": False, "studocu": True}
    assert "●" in output


def test_keyboard_removal_can_disable_both_extensions(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b" \x1b[B \r")
    assert code == 0, output
    assert state == {"lecture": False, "studocu": False}


def test_keyboard_cancellation_preserves_every_extension(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b"\x03")
    assert code == 130, output
    assert state == {"lecture": True, "studocu": True}
    assert "\x1b[?25h" in output


def test_disabled_extensions_cannot_be_selected(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b" \r", enabled=("studocu",))
    assert code == 0, output
    assert state == {"lecture": False, "studocu": False}


def test_numbered_picker_rejects_disabled_items_and_removes_only_the_selected_one(
    tmp_path: Path,
) -> None:
    code, output, state = run_removal(tmp_path, b"1\n2\n", enabled=("studocu",), terminal="dumb")
    assert code == 0, output
    assert state == {"lecture": False, "studocu": False}
    assert "\x1b[" not in output


def test_no_color_preserves_status_labels_and_keyboard_operation(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b" \r", no_color=True)
    assert code == 0, output
    assert state == {"lecture": False, "studocu": True}
    for sequence in re.findall(r"\x1b\[([\d;]*)m", output):
        assert not any(
            30 <= int(value) <= 49 or 90 <= int(value) <= 107
            for value in sequence.split(";")
            if value
        )


def test_no_optional_extensions_still_offers_full_package_removal(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b"\x03", enabled=())
    assert code == 130, output
    assert state == {"lecture": False, "studocu": False}
    assert "All" in output


def test_all_selection_hands_off_to_the_launcher_without_partial_extension_changes(
    tmp_path: Path,
) -> None:
    code, output, state = run_removal(tmp_path, b"\x1b[B\x1b[B \r", launcher=True)
    assert code == 20, output
    assert state == {"lecture": True, "studocu": True}


def test_all_cannot_be_combined_with_individual_extension_removal(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b" \x1b[B\x1b[B \r \r", launcher=True)
    assert code == 0, output
    assert state == {"lecture": False, "studocu": True}


def test_install_picker_can_install_both_workflows_without_recognition(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b" \x1b[B \r", enabled=(), mode="install")
    assert code == 0, output
    assert state == {"lecture": True, "studocu": True}


def test_install_picker_skips_an_already_installed_workflow(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b" \r", enabled=("lecture",), mode="install")
    assert code == 0, output
    assert state == {"lecture": True, "studocu": True}


def test_cancelled_install_picker_does_not_enable_any_workflow(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b"\x03", enabled=(), mode="install")
    assert code == 130, output
    assert state == {"lecture": False, "studocu": False}


def test_setup_picker_configures_only_the_selected_client(tmp_path: Path) -> None:
    code, output, _ = run_removal(tmp_path, b"\x1b[B \r", mode="setup")
    assert code == 0, output
    assert (tmp_path / "profile/.claude.json").is_file()
    assert not (tmp_path / "profile/.codex/plugins/local/tum-mcp").exists()


def test_cancelled_setup_does_not_create_client_registrations(tmp_path: Path) -> None:
    code, output, _ = run_removal(tmp_path, b"\x03", mode="setup")
    assert code == 130, output
    assert not (tmp_path / "profile").exists()


def test_login_picker_cancels_without_opening_a_browser(tmp_path: Path) -> None:
    code, output, state = run_removal(tmp_path, b"\x03", mode="login")
    assert code == 130, output
    assert state == {"lecture": True, "studocu": True}
    assert "\x1b[?25h" in output
