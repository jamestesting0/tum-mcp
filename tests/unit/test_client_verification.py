import json
from pathlib import Path

import pytest

from tum_mcp.clients import codex_runtime, install_client, verification
from tum_mcp.clients.hosts import ClientHost
from tum_mcp.commands.ui import State
from tum_mcp.errors import CampusError


@pytest.fixture
def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(codex_runtime.shutil, "which", lambda _: None)
    home = tmp_path / "client profile"
    install_client("codex", home, announce=False)
    return home


def test_codex_setup_uses_native_hashes_for_only_its_exact_hooks(
    profile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definitions = json.loads((profile / ".codex/hooks.json").read_bytes())["hooks"]
    commands = [entries[0]["hooks"][0]["command"] for entries in definitions.values()]
    hooks = [
        {
            "key": f"native-key-{n}",
            "source": "user",
            "sourcePath": str(profile / ".codex/hooks.json"),
            "command": command,
            "enabled": True,
            "currentHash": "sha256:" + str(n) * 64,
            "trustStatus": "untrusted",
        }
        for n, command in enumerate(commands)
    ]
    foreign = dict(hooks[0], key="another-plugin", command="do-not-trust-me")
    edits = []

    class Native:
        def __init__(self, home: Path) -> None:
            assert home == profile

        def call(self, method: str, params: dict) -> dict:
            if method == "hooks/list":
                return {"data": [{"hooks": [*hooks, foreign]}]}
            if method == "config/batchWrite":
                edits.extend(params["edits"])
                for hook in hooks:
                    hook["trustStatus"] = "trusted"
            return {"plugin": {"summary": {"enabled": True}}}

        def close(self) -> None:
            pass

    monkeypatch.setattr(codex_runtime, "Runtime", Native)
    assert "trusted" in codex_runtime.verify(profile, ClientHost.LOCAL, install=True)
    assert edits == [
        {
            "keyPath": "hooks.state",
            "value": {h["key"]: {"trusted_hash": h["currentHash"]} for h in hooks},
            "mergeStrategy": "upsert",
        }
    ]
    assert foreign["trustStatus"] == "untrusted"

    hooks[0]["enabled"] = False
    edits.clear()
    with pytest.raises(CampusError, match="preserves disabled"):
        codex_runtime.verify(profile, ClientHost.LOCAL, install=True)
    assert edits == []

    hooks[0]["enabled"] = True
    hooks[0].pop("currentHash")
    with pytest.raises(CampusError, match="unsupported registration response"):
        codex_runtime.verify(profile, ClientHost.LOCAL, install=True)
    assert edits == []


def test_static_client_verification_never_launches_a_transport(
    profile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden(*args):
        pytest.fail("--static launched MCP")

    monkeypatch.setattr(verification, "transport", forbidden)
    state, detail = verification.inspect("codex", profile, ClientHost.LOCAL, live=False)
    assert state == State.CONFIGURED and "not checked" in detail
    target = profile / ".codex/plugins/local/tum-mcp/scripts/course-task.mjs"
    target.write_text("modified")
    assert verification.inspect("codex", profile, ClientHost.LOCAL, live=True)[0] == State.ACTION


def test_live_transport_cannot_be_reported_as_native_host_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "antigravity-profile"
    install_client("antigravity", home, announce=False)
    called = []

    async def connected(*args):
        called.append(True)

    monkeypatch.setattr(verification, "transport", connected)
    state, detail = verification.inspect("antigravity", home, ClientHost.LOCAL, live=True)
    assert called == [True]
    assert state == State.CONFIGURED and "unverified" in detail

    settings = home / ".gemini/config/mcp_config.json"
    value = json.loads(settings.read_bytes())
    value["mcpServers"]["tum"]["command"] = "unowned-executable"
    settings.write_text(json.dumps(value))
    called.clear()
    assert verification.inspect("antigravity", home, ClientHost.LOCAL, live=True)[0] == State.ACTION
    assert called == []


@pytest.mark.parametrize("state", [State.READY, State.ACTION, State.CONFIGURED])
def test_setup_shows_the_actual_client_verification_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: State
) -> None:
    from typer.testing import CliRunner

    from tum_mcp.cli import app

    monkeypatch.setattr("tum_mcp.clients.client_home", lambda *args: tmp_path / "profile")
    detail = "TUM guard requires host review." if state == State.ACTION else "TUM guard checked."
    monkeypatch.setattr(verification, "inspect", lambda *args, **kwargs: (state, detail))

    result = CliRunner().invoke(app, ["setup", "--client", "claude"])

    assert result.exit_code == 0, result.output
    assert detail in result.output
    assert state.value in result.output
    if state != State.READY:
        assert "Updated" not in result.output
