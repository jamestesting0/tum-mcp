import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from tum_mcp import __version__
from tum_mcp.client_hosts import ClientHost, client_launch
from tum_mcp.client_installs import ClientName, Installation, receipt_path
from tum_mcp.clients import client_config_path, install_client
from tum_mcp.errors import CampusError
from tum_mcp.skill_catalog import CURRENT_SKILLS
from tum_mcp.skills import customize_skill, export_pack
from tum_mcp.uninstall import uninstall_client
from tum_mcp.updates import refresh_clients


@dataclass(frozen=True, slots=True)
class SkillClient:
    name: ClientName
    home: Path
    skills: Path


@pytest.fixture(params=["cursor", "antigravity"])
def client(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SkillClient:
    home = tmp_path / "profile München"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr("tum_mcp.updates.is_wsl", lambda: False)
    relative = {"cursor": ".cursor/skills", "antigravity": ".gemini/config/skills"}
    return SkillClient(request.param, home, home / relative[request.param])


def snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        sorted(
            (p.relative_to(root).as_posix(), p.read_bytes()) for p in root.rglob("*") if p.is_file()
        )
    )


def test_update_adopts_mcp_only_receipt_and_installs_all_skills(client: SkillClient) -> None:
    entry = dict(client_launch(ClientHost.LOCAL).entry())
    config = client_config_path(client.name, client.home)
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"mcpServers": {"tum": entry}}), encoding="utf-8")
    old = Installation(
        client=client.name,
        host=ClientHost.LOCAL,
        home=client.home,
        version="0.5.0",
        server=entry,
    )
    record = receipt_path(client.name, ClientHost.LOCAL, client.home)
    record.parent.mkdir(parents=True)
    record.write_text(old.model_dump_json(), encoding="utf-8")

    result = refresh_clients()

    assert result["updated"] == 1 and result["needs_review"] == 0
    assert {p.name for p in client.skills.iterdir()} == set(CURRENT_SKILLS)
    installed = Installation.model_validate_json(record.read_bytes())
    assert installed.version == __version__ and installed.files


def test_skill_update_refreshes_owned_files_and_preserves_extras(client: SkillClient) -> None:
    install_client(client.name, client.home)
    note = client.skills / "read-content/personal-note.txt"
    note.write_text("Keep my note.", encoding="utf-8")
    custom = customize_skill("read-content") / "SKILL.md"
    updated = custom.read_text(encoding="utf-8") + "\nPrefer short explanations.\n"
    custom.write_text(updated, encoding="utf-8")

    result = refresh_clients()

    assert result["updated"] == 1 and result["needs_review"] == 0
    assert (client.skills / "read-content/SKILL.md").read_text(encoding="utf-8") == updated
    assert note.read_text(encoding="utf-8") == "Keep my note."
    assert custom.read_text(encoding="utf-8") == updated


def test_update_prunes_retired_skill_assets(client: SkillClient) -> None:
    custom = customize_skill("read-content")
    retired = custom / "assets/retired/example.txt"
    retired.parent.mkdir(parents=True)
    retired.write_text("Synthetic retired asset.", encoding="utf-8")
    install_client(client.name, client.home)
    retired.unlink()

    install_client(client.name, client.home)

    assert not (client.skills / "read-content/assets").exists()
    assert (client.skills / "read-content/SKILL.md").is_file()


@pytest.mark.parametrize(
    "relative", ["read-content/SKILL.md", "prepare-study/assets/site/styles.css"]
)
def test_edited_managed_files_block_update_and_uninstall(
    client: SkillClient, relative: str
) -> None:
    install_client(client.name, client.home)
    edited = client.skills / relative
    edited.write_bytes(edited.read_bytes() + b"\nPersonal edit.\n")
    before = snapshot(client.home)
    record = receipt_path(client.name, ClientHost.LOCAL, client.home)
    receipt = record.read_bytes()

    result = refresh_clients()
    assert result["updated"] == 0 and result["needs_review"] == 1
    with pytest.raises(CampusError, match="Customized"):
        uninstall_client(client.name, client.home)

    assert snapshot(client.home) == before
    assert record.read_bytes() == receipt


def test_setup_preserves_preexisting_conflicting_skills(client: SkillClient) -> None:
    existing = client.skills / "prepare-study/SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("My own teaching workflow.", encoding="utf-8")
    before = snapshot(client.home)

    with pytest.raises(CampusError, match="Existing customized file"):
        install_client(client.name, client.home)

    assert snapshot(client.home) == before


def test_uninstall_prunes_owned_folders_but_keeps_user_files(client: SkillClient) -> None:
    install_client(client.name, client.home)
    personal = client.skills / "personal-skill/SKILL.md"
    personal.parent.mkdir()
    personal.write_text("Personal workflow.", encoding="utf-8")
    note = client.skills / "read-content/personal-note.txt"
    note.write_text("Keep my note.", encoding="utf-8")

    assert uninstall_client(client.name, client.home)

    assert snapshot(client.skills) == (
        ("personal-skill/SKILL.md", b"Personal workflow."),
        ("read-content/personal-note.txt", b"Keep my note."),
    )
    assert not any(
        (client.skills / name).exists() for name in CURRENT_SKILLS if name != "read-content"
    )
    assert not uninstall_client(client.name, client.home)


def test_uninstall_without_receipt_preserves_manually_exported_skills(
    client: SkillClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = client_config_path(client.name, client.home)
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"mcpServers": {"tum": dict(client_launch(ClientHost.LOCAL).entry())}}),
        encoding="utf-8",
    )
    export_pack(client.skills)
    before = snapshot(client.skills)
    monkeypatch.setattr(
        "tum_mcp.uninstall.rendered_client", lambda *args: pytest.fail("No skill export needed")
    )

    assert uninstall_client(client.name, client.home)

    assert snapshot(client.skills) == before
    assert "tum" not in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]


@pytest.mark.parametrize(
    "relative",
    ["../outside", "personal-skill/SKILL.md", "read-content/../../outside", "read-content"],
)
def test_receipt_cannot_claim_paths_outside_managed_skills(
    client: SkillClient, relative: str
) -> None:
    name = client.skills.relative_to(client.home).as_posix() + "/" + relative
    with pytest.raises(CampusError, match="Invalid managed installation paths"):
        Installation(
            client=client.name,
            host=ClientHost.LOCAL,
            home=client.home,
            version=__version__,
            server={},
            files={name: "a" * 64},
        )


def test_symbolic_skill_directory_is_preserved(client: SkillClient, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    note = outside / "personal-note.txt"
    note.write_text("Keep my note.", encoding="utf-8")
    client.skills.parent.mkdir(parents=True)
    try:
        client.skills.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This platform/profile cannot create symlinks.")

    with pytest.raises(CampusError, match="symbolic link"):
        install_client(client.name, client.home)

    assert snapshot(outside) == (("personal-note.txt", b"Keep my note."),)
    assert not client_config_path(client.name, client.home).exists()
