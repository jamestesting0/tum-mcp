"""Stdio MCP filter in front of the TUM server: hides and refuses account-changing tools.

Usage: python -I mcp_proxy.py --block a,b -- <backend command...>
Standard library only, because it runs on the variant's interpreter without the lab on its path.
"""

import json
import subprocess
import sys
import threading

BLOCKED_MESSAGE = "This tool is not available in a skill-lab trial."


def is_blocked(tool: dict, blocked: set[str]) -> bool:
    annotations = tool.get("annotations") or {}
    return tool.get("name") in blocked or annotations.get("destructiveHint") is True


class Proxy:
    def __init__(self, blocked: set[str], out) -> None:
        self.blocked = set(blocked)
        self.out = out
        self.list_ids: set[object] = set()
        self.lock = threading.Lock()

    def emit(self, message: object) -> None:
        with self.lock:
            self.out.write(json.dumps(message) + "\n")
            self.out.flush()

    def from_client(self, line: str) -> str | None:
        try:
            message = json.loads(line)
        except ValueError:
            return line
        if not isinstance(message, dict):
            return line
        if message.get("method") == "tools/list":
            self.list_ids.add(message.get("id"))
        if message.get("method") == "tools/call":
            name = (message.get("params") or {}).get("name")
            if name in self.blocked:
                self.emit(
                    {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "result": {
                            "content": [{"type": "text", "text": BLOCKED_MESSAGE}],
                            "isError": True,
                        },
                    }
                )
                return None
        return line

    def from_server(self, line: str) -> str:
        try:
            message = json.loads(line)
        except ValueError:
            return line
        if not isinstance(message, dict) or message.get("id") not in self.list_ids:
            return line
        self.list_ids.discard(message.get("id"))
        result = message.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            kept = []
            for tool in result["tools"]:
                if is_blocked(tool, self.blocked):
                    self.blocked.add(tool.get("name"))
                else:
                    kept.append(tool)
            result["tools"] = kept
            return json.dumps(message)
        return line


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("usage: mcp_proxy.py --block a,b -- <command...>", file=sys.stderr)
        return 2
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1 :]
    blocked: set[str] = set()
    if "--block" in options:
        blocked = {name for name in options[options.index("--block") + 1].split(",") if name}
    backend = subprocess.Popen(  # noqa: S603 - the lab passes a fixed backend command
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
    )
    proxy = Proxy(blocked, sys.stdout)
    server_out, server_in = backend.stdout, backend.stdin
    if server_out is None or server_in is None:
        raise RuntimeError("The backend pipes did not open.")

    def pump_server() -> None:
        for line in server_out:
            with proxy.lock:
                sys.stdout.write(proxy.from_server(line.rstrip("\n")) + "\n")
                sys.stdout.flush()

    reader = threading.Thread(target=pump_server, daemon=True)
    reader.start()
    for line in sys.stdin:
        forwarded = proxy.from_client(line.rstrip("\n"))
        if forwarded is not None:
            server_in.write(forwarded + "\n")
            server_in.flush()
    server_in.close()
    code = backend.wait()
    reader.join()
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
