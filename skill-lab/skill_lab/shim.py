"""The trial's `tum-mcp` command: runs the variant's CLI and refuses account-changing commands.

Usage: <variant python> -I shim.py <tum-mcp arguments...>
Standard library only, because it runs on the variant's interpreter without the lab on its path.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime

BLOCKED = frozenset(
    {"login", "logout", "setup", "uninstall", "update", "install", "manage", "serve"}
)
BLOCKED_STUDY = frozenset({"publish"})


def refusal(arguments: list[str]) -> str | None:
    if arguments and arguments[0] in BLOCKED:
        return f"tum-mcp {arguments[0]} is not available in a skill-lab trial."
    if len(arguments) > 1 and arguments[0] == "study" and arguments[1] in BLOCKED_STUDY:
        return f"tum-mcp study {arguments[1]} is not available in a skill-lab trial."
    return None


# Browser checks, fresh checker sessions and recording acquisition need the host's
# capabilities; the trial still selects only workspace-bound, vetted commands.
BROKERED = (
    ["study", "visuals"],
    ["review", "run-checker"],
    ["lecture", "prepare"],
    ["audio-notes", "listen"],
    ["video-notes", "listen"],
)
WAIT_SECONDS = 2400


def brokers(arguments: list[str]) -> bool:
    """Whether the lab runs this command on the host; help needs no browser or checker."""
    if "--help" in arguments or "-h" in arguments:
        return False
    return any(arguments[: len(prefix)] == prefix for prefix in BROKERED)


def brokered(arguments: list[str], folder: str) -> int:
    """Hand the command to the lab through a request file and print the host's result."""
    os.makedirs(folder, exist_ok=True)
    name = uuid.uuid4().hex
    request = os.path.join(folder, f"{name}.request.json")
    with open(request + ".tmp", "w", encoding="utf-8") as handle:
        json.dump({"arguments": arguments, "cwd": os.getcwd()}, handle)
    os.replace(request + ".tmp", request)
    response = os.path.join(folder, f"{name}.response.json")
    deadline = time.monotonic() + WAIT_SECONDS
    while not os.path.exists(response):
        if time.monotonic() > deadline:
            print("The lab did not run the check in time.", file=sys.stderr)
            return 1
        time.sleep(1)
    with open(response, encoding="utf-8") as handle:
        result = json.load(handle)
    sys.stdout.write(result["stdout"])
    sys.stderr.write(result["stderr"])
    return int(result["code"])


def checker(log: str, kind: str, command: list[str]) -> int:
    """Observe each fresh or repair invocation without retaining its prompt or output."""
    attempt = 0
    if os.path.exists(log):
        with open(log, encoding="utf-8") as handle:
            attempt = sum(json.loads(line)["event"] == "started" for line in handle)
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "started",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "attempt": attempt,
                    "kind": kind,
                }
            )
            + "\n"
        )
        handle.flush()
        done = subprocess.run(command, check=False)
        handle.write(
            json.dumps(
                {
                    "event": "completed",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "attempt": attempt,
                    "status": "completed" if done.returncode == 0 else "failed",
                }
            )
            + "\n"
        )
    return done.returncode


def main() -> None:
    arguments = sys.argv[1:]
    if arguments[:1] == ["--lab-checker"]:
        raise SystemExit(checker(arguments[1], arguments[2], arguments[3:]))
    message = refusal(arguments)
    if message:
        print(message, file=sys.stderr)
        raise SystemExit(2)
    folder = os.environ.get("SKILL_LAB_RENDER_BROKER")
    if folder and brokers(arguments):
        raise SystemExit(brokered(arguments, folder))
    os.execv(sys.executable, [sys.executable, "-I", "-m", "tum_mcp", *arguments])  # noqa: S606


if __name__ == "__main__":
    main()
