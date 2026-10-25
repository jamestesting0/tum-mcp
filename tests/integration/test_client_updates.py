import json
import sys
from pathlib import Path

import pytest

from tum_mcp import skills
from tum_mcp.clients import client_config_path, install_client
from tum_mcp.skill_catalog import CURRENT_SKILLS


@pytest.fixture(scope="module")
def transaction_skill_pack(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Exercise ownership transactions without reinstalling the full teaching site."""
    root = tmp_path_factory.mktemp("transaction-skills")
    for name in CURRENT_SKILLS:
        skill = root / name
        (skill / "assets").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Synthetic transaction fixture.\n---\n",
            encoding="utf-8",
        )
        (skill / "assets/payload.bin").write_bytes(b"\x00\xffsynthetic-owned-asset")
    return root


@pytest.fixture(autouse=True)
def use_transaction_skill_pack(
    transaction_skill_pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Full pack/metadata/export fidelity belongs to campus-client, migration and
    # installed-consumer checks. These cases own rollback and preservation rules.
    monkeypatch.setattr(skills, "bundled", lambda: transaction_skill_pack)


@pytest.mark.parametrize("name", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_managed_client_updates_to_a_new_runtime_without_losing_other_settings(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an unchanged managed registration from the previous runtime.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    install_client(name, home)
    path = client_config_path(name, home)
    before = json.loads(path.read_text(encoding="utf-8"))
    before["unrelated"] = {"keep": "München"}
    path.write_text(json.dumps(before), encoding="utf-8")
    previous_python = sys.executable
    next_python = str(tmp_path / "next-runtime/python")
    monkeypatch.setattr(sys, "executable", next_python)
    # When setup refreshes the same client against the new runtime.
    install_client(name, home)
    # Then the registration/launcher advances and unrelated settings survive.
    configured = json.loads(path.read_text(encoding="utf-8"))
    assert configured["unrelated"] == before["unrelated"]
    if name == "codex":
        wrapper = (path.parent / "scripts/serve.mjs").read_text(encoding="utf-8")
        assert json.dumps(next_python) in wrapper and json.dumps(previous_python) not in wrapper
    else:
        assert configured["mcpServers"]["tum"]["command"] == next_python


@pytest.mark.parametrize("name", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_customized_mcp_entry_is_preserved_before_any_update_writes(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.errors import CampusError

    # Given a managed client whose entry the user has subsequently customized.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    install_client(name, home)
    path = client_config_path(name, home)
    current = json.loads(path.read_text(encoding="utf-8"))
    current["mcpServers"]["tum"]["env"] = {"USER_CHOICE": "synthetic-preference"}
    path.write_text(json.dumps(current))
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "executable", str(tmp_path / "next/python"))
    # When an update encounters the edited entry.
    with pytest.raises(CampusError, match="customized"):
        install_client(name, home)
    # Then no registration, skill or launcher is overwritten.
    assert {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("name", ["codex", "claude", "cursor", "antigravity"])
def test_customized_skill_blocks_its_client_without_overwriting_any_file(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.errors import CampusError

    # Given an installed site skill with a user's direct edit.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    install_client(name, home)
    skill = next(home.rglob("read-content/SKILL.md"))
    skill.write_text(skill.read_text(encoding="utf-8") + "\nPersonal instruction to retain.\n")
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "executable", str(tmp_path / "next/python"))
    # When the runtime and bundled files are refreshed.
    with pytest.raises(CampusError, match="Customized"):
        install_client(name, home)
    # Then the entire client remains on its previous coherent files.
    assert {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("name", ["codex", "claude", "cursor", "antigravity"])
def test_failed_client_write_rolls_back_already_written_managed_files(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp import client_installs
    from tum_mcp.errors import CampusError

    # Given a changed runtime and a write error after its launcher would change.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    install_client(name, home)
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    from tum_mcp.client_hosts import ClientHost

    target = client_installs.receipt_path(name, ClientHost.LOCAL, home)
    write = client_installs.private_write
    failed = False

    def fail_once(path: Path, content: bytes) -> None:
        nonlocal failed
        if path == target and not failed:
            failed = True
            raise PermissionError("synthetic write failure")
        write(path, content)

    monkeypatch.setattr(client_installs, "private_write", fail_once)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "next/python"))
    # When activation fails midway.
    with pytest.raises(CampusError, match="restored"):
        install_client(name, home)
    # Then the prior managed launcher and all client content are restored.
    assert failed
    assert {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()} == before


def test_update_continues_other_clients_but_reports_a_customized_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.updates import refresh_clients

    # Given two clients, one with a customized registration, and unrelated saved data.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    for name in ("cursor", "antigravity"):
        install_client(name, home)
    cursor = client_config_path("cursor", home)
    custom = {"mcpServers": {"tum": {"command": "user-custom-launcher"}}}
    cursor.write_text(json.dumps(custom))
    saved = tmp_path / "data/credentials/local/synthetic.enc"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"synthetic-encrypted-record-to-retain")
    next_python = str(tmp_path / "next/python")
    monkeypatch.setattr(sys, "executable", next_python)
    # When the update refreshes previously configured clients.
    result = refresh_clients()
    # Then the intact client advances, the conflict is reported, and saved data survives.
    assert result["updated"] == 1 and result["needs_review"] == 1
    assert json.loads(cursor.read_text(encoding="utf-8")) == custom
    assert (
        json.loads(client_config_path("antigravity", home).read_text(encoding="utf-8"))[
            "mcpServers"
        ]["tum"]["command"]
        == next_python
    )
    assert saved.read_bytes() == b"synthetic-encrypted-record-to-retain"


def test_uninstalled_client_is_not_recreated_by_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.uninstall import uninstall_client
    from tum_mcp.updates import refresh_clients

    # Given a configured client that has been explicitly removed.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    install_client("cursor", home)
    uninstall_client("cursor", home)
    # When other installed clients are refreshed.
    result = refresh_clients()
    # Then this client stays removed.
    assert result["updated"] == 0 and result["needs_review"] == 0
    assert (
        "tum"
        not in json.loads(client_config_path("cursor", home).read_text(encoding="utf-8"))[
            "mcpServers"
        ]
    )


def test_native_registration_binds_the_selected_data_and_download_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given custom local storage chosen during setup, independent of the desktop host's environment.
    variables = {
        "TUM_MCP_DATA_DIR": tmp_path / "campus",
        "TUM_MCP_CONFIG_DIR": tmp_path / "configuration",
        "TUM_MOODLE_DATA_DIR": tmp_path / "moodle",
        "TUM_MOODLE_DOWNLOAD_DIR": tmp_path / "downloads",
    }
    for key, path in variables.items():
        monkeypatch.setenv(key, str(path))
    home = tmp_path / "profile"
    # When the client is registered for a desktop launch.
    install_client("cursor", home)
    entry = json.loads(client_config_path("cursor", home).read_text(encoding="utf-8"))[
        "mcpServers"
    ]["tum"]
    # Then the desktop launch carries the same nonsecret storage paths.
    assert entry.get("env") == {key: str(path.resolve()) for key, path in variables.items()}


def test_update_does_not_silently_downgrade_a_newer_managed_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.client_hosts import ClientHost
    from tum_mcp.client_installs import receipt_path
    from tum_mcp.errors import CampusError

    # Given a newer managed installation recorded by another package version.
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "profile"
    install_client("cursor", home)
    record = receipt_path("cursor", ClientHost.LOCAL, home)
    receipt = json.loads(record.read_text(encoding="utf-8"))
    receipt["version"] = "99.0.0"
    record.write_text(json.dumps(receipt))
    before = client_config_path("cursor", home).read_bytes()
    # When an older installed package attempts to refresh it.
    with pytest.raises(CampusError, match="newer managed client"):
        install_client("cursor", home)
    # Then its newer registration and record remain untouched.
    assert client_config_path("cursor", home).read_bytes() == before
    assert json.loads(record.read_text(encoding="utf-8"))["version"] == "99.0.0"
