import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.client_config import client_config_path
from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError
from tum_mcp.removal import remove_clients
from tum_mcp.runtime_leases import require_idle_runtimes, runtime_lease
from tum_moodle import auth


@pytest.fixture
def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(auth, "system_keyring", lambda: pytest.fail("No native-store access"))
    return home


def test_all_removal_retires_managed_files_and_preserves_custom_files_and_saved_data(
    profile: Path, tmp_path: Path
) -> None:
    # Given all five configured clients, plus unrelated work and saved state.
    for name in ("codex", "claude", "cursor", "antigravity", "generic"):
        install_client(name, profile)
    note = profile / ".codex/plugins/local/tum-mcp/personal-note.txt"
    note.write_text("keep my note")
    saved = tmp_path / "data/credentials/local/session.key"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"synthetic-key-to-retain")
    work = profile / "University/assignment/Main.java"
    work.parent.mkdir(parents=True)
    work.write_text("class Main {}")
    # When all managed clients are removed.
    result = CliRunner().invoke(app, ["uninstall", "--all"])
    # Then managed entries/skills disappear while personal files and sessions remain.
    assert result.exit_code == 0, result.output
    assert note.read_text() == "keep my note" and work.is_file()
    assert saved.read_bytes() == b"synthetic-key-to-retain"
    assert not (profile / ".claude/skills/read-content").exists()
    assert not (profile / ".codex/plugins/local/tum-mcp/plugin.json").exists()
    for name in ("claude", "cursor", "antigravity"):
        assert "tum" not in json.loads(client_config_path(name, profile).read_text())["mcpServers"]
    assert "npm uninstall" in result.output


def test_credential_forgetting_deletes_only_local_service_records(
    profile: Path, tmp_path: Path
) -> None:
    # Given synthetic local credentials and an older Moodle/native-store record.
    local = tmp_path / "data/credentials/local"
    local.mkdir(parents=True)
    (local / ("a" * 64 + ".enc")).write_bytes(b"synthetic-ciphertext")
    (local / "session.key").write_bytes(b"synthetic-key")
    moodle = tmp_path / "moodle"
    (moodle / "local-session").mkdir(parents=True)
    (moodle / "session.enc").write_bytes(b"legacy-record-to-preserve")
    for name in ("session.enc", "session.key"):
        (moodle / "local-session" / name).write_bytes(b"synthetic-local-record")
    # When explicit local credential forgetting is requested.
    remove_clients(forget_credentials=True)
    # Then local secrets disappear and the legacy record stays intact.
    assert not tuple(local.glob("*.enc")) and not (local / "session.key").exists()
    assert not (moodle / "local-session/session.enc").exists()
    assert not (moodle / "local-session/session.key").exists()
    assert (moodle / "session.enc").read_bytes() == b"legacy-record-to-preserve"


def test_running_managed_backend_blocks_runtime_cleanup(
    profile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an active managed backend lease.
    import os
    import sys

    from tum_mcp.settings import data_path

    executable = (
        data_path()
        / "runtimes"
        / ("a" * 64)
        / "env-fixture"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"synthetic-interpreter-not-executed")
    monkeypatch.setattr(sys, "executable", str(executable))
    with runtime_lease():
        # When cleanup checks for running clients.
        with pytest.raises(CampusError, match="still running"):
            require_idle_runtimes()
    # Then releasing the backend permits cleanup.
    require_idle_runtimes()


def test_cleanup_refuses_runtime_paths_that_overlap_assignment_work(
    profile: Path, tmp_path: Path
) -> None:
    # Given a user-selected assignment root inside the runtime namespace.
    config = tmp_path / "data/config"
    config.mkdir(parents=True)
    (config / "preferences.json").write_text(
        json.dumps({"workspace_root": str(tmp_path / "data/runtimes/assignment")})
    )
    # When automatic runtime cleanup is requested.
    with pytest.raises(CampusError, match="overlap user work"):
        remove_clients(purge_runtime=True)
    # Then no assignment path or cleanup marker is created/deleted.
    assert not (tmp_path / "data/runtime-removal.pending").exists()


def test_destructive_cleanup_options_require_explicit_all_selection(profile: Path) -> None:
    # Given no all-clients removal request.
    # When a credential cleanup option accompanies one client only.
    result = CliRunner().invoke(app, ["uninstall", "--client", "cursor", "--forget-credentials"])
    # Then the request is rejected before any credentials are changed.
    assert result.exit_code != 0 and "requires --all" in str(result.exception)
