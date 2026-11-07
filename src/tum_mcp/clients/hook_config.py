"""Own only TUM hook entries in native clients' shared settings."""

import json
from pathlib import Path

from pydantic import JsonValue

from tum_mcp.clients import hosts
from tum_mcp.clients.hooks import launcher, script_command
from tum_mcp.clients.hosts import ClientHost, StdioLaunch
from tum_mcp.clients.installs import MANAGED_ROOTS, Write, read_owned_file
from tum_mcp.errors import CampusError, Code

PATHS = {
    "codex": ".codex/hooks.json",
    "claude": ".claude/settings.json",
    "cursor": ".cursor/hooks.json",
    "antigravity": ".gemini/config/hooks.json",
}


def render(
    name: str, home: Path, launch: StdioLaunch, *, host: ClientHost = ClientHost.LOCAL
) -> tuple[dict[str, bytes], dict[str, JsonValue]]:
    if name not in PATHS:
        return {}, {}
    path = MANAGED_ROOTS[name] + (
        "/scripts/course-task.mjs"
        if name == "codex"
        else "/prepare-study/references/course-task.mjs"
    )
    script = str(home / path)
    if host == ClientHost.WINDOWS:
        script = hosts.wsl_path(script, windows=True)
    command = script_command(script)
    if name == "cursor":
        definitions = {
            event: [
                {
                    "command": f"{command} --event {event}",
                    **({"loop_limit": 20} if event == "stop" else {}),
                }
            ]
            for event in ("sessionStart", "stop", "sessionEnd")
        }
    elif name == "antigravity":
        definitions = {
            "tum-mcp-course": {
                event: [{"type": "command", "command": f"{command} --event {event}", "timeout": 30}]
                for event in ("SessionStart", "Stop")
            }
        }
    else:
        definitions = {
            event: [
                {
                    "hooks": [
                        {"type": "command", "command": f"{command} --event {event}", "timeout": 30}
                    ]
                }
            ]
            for event in (
                ("UserPromptSubmit", "Stop", "Interrupt")
                if name == "codex"
                else ("UserPromptSubmit", "Stop", "StopFailure", "SessionEnd")
            )
        }
    return {path: launcher(launch, name)}, definitions


def writes(
    name: str, home: Path, desired: dict[str, JsonValue], previous: dict[str, JsonValue]
) -> tuple[Write, ...]:
    if name not in PATHS or not (desired or previous):
        return ()
    target = home / PATHS[name]
    before = read_owned_file(target, home)
    try:
        value = json.loads(before) if before else {}
    except (ValueError, UnicodeError):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Invalid hook settings were preserved."
        ) from None
    if not isinstance(value, dict) or (
        name != "antigravity" and not isinstance(value.get("hooks", {}), dict)
    ):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Invalid hook settings were preserved.")
    hooks = dict(value if name == "antigravity" else value.get("hooks", {}))
    for event in previous.keys() | desired.keys():
        old, new, current = previous.get(event), desired.get(event), hooks.get(event)
        if name == "antigravity":
            if current is not None and current not in (old, new):
                raise CampusError(Code.WORKSPACE_CONFLICT, "Customized TUM hooks were preserved.")
            if old is not None and current != old:
                raise CampusError(Code.WORKSPACE_CONFLICT, "Removed TUM hooks were preserved.")
            if new is None:
                hooks.pop(event, None)
            else:
                hooks[event] = new
            continue
        current = list(current) if isinstance(current, list) else [] if current is None else None
        if current is None:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Invalid hook event settings were preserved."
            )
        insertion = len(current)
        for entry in old or []:
            if current.count(entry) != 1:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Customized or removed TUM hooks were preserved."
                )
            insertion = min(insertion, current.index(entry))
            current.remove(entry)
        for entry in new or []:
            if entry not in current:
                current.insert(insertion, entry)
                insertion += 1
        if current:
            hooks[event] = current
        else:
            hooks.pop(event, None)
    if name == "antigravity":
        value = hooks
    elif hooks:
        value["hooks"] = hooks
    else:
        value.pop("hooks", None)
    if name == "cursor" and desired:
        value.setdefault("version", 1)
    after = (json.dumps(value, indent=2) + "\n").encode() if value else None
    return (Write(target, before, after),)
