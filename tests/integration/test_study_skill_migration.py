"""Rename lifecycle skills through owned receipts without losing customizations."""

from pathlib import Path

import pytest

from tum_mcp import skills
from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError


def previous_pack(root: Path) -> Path:
    for name in ("init-study", "update-study"):
        skill = root / name
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Previous lifecycle workflow.\n---\n", encoding="utf-8"
        )
        (skill / "references/project.md").write_text(
            "A preserved old reference.\n", encoding="utf-8"
        )
    return root


@pytest.mark.parametrize("client", ["codex", "claude"])
def test_managed_old_skills_are_replaced_by_one_complete_sync_skill(
    client: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    home = tmp_path / "profile"
    old = previous_pack(tmp_path / "old")
    with monkeypatch.context() as old_source:
        old_source.setattr(skills, "bundled", lambda: old)
        install_client(client, home, announce=False)
    old_entries = list(home.rglob("init-study/SKILL.md"))
    assert len(old_entries) == 1
    parent = old_entries[0].parent.parent
    extra = parent / "init-study/personal-note.txt"
    extra.write_bytes(b"Keep this user file")
    install_client(client, home, announce=False)
    assert not (parent / "init-study/SKILL.md").exists()
    assert not (parent / "update-study").exists()
    assert extra.read_bytes() == b"Keep this user file"
    source = skills.bundled() / "sync-study"
    target = parent / "sync-study"
    assert {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()} == {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    first = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    install_client(client, home, announce=False)
    assert {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()} == first


@pytest.mark.parametrize("client", ["codex", "claude"])
def test_customized_old_installed_skill_blocks_the_whole_refresh_without_loss(
    client: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    home = tmp_path / "profile"
    old = previous_pack(tmp_path / "old")
    with monkeypatch.context() as old_source:
        old_source.setattr(skills, "bundled", lambda: old)
        install_client(client, home, announce=False)
    entry = next(home.rglob("update-study/SKILL.md"))
    entry.write_text(
        entry.read_text(encoding="utf-8") + "Personal workflow to retain.\n", encoding="utf-8"
    )
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    with pytest.raises(CampusError, match="Customized or removed client file preserved"):
        install_client(client, home, announce=False)
    assert {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()} == before
    assert not list(home.rglob("sync-study/SKILL.md"))


@pytest.mark.parametrize("name", ["init-study", "update-study"])
def test_old_personal_overrides_remain_intact_with_the_correct_merge_target(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    custom = tmp_path / "config/skills" / name / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"Keep my workflow")
    with pytest.raises(CampusError, match="merge them into sync-study"):
        skills.export_pack(tmp_path / "export")
    assert custom.read_bytes() == b"Keep my workflow"
    assert not (tmp_path / "export").exists()
    with pytest.raises(CampusError, match="retired; use sync-study"):
        skills.selected(name)
