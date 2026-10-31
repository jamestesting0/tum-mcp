"""The trial's `tum-mcp` command: runs the variant's CLI and refuses account-changing commands.

Usage: <variant python> -I shim.py <tum-mcp arguments...>
Standard library only, because it runs on the variant's interpreter without the lab on its path.
"""

import os
import sys

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


def main() -> None:
    arguments = sys.argv[1:]
    message = refusal(arguments)
    if message:
        print(message, file=sys.stderr)
        raise SystemExit(2)
    os.execv(sys.executable, [sys.executable, "-I", "-m", "tum_mcp", *arguments])  # noqa: S606


if __name__ == "__main__":
    main()
