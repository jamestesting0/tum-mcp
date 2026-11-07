"""Ask Codex itself to identify and verify this installer's user-level hooks."""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from tum_mcp.clients.hosts import ClientHost
from tum_mcp.clients.installs import load_receipt, read_owned_file
from tum_mcp.errors import CampusError, Code


class Runtime:
    def __init__(self, home: Path) -> None:
        executable = shutil.which("codex")
        if executable is None:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Codex CLI is unavailable; automatic registration verification could not run. "
                "In Codex, enable TUM MCP in Plugins and inspect Settings > Hooks "
                "(or /hooks in the CLI) to review only the TUM course guard. "
                "Run tum-mcp doctor when the CLI is available; native loading remains unverified.",
            )
        self.process = subprocess.Popen(  # noqa: S603
            [executable, "app-server", "--stdio", "-c", "mcp_servers={}"],
            cwd=home,
            env={**os.environ, "CODEX_HOME": str(home / ".codex")},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        self.messages: queue.Queue = queue.Queue()
        self.sequence = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except (ValueError, OSError):
            pass
        finally:
            self.messages.put(None)

    def call(self, method: str, params: dict) -> dict:
        self.sequence += 1
        self.process.stdin.write(
            json.dumps({"id": self.sequence, "method": method, "params": params}) + "\n"
        )
        self.process.stdin.flush()
        deadline = time.monotonic() + 15
        while True:
            try:
                message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise CampusError(
                    Code.ACTION_REQUIRED, "Codex registration verification timed out."
                ) from None
            if message is None:
                raise CampusError(
                    Code.ACTION_REQUIRED, "Codex registration verification stopped unexpectedly."
                )
            if message.get("id") != self.sequence:
                continue
            if "error" in message:
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Codex rejected registration verification; inspect /hooks in Codex.",
                )
            return message["result"]

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()


def verify(home: Path, host: ClientHost, *, install: bool = False) -> str:
    """Only explicit setup may activate this plugin or trust its owned hook definitions."""
    if host != ClientHost.LOCAL:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Run doctor in the Windows host to verify Codex; WSL file inspection is static only.",
        )
    receipt = load_receipt("codex", host, home)
    if receipt is None or not receipt.hooks:
        raise CampusError(
            Code.ACTION_REQUIRED, "Rerun tum-mcp setup --client codex to register the course guard."
        )
    config = home / ".codex/config.toml"
    read_owned_file(config, home)
    expected = {
        entry["hooks"][0]["command"] for entries in receipt.hooks.values() for entry in entries
    }
    runtime = Runtime(home)
    try:
        runtime.call(
            "initialize",
            {
                "clientInfo": {"name": "tum-mcp-setup", "version": "1"},
                "capabilities": {"experimentalApi": True, "explicitGatewayOauth": True},
            },
        )
        configuration = runtime.call("config/read", {"includeLayers": False})
        features = configuration.get("config", {}).get("features") or {}
        if features.get("hooks") is False or features.get("codex_hooks") is False:
            raise CampusError(
                Code.ACTION_REQUIRED, "Codex hooks are disabled; setup preserves host policy."
            )
        if install:
            runtime.call(
                "plugin/install",
                {
                    "marketplacePath": str(home / ".agents/plugins/marketplace.json"),
                    "pluginName": "tum-mcp",
                },
            )
        details = runtime.call(
            "plugin/read",
            {
                "marketplacePath": str(home / ".agents/plugins/marketplace.json"),
                "pluginName": "tum-mcp",
            },
        )
        if not details["plugin"]["summary"]["enabled"]:
            raise CampusError(
                Code.ACTION_REQUIRED, "The TUM plugin is disabled in Codex; enable it in Plugins."
            )

        def listing() -> list[dict]:
            result = runtime.call("hooks/list", {"cwds": [str(home)]})
            return [
                h
                for entry in result["data"]
                for h in entry["hooks"]
                if h.get("source") == "user"
                and Path(h["sourcePath"]) == home / ".codex/hooks.json"
                and h.get("command") in expected
            ]

        hooks = listing()
        if len(hooks) != len(expected) or any(not h["enabled"] for h in hooks):
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Codex did not load all enabled TUM hooks; inspect /hooks and host policy. "
                "Setup preserves disabled hooks.",
            )
        if install:
            if any(not re.fullmatch(r"sha256:[0-9a-f]{64}", h["currentHash"]) for h in hooks):
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Codex returned an unsupported hook identity; review the TUM hooks in /hooks.",
                )
            runtime.call(
                "config/batchWrite",
                {
                    "edits": [
                        {
                            "keyPath": "hooks.state",
                            "value": {h["key"]: {"trusted_hash": h["currentHash"]} for h in hooks},
                            "mergeStrategy": "upsert",
                        }
                    ],
                    "reloadUserConfig": True,
                },
            )
            hooks = listing()
        if any(h["trustStatus"] != "trusted" for h in hooks):
            raise CampusError(
                Code.ACTION_REQUIRED,
                "TUM hooks need trust in this Codex version; "
                "review the TUM entries in /hooks, then rerun doctor.",
            )
        return "Codex loaded the TUM plugin and all three enabled, trusted course hooks."
    except (KeyError, TypeError, AttributeError):
        raise CampusError(
            Code.ACTION_REQUIRED,
            "This Codex runtime has an unsupported registration response; "
            "review the TUM hooks in /hooks, then rerun doctor.",
        ) from None
    finally:
        runtime.close()
