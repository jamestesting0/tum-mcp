"""Record the real `tum-mcp login` picker screens.

Usage: login_screens.py TUM_MCP_BIN PYTHON OUT_JSON HOME

Runs login in a pseudo-terminal with a throwaway HOME whose Lecture workflow is on (as after
the walkthrough's setup), ticks Moodle, confirms, and presses Esc at the browser list, which
cancels before any browser opens. No account or credential is involved.
"""

import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

import pyte

BINARY, PYTHON, OUT, HOME = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
COLUMNS, LINES = 88, 30
ESCAPE = "\x1b"

environment = dict(
    os.environ,
    HOME=HOME,
    TERM="xterm-256color",
    COLUMNS=str(COLUMNS),
    LINES=str(LINES),
)
_ = subprocess.run(  # noqa: S603 - the repo's own interpreter writes the Lecture record
    [
        PYTHON,
        "-c",
        "\n".join(
            (
                "from datetime import UTC, datetime",
                "from tum_mcp.extensions import LectureInstallation, config_path",
                "path = config_path() / 'lecture-extension.json'",
                "path.parent.mkdir(parents=True, exist_ok=True)",
                "record = LectureInstallation(",
                "    enabled=True, installed_at=datetime.now(UTC), package_version='walkthrough'",
                ")",
                "path.write_text(record.model_dump_json())",
            )
        ),
    ],
    env=environment,
    check=True,
)

screen = pyte.Screen(COLUMNS, LINES)
stream = pyte.ByteStream(screen)
pid, terminal = pty.fork()
if pid == 0:
    os.chdir(HOME)
    os.execve(BINARY, [BINARY, "login"], environment)  # noqa: S606 - the repo's own CLI
_ = fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", LINES, COLUMNS, 0, 0))
screens: dict[str, list[list[list[object]]]] = {}


def read_for(seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        ready, _, _ = select.select([terminal], [], [], 0.05)
        if not ready:
            continue
        try:
            data = os.read(terminal, 65536)
        except OSError:
            return
        if not data:
            return
        stream.feed(data)


def record(name: str) -> None:
    screens[name] = [
        [[cell.data, cell.fg, cell.bold] for cell in (screen.buffer[y][x] for x in range(COLUMNS))]
        for y in range(LINES)
    ]


def press(keys: str, seconds: float = 0.6) -> None:
    _ = os.write(terminal, keys.encode())
    read_for(seconds)


read_for(15)
record("services")
press(" ")
record("services-selected")
press("\r", 4)
record("browser")
press(ESCAPE, 3)
record("cancelled")
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(screens, handle)
