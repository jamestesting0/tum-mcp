import json
from pathlib import Path

import pytest

from tum_mcp.clients import install_client
from tum_mcp.clients.hook_config import PATHS
from tum_mcp.clients.installs import MANAGED_ROOTS
from tum_mcp.errors import CampusError
from tum_mcp.uninstall import uninstall_client


@pytest.mark.parametrize("host", ["codex", "claude", "cursor", "antigravity"])
def test_hook_install_update_and_removal_preserve_unrelated_settings(
    tmp_path: Path, host: str
) -> None:
    home = tmp_path / "profile with spaces"
    target = home / PATHS[host]
    target.parent.mkdir(parents=True)
    other = {"command": "keep-user-hook"}
    event = "stop" if host == "cursor" else "Stop"
    hooks = {"other-plugin": {"Stop": [other]}} if host == "antigravity" else {event: [other]}
    original = (
        dict(hooks, personal={"keep": True})
        if host == "antigravity"
        else {"hooks": hooks, "personal": {"keep": True}}
    )
    if host == "cursor":
        original["version"] = 1
    target.write_text(json.dumps(original))

    install_client(host, home)
    before = target.read_bytes()
    install_client(host, home)
    assert target.read_bytes() == before
    current = json.loads(before)
    assert current["personal"] == original["personal"]
    if host == "codex":
        assert current["hooks"]["Interrupt"][-1]["hooks"][0]["timeout"] == 3
    if host == "antigravity":
        assert current["other-plugin"] == hooks["other-plugin"]
    else:
        assert current["hooks"][event][0] == other
        later = {"command": "user-added-later"}
        current["hooks"][event].append(later)
        target.write_text(json.dumps(current))
        install_client(host, home)
        assert json.loads(target.read_bytes())["hooks"][event] == current["hooks"][event]
        original["hooks"][event].append(later)
    script = (
        home
        / MANAGED_ROOTS[host]
        / (
            "scripts/course-task.mjs"
            if host == "codex"
            else "prepare-study/references/course-task.mjs"
        )
    )
    assert script.is_file()
    assert f'"--host", "{host}"' in script.read_text()

    uninstall_client(host, home)

    assert json.loads(target.read_bytes()) == original
    assert not script.exists()


@pytest.mark.parametrize("host", ["codex", "claude", "cursor", "antigravity"])
def test_customized_hook_definition_is_preserved_on_update_and_uninstall(
    tmp_path: Path, host: str
) -> None:
    home = tmp_path / "profile"
    install_client(host, home)
    target = home / PATHS[host]
    value = json.loads(target.read_bytes())
    if host == "antigravity":
        value["tum-mcp-course"]["Stop"][0]["command"] += " --custom"
    elif host == "cursor":
        value["hooks"]["stop"][0]["command"] += " --custom"
    else:
        value["hooks"]["Stop"][0]["hooks"][0]["command"] += " --custom"
    target.write_text(json.dumps(value))
    before = target.read_bytes()
    for operation in (install_client, uninstall_client):
        with pytest.raises(CampusError, match="preserved"):
            operation(host, home)
        assert target.read_bytes() == before


def test_hook_command_preserves_shell_metacharacters_and_host_arguments(tmp_path: Path) -> None:
    import os
    import shutil
    import subprocess

    from tum_mcp.clients.hooks import script_command

    if not shutil.which("node"):
        pytest.skip("Node.js is unavailable")
    script = tmp_path / "profile $USER 'quoted' `literal` 漢字" / "hook.mjs"
    script.parent.mkdir()
    script.write_text("console.log(JSON.stringify(process.argv.slice(2)))")
    command = script_command(str(script)) + " --event Stop"
    result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)  # noqa: S602
    assert json.loads(result.stdout) == ["--event", "Stop"]
    if os.name == "nt":
        result = subprocess.run(  # noqa: S603 - fixed native shell, synthetic owned hook
            [shutil.which("powershell.exe"), "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout) == ["--event", "Stop"]
