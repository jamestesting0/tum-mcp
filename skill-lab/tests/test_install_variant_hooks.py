import hashlib
import json
import sys

import pytest
from skill_lab import install_variant


@pytest.fixture
def native_runtime(monkeypatch):
    from tum_mcp.clients import codex_runtime

    instances = []

    class Runtime:
        def __init__(self, home):
            self.home, self.trusted, self.closed, self.disabled = home, {}, False, False
            instances.append(self)

        def call(self, method, params):
            if method == "initialize":
                return {}
            if method == "config/batchWrite":
                self.trusted.update(params["edits"][0]["value"])
                return {}
            assert method == "hooks/list"
            path = self.home / ".codex/hooks.json"
            entries = json.loads(path.read_text())["hooks"]
            return {
                "data": [
                    {
                        "hooks": [
                            {
                                "key": event + str(index),
                                "source": "user",
                                "sourcePath": str(path),
                                "command": item["hooks"][0]["command"],
                                "enabled": not self.disabled,
                                "currentHash": "sha256:"
                                + hashlib.sha256(item["hooks"][0]["command"].encode()).hexdigest(),
                                "trustStatus": "trusted"
                                if event + str(index) in self.trusted
                                else "untrusted",
                            }
                            for event, hooks in entries.items()
                            for index, item in enumerate(hooks)
                        ]
                    }
                ]
            }

        def close(self):
            self.closed = True

    monkeypatch.setattr(codex_runtime, "Runtime", Runtime)
    return instances


def test_trial_guard_uses_candidate_backend_and_preserves_unrelated_hooks(tmp_path, native_runtime):
    home = tmp_path / "lab-home"
    path = home / ".codex/hooks.json"
    path.parent.mkdir(parents=True)
    stale = {"hooks": [{"type": "command", "command": "node older-owned-script.mjs"}]}
    path.write_text(json.dumps({"hooks": {"Stop": [stale]}}))
    installed = install_variant.install_course_hooks(home)
    runtime = native_runtime[0]
    assert runtime.closed and len(runtime.trusted) == 3
    assert "Stop0" not in runtime.trusted
    script = next(home / item for item in installed if item.endswith(".mjs"))
    assert json.dumps(sys.executable) in script.read_text()
    assert '"study", "task", "hook"' in script.read_text()
    hooks = json.loads(path.read_text())["hooks"]
    assert hooks["Stop"][0] == stale and len(hooks["Stop"]) == 2
    (home / install_variant.MARKER).write_text(json.dumps({"paths": installed}))
    install_variant.remove_previous(home)
    assert json.loads(path.read_text()) == {"hooks": {"Stop": [stale]}}
    assert not script.exists()


def test_disabled_candidate_guard_cannot_start_a_trial(tmp_path, native_runtime, monkeypatch):
    from tum_mcp.clients import codex_runtime

    constructor = codex_runtime.Runtime

    def disabled(home):
        runtime = constructor(home)
        runtime.disabled = True
        return runtime

    monkeypatch.setattr(codex_runtime, "Runtime", disabled)
    with pytest.raises(RuntimeError, match="enabled course guards"):
        install_variant.install_course_hooks(tmp_path)
    assert native_runtime[0].closed and not native_runtime[0].trusted


def test_previous_standard_interrupt_timeout_is_replaced_not_duplicated(tmp_path, native_runtime):
    from tum_mcp.clients.hook_config import render
    from tum_mcp.clients.hosts import StdioLaunch

    _, previous = render("codex", tmp_path, StdioLaunch(sys.executable, ("-m", "old", "serve")))
    previous["Interrupt"][0]["hooks"][0]["timeout"] = 30
    path = tmp_path / ".codex/hooks.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"hooks": previous}))
    install_variant.install_course_hooks(tmp_path)
    current = json.loads(path.read_text())["hooks"]
    assert all(len(entries) == 1 for entries in current.values())
    assert current["Interrupt"][0]["hooks"][0]["timeout"] == 3
    assert len(native_runtime[0].trusted) == 3
