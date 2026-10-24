"""Verify installed client discovery in disposable profiles, without running a model."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from tum_mcp import __version__
from tum_mcp.clients import install_client
from tum_mcp.skills import inspect_skills


def verify() -> dict[str, object]:
    codex = shutil.which("codex")
    claude = shutil.which("claude")
    if not codex or not claude:
        raise RuntimeError("Both installed CLIs are required for this opt-in verification.")
    with tempfile.TemporaryDirectory(prefix="tum-mcp-hosts-") as temporary:
        root = Path(temporary)
        home = root / "profile"
        previous = {key: os.environ.get(key) for key in ("TUM_MCP_DATA_DIR", "TUM_MCP_CONFIG_DIR")}
        os.environ["TUM_MCP_DATA_DIR"] = str(root / "data")
        os.environ["TUM_MCP_CONFIG_DIR"] = str(root / "config")
        try:
            with redirect_stdout(sys.stderr):
                install_client("codex", home)
                install_client("claude", home)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "TMPDIR", "TMP", "TEMP", "USER", "LOGNAME"}
        }
        environment.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "CODEX_HOME": str(home / ".codex"),
                "TUM_MCP_DATA_DIR": str(root / "data"),
                "TUM_MCP_CONFIG_DIR": str(root / "config"),
                "TUM_MOODLE_DATA_DIR": str(root / "moodle"),
            }
        )

        def run(command: list[str]) -> str:
            result = subprocess.run(  # noqa: S603
                command,
                env=environment,
                cwd=home,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f"Client verification failed: {result.stderr}")
            return result.stdout

        run([codex, "plugin", "marketplace", "add", str(home), "--json"])
        installed = json.loads(run([codex, "plugin", "add", "tum-mcp@personal-local", "--json"]))
        listing = json.loads(
            run([codex, "plugin", "list", "--marketplace", "personal-local", "--json"])
        )
        claude_status = run([claude, "mcp", "get", "tum"])
        if "Connected" not in claude_status:
            raise RuntimeError("Claude did not connect to the campus stdio process.")
        with (root / "app-server.log").open("w+") as diagnostics:
            process = subprocess.Popen(  # noqa: S603
                [codex, "app-server", "--stdio"],
                env=environment,
                cwd=home,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=diagnostics,
                text=True,
            )
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("App-server pipes unavailable.")
            incoming: Queue[str] = Queue()

            def read_stdout() -> None:
                if process.stdout is not None:
                    for line in process.stdout:
                        incoming.put(line)

            reader = Thread(target=read_stdout, daemon=True)
            reader.start()
            sequence = 0

            def request(method: str, params: dict[str, object]) -> object:
                nonlocal sequence
                sequence += 1
                if process.stdin is None or process.stdout is None:
                    raise RuntimeError("App-server disconnected.")
                process.stdin.write(
                    json.dumps({"id": sequence, "method": method, "params": params}) + "\n"
                )
                process.stdin.flush()
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    try:
                        line = incoming.get(timeout=1)
                    except Empty:
                        if process.poll() is not None:
                            break
                        continue
                    if not line:
                        break
                    response = json.loads(line)
                    if response.get("id") == sequence:
                        if "error" in response:
                            raise RuntimeError(str(response["error"]))
                        return response["result"]
                raise RuntimeError(f"No app-server response for {method}.")

            try:
                request(
                    "initialize",
                    {
                        "clientInfo": {"name": "tum_mcp_local_qa", "version": __version__},
                        "capabilities": {"experimentalApi": True},
                    },
                )
                process.stdin.write('{"method":"initialized","params":{}}\n')
                process.stdin.flush()
                skills = request("skills/list", {"cwds": [str(home)], "forceReload": True})
                plugin = request(
                    "plugin/read",
                    {
                        "pluginName": "tum-mcp",
                        "marketplacePath": str(home / ".agents/plugins/marketplace.json"),
                    },
                )
                servers = request("mcpServerStatus/list", {})
                expected_skills = {"tum-mcp:" + item["name"] for item in inspect_skills()}
                actual_skills = {
                    item["name"]
                    for entry in skills["data"]
                    for item in entry["skills"]
                    if item.get("pluginId") == "tum-mcp@personal-local"
                }
                if actual_skills != expected_skills:
                    raise RuntimeError("Codex did not discover the complete campus skill pack.")
                campus = next((item for item in servers["data"] if item["name"] == "tum"), None)
                required = {"moodle_list_courses", "artemis_get_feedback", "zulip_search_messages"}
                if (
                    campus is None
                    or campus.get("toolsError")
                    or not required <= campus["tools"].keys()
                ):
                    raise RuntimeError("Codex did not discover the required campus MCP tools.")
                if {"artemis_submit", "artemis_start_exercise"} & campus["tools"].keys():
                    raise RuntimeError("Unverified remote-action tools were unexpectedly exposed.")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                reader.join(timeout=1)
        return {
            "codex_version": run([codex, "--version"]).strip(),
            "claude_version": run([claude, "--version"]).strip(),
            "installed": installed,
            "listing": listing,
            "skills": skills,
            "plugin": plugin,
            "servers": servers,
            "claude_mcp_connected": True,
            "model_trials_run": False,
            "real_user_profile_modified": False,
        }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
