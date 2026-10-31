import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tum_mcp.tumonline.policy import PolicyStore, Scope

pytestmark = pytest.mark.skipif(os.name == "nt", reason="PTY keyboard QA requires POSIX.")
ACCOUNT = "a" * 64


def run_manager(
    tmp_path: Path, keys: bytes, *, terminal: str = "xterm-256color"
) -> tuple[int, str]:
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    columns = int(os.environ.get("TUM_MCP_TERMINAL_COLUMNS", "40"))
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, columns, 0, 0))
    env = {
        **os.environ,
        "TERM": terminal,
        "COLUMNS": str(columns),
        "LINES": "30",
        "NO_COLOR": "1",
        "TUM_MCP_CONFIG_DIR": str(tmp_path),
    }
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "from tum_mcp.cli import main; main()", "manage", "tumonline"],
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
                if not chunk:
                    break
                captured.extend(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
                plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", bytes(captured))
                ready = (
                    b"Permissions: " in plain
                    if terminal == "dumb"
                    # The last row appears once in the category notes and once in the selector.
                    else (plain.count(b"Admission") >= 2 and b"\x1b[?25l" in captured)
                )
                if not sent and ready:
                    if destination := os.environ.get("TUM_MCP_TERMINAL_QA"):
                        Path(destination).mkdir(parents=True, exist_ok=True)
                        (
                            Path(destination) / f"tumonline-{terminal}-{keys.hex()}-initial.ansi"
                        ).write_bytes(captured)
                    os.write(master, keys)
                    sent = True
            if process.poll() is not None:
                break
        else:
            pytest.fail("Permission selector did not finish.")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        os.close(master)
    output = bytes(captured).decode("utf-8", errors="replace")
    if destination := os.environ.get("TUM_MCP_TERMINAL_QA"):
        Path(destination).mkdir(parents=True, exist_ok=True)
        (Path(destination) / f"tumonline-{terminal}-{keys.hex()}.ansi").write_text(
            output, encoding="utf-8"
        )
    return process.returncode, output


@pytest.mark.parametrize("enabled", [False, True])
def test_checkbox_toggles_studies_and_leaves_other_categories_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, enabled)
    code, output = run_manager(tmp_path, b" \r")
    assert code == 0, output
    assert "Grades and progress" in output
    assert policies.read(ACCOUNT).allowed == (
        frozenset() if enabled else frozenset({Scope.STUDIES_COURSES})
    )


def test_arrow_keys_move_between_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    code, output = run_manager(tmp_path, b"\x1b[B\x1b[B\x1b[A \x1b[B\x1b[B \r")
    assert code == 0, output
    assert policies.read(ACCOUNT).allowed == frozenset(
        {Scope.STUDIES_COURSES, Scope.ACADEMIC_PROGRESS, Scope.ADMISSION}
    )


def test_checkbox_cancellation_preserves_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    original = policies.create(ACCOUNT)
    code, output = run_manager(tmp_path, b" \x03")
    assert code == 0, output
    assert policies.read(ACCOUNT) == original


@pytest.mark.parametrize(
    "keys, allowed",
    [
        (b"none\n", frozenset()),
        (b"\n", frozenset({Scope.STUDIES_COURSES})),
        (b"2, 3\n", frozenset({Scope.ACADEMIC_PROGRESS, Scope.EXAMS})),
    ],
)
def test_basic_terminal_accepts_numbered_selection_revoke_or_keep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keys: bytes, allowed: frozenset[Scope]
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    code, output = run_manager(tmp_path, keys, terminal="dumb")
    assert code == 0, output
    assert "Exams (denied)" in output and "\x1b[" not in output
    assert policies.read(ACCOUNT).allowed == allowed


def test_basic_terminal_rejects_an_unknown_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    code, output = run_manager(tmp_path, b"5\nnone\n", terminal="dumb")
    assert code == 0, output
    assert not policies.read(ACCOUNT).allowed
