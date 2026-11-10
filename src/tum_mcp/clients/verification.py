"""Check owned registrations without model requests, sign-in or campus reads."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TextIO

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tum_mcp.clients import hook_config
from tum_mcp.clients.config import client_config_path, read_client_config
from tum_mcp.clients.hosts import ClientHost
from tum_mcp.clients.installs import Installation, load_receipt, read_owned_file
from tum_mcp.commands.ui import State
from tum_mcp.errors import CampusError, Code


async def transport(server: dict, root: Path, errors: TextIO) -> None:
    arguments = [
        str(value).replace("${PLUGIN_ROOT}", str(root)) for value in server.get("args", [])
    ]
    params = StdioServerParameters(
        command=server["command"],
        args=arguments,
        env={**os.environ, **server.get("env", {})},
    )
    async with asyncio.timeout(20):
        async with stdio_client(params, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                if "moodle_list_courses" not in {tool.name for tool in tools.tools}:
                    raise CampusError(
                        Code.INVALID_RESPONSE,
                        "The registered server is missing the TUM tool catalog.",
                    )


def inspect(
    name: str, home: Path, host: ClientHost, *, live: bool, refresh: bool = False
) -> tuple[State, str]:
    receipt = load_receipt(name, host, home)
    if receipt is None:
        return (
            State.ACTION,
            "Registration has no ownership receipt; rerun tum-mcp setup before live verification.",
        )
    configured = read_client_config(client_config_path(name, home, host=host)).mcpServers.get("tum")
    if configured != receipt.server:
        return (
            State.ACTION,
            "The MCP registration differs from its receipt; "
            "preserve and review it before live verification.",
        )
    for relative, digest in receipt.files.items():
        value = read_owned_file(home / relative, home)
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            return (
                State.ACTION,
                "An installed TUM file changed or is missing; review it before rerunning setup.",
            )
    if name not in hook_config.PATHS:
        return (
            State.CONFIGURED,
            "Generic configuration saved; no native client lifecycle is available.",
        )
    if not receipt.hooks:
        return State.ACTION, "Course completion hooks are missing; rerun tum-mcp setup."
    hook_config.writes(name, home, receipt.hooks, receipt.hooks)
    settings = json.loads((home / hook_config.PATHS[name]).read_bytes())
    if name == "claude" and settings.get("disableAllHooks") is True:
        return (
            State.ACTION,
            "Claude hooks are explicitly disabled; setup preserves that preference.",
        )
    if not live:
        return (
            State.CONFIGURED,
            "Registration and hooks match; not checked live.",
        )
    if host != ClientHost.LOCAL:
        return (
            State.CONFIGURED,
            "Registration and hooks match; run tum-mcp doctor on Windows to check it live.",
        )
    from tum_mcp.clients import verification_cache

    path = verification_cache.path_for(receipt)
    identity = verification_cache.fingerprint(receipt)
    if not refresh and (cached := verification_cache.load(path, identity)) is not None:
        return cached
    path.unlink(missing_ok=True)
    state, detail = _inspect_live(name, home, host, receipt)
    verification_cache.save(path, identity, state, detail)
    return state, detail


def _inspect_live(
    name: str, home: Path, host: ClientHost, receipt: Installation
) -> tuple[State, str]:
    root = home / ".codex/plugins/local/tum-mcp"
    try:
        with open(os.devnull, "w") as errors:
            asyncio.run(transport(receipt.server, root, errors))
    except (OSError, TimeoutError, ExceptionGroup, RuntimeError, ValueError):
        return (
            State.ACTION,
            "The registered MCP transport failed initialization or tool discovery; rerun setup.",
        )
    if name == "codex":
        from tum_mcp.clients.codex_runtime import verify
        from tum_mcp.clients.rendering import codex_cache_note

        if note := codex_cache_note(home):
            return State.ACTION, note
        return State.READY, verify(home, host) + " TUM tools found."
    if name == "claude":
        executable = shutil.which("claude")
        command = [executable, "mcp", "get", "tum"] if executable else None
    elif name == "cursor":
        executable = shutil.which("cursor-agent")
        command = [executable, "mcp", "list-tools", "tum"] if executable else None
    else:
        command = None
    if command is None:
        return (
            State.CONFIGURED,
            "TUM tools found; loading inside the app was not checked because its CLI is missing.",
        )
    result = subprocess.run(  # noqa: S603
        command,
        cwd=home,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    connected = (
        re.search(r"\bconnected\b", result.stdout, re.IGNORECASE) is not None
        and re.search(r"\bnot\s+connected\b", result.stdout, re.IGNORECASE) is None
        if name == "claude"
        else "moodle_list_courses" in result.stdout
    )
    if result.returncode or not connected:
        return (
            State.ACTION,
            "MCP transport passed, but native client registration was not confirmed; "
            "inspect its TUM server and workspace permissions.",
        )
    return State.READY, (
        "Loaded by the app with its TUM tools and course hooks; "
        "the app's workspace trust settings still apply."
    )


def setup_check(name: str, home: Path, host: ClientHost) -> tuple[State, str]:
    """Explicit installation authorizes only this owned registration and its guard."""
    try:
        if name == "codex":
            from tum_mcp.clients.codex_runtime import verify

            verify(home, host, install=True)
        return inspect(name, home, host, live=True, refresh=True)
    except CampusError as error:
        return (
            State.ACTION,
            f"Registration saved; live verification needs attention: {error.message}",
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return (
            State.ACTION,
            "Registration saved; live client verification could not finish. Run tum-mcp doctor.",
        )
