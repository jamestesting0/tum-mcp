import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("include_local_docs", [False, True])
def test_registration_works_outside_home_and_preserves_other_plugins(
    tmp_path: Path, include_local_docs: bool
) -> None:
    root = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "external checkout"
    home = tmp_path / "user home"
    checkout.mkdir()
    for name in ("plugin", "src", "scripts"):
        shutil.copytree(root / name, checkout / name)
    (checkout / "docs").mkdir()
    for name in ("setup.md", "development.md", "tum-mcp.md"):
        shutil.copy2(root / "docs" / name, checkout / "docs" / name)
    if include_local_docs:
        for name in (
            "tum-mcp-handoff.md",
            "credential-storage-options.md",
            "release-workflow.yml.example",
        ):
            (checkout / "docs" / name).write_text("LOCAL_ONLY_DOC_DO_NOT_PACKAGE\n")
        (checkout / "AGENTS.md").write_text("LOCAL_ONLY_AGENT_INSTRUCTIONS\n")
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
    environment = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    command = [sys.executable, str(checkout / "scripts/package_plugin.py"), "--register"]
    subprocess.run(command, env=environment, check=True, capture_output=True)

    installed_source = home / ".codex/plugins/local/tum-moodle"
    assert (installed_source / "src/tum_moodle/__init__.py").is_file()
    assert (installed_source / "assets/tum-logo.png").is_file()
    assert (installed_source / "README.md").read_bytes() == (root / "README.md").read_bytes()
    assert (installed_source / "docs/setup.md").is_file()
    assert (installed_source / "docs/tum-mcp.md").is_file()
    assert not (installed_source / "docs/tum-mcp-handoff.md").exists()
    assert not (installed_source / "docs/credential-storage-options.md").exists()
    assert not (installed_source / "docs/release-workflow.yml.example").exists()
    assert not (installed_source / "AGENTS.md").exists()
    assert (installed_source / "LICENSE").read_bytes() == (root / "LICENSE").read_bytes()
    assert (installed_source / "NOTICE").read_bytes() == (root / "NOTICE").read_bytes()
    assert not (installed_source / ".env").exists()
    assert not (installed_source / "lecture.pdf").exists()
    marketplace = json.loads(marketplace_path.read_text())
    assert marketplace["interface"] == existing["interface"]
    assert marketplace["plugins"][0] == {"name": "other-plugin"}
    plugin = marketplace["plugins"][1]
    assert (home / plugin["source"]["path"]).resolve() == installed_source
    assert "\\" not in plugin["source"]["path"]

    (checkout / "dist/tum-moodle/stale.py").write_text("stale")
    (installed_source / "stale.py").write_text("stale")
    subprocess.run(command, env=environment, check=True, capture_output=True)
    assert not (checkout / "dist/tum-moodle/stale.py").exists()
    assert not (installed_source / "stale.py").exists()
    assert len(json.loads(marketplace_path.read_text())["plugins"]) == 2
