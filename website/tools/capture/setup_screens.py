"""Record the real `tum-mcp setup` screens for one coding app.

Usage: setup_screens.py TUM_MCP_BIN OUT_JSON ROW HOME

Runs setup in a pseudo-terminal with a throwaway HOME, picks the app on row ROW, then
selects every optional workflow and cancels before anything is installed.
"""

import fcntl
import json
import os
import pty
import select
import struct
import sys
import termios
import time

import pyte

BINARY, OUT, ROW, HOME = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
COLUMNS, LINES = 88, 30
DOWN, ESCAPE = "\x1b[B", "\x1b"

screen = pyte.Screen(COLUMNS, LINES)
stream = pyte.ByteStream(screen)
environment = dict(
    os.environ,
    HOME=HOME,
    PATH=os.path.join(HOME, "bin") + os.pathsep + os.environ["PATH"],
    TERM="xterm-256color",
    COLUMNS=str(COLUMNS),
    LINES=str(LINES),
)
pid, terminal = pty.fork()
if pid == 0:
    os.chdir(HOME)
    os.execve(BINARY, [BINARY, "setup"], environment)  # noqa: S606 - the repo's own CLI
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


def press(keys: str, seconds: float = 0.5) -> None:
    _ = os.write(terminal, keys.encode())
    read_for(seconds)


read_for(12)
record("clients")
for _ in range(ROW):
    press(DOWN, 0.3)
press(" ")
record("clients-selected")
press("\r", 15)
record("workflows")
for index in range(4):
    press(" ")
    if index < 3:
        press(DOWN)
record("workflows-selected")
press(ESCAPE, 6)
record("next")
with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(screens, handle)
