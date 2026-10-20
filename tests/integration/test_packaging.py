import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_registration_works_outside_home_and_preserves_other_plugins(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "external checkout"
    home = tmp_path / "user home"
    checkout.mkdir()
    for name in ("plugin", "src", "scripts"):
        shutil.copytree(root / name, checkout / name)
    for name in ("pyproject.toml", "uv.lock", "README.md", ".python-version", "LICENSE", "NOTICE"):
        shutil.copy2(root / name, checkout / name)
    (checkout / ".env").write_text("PRIVATE_TEST_VALUE=do-not-package\n")
    (checkout / "lecture.pdf").write_bytes(b"private course material")
    marketplace_path = home / ".agents/plugins/marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    existing = {
        "name": "personal-local",
        "interface": {"displayName": "My tools"},
        "plugins": [{"name": "other-plugin"}],
    }
    marketplace_path.write_text(json.dumps(existing))
    environment = {**os.environ, "HOME": str(home)}
    command = [sys.executable, str(checkout / "scripts/package_plugin.py"), "--register"]
    subprocess.run(command, env=environment, check=True, capture_output=True)

    installed_source = home / ".codex/plugins/local/tum-moodle"
    assert (installed_source / "src/tum_moodle/__init__.py").is_file()
    assert (installed_source / "assets/tum-logo.png").is_file()
    assert (installed_source / "LICENSE").read_bytes() == (root / "LICENSE").read_bytes()
    assert (installed_source / "NOTICE").read_bytes() == (root / "NOTICE").read_bytes()
    assert not (installed_source / ".env").exists()
    assert not (installed_source / "lecture.pdf").exists()
    marketplace = json.loads(marketplace_path.read_text())
    assert marketplace["interface"] == existing["interface"]
    assert marketplace["plugins"][0] == {"name": "other-plugin"}
    plugin = marketplace["plugins"][1]
    assert (home / plugin["source"]["path"]).resolve() == installed_source

    (checkout / "dist/tum-moodle/stale.py").write_text("stale")
    (installed_source / "stale.py").write_text("stale")
    subprocess.run(command, env=environment, check=True, capture_output=True)
    assert not (checkout / "dist/tum-moodle/stale.py").exists()
    assert not (installed_source / "stale.py").exists()
    assert len(json.loads(marketplace_path.read_text())["plugins"]) == 2


def test_bootstrap_finds_intel_homebrew_and_uses_locked_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setattr(Path, "is_file", lambda path: str(path) == "/usr/local/bin/uv")

    def run(command: list[str], *, env: dict[str, str], check: bool) -> None:
        assert check
        assert env["UV_PROJECT_ENVIRONMENT"] == str(
            tmp_path / "Library/Application Support/TUMMoodle/runtime"
        )
        calls.append(command)

    monkeypatch.setattr(subprocess, "run", run)
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "plugin/scripts/bootstrap.py"))
    assert len(calls) == 1
    assert calls[0][0] == "/usr/local/bin/uv"
    assert {"--locked", "--no-dev", "--no-editable"} <= set(calls[0])
