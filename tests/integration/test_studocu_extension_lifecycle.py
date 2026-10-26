from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.extensions import studocu_enabled
from tum_mcp.skills import export_pack


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr("tum_mcp.updates.is_wsl", lambda: False)
    return home


@pytest.mark.parametrize("client", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_install_update_remove(home: Path, tmp_path: Path, client: str) -> None:
    install_client(client, home, announce=False)
    export_pack(tmp_path / "base")
    assert not (tmp_path / "base/sync-studocu").exists()
    runner = CliRunner()
    result = runner.invoke(app, ["install", "studocu"])
    assert result.exit_code == 0, result.output
    assert studocu_enabled()
    export_pack(tmp_path / "enabled")
    assert (tmp_path / "enabled/sync-studocu/SKILL.md").is_file()
    install_client(client, home, announce=False)
    result = runner.invoke(app, ["extensions", "remove", "studocu"])
    assert result.exit_code == 0, result.output
    assert not studocu_enabled()
    export_pack(tmp_path / "removed")
    assert not (tmp_path / "removed/sync-studocu").exists()


def test_customized_skill_is_preserved_and_disabled(home: Path) -> None:
    install_client("cursor", home, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "studocu"]).exit_code == 0
    path = home / ".cursor/skills/sync-studocu/SKILL.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nMy changes.\n", encoding="utf-8")
    result = runner.invoke(app, ["extensions", "remove", "studocu"])
    assert result.exit_code == 0
    assert "disabled_needs_review" in result.output
    assert "My changes" in path.read_text(encoding="utf-8")
    assert not studocu_enabled()


def test_conflict_prevents_activation_across_clients(home: Path) -> None:
    install_client("cursor", home, announce=False)
    install_client("antigravity", home, announce=False)
    conflict = home / ".gemini/config/skills/sync-studocu/SKILL.md"
    conflict.parent.mkdir(parents=True)
    conflict.write_text("Keep this personal skill.", encoding="utf-8")
    result = CliRunner().invoke(app, ["install", "studocu"])
    assert result.exit_code != 0
    assert not studocu_enabled()
    assert not (home / ".cursor/skills/sync-studocu").exists()
    assert conflict.read_text(encoding="utf-8") == "Keep this personal skill."


@pytest.mark.parametrize("first_installed", ["lecture", "studocu"])
@pytest.mark.parametrize("first_removed", ["lecture", "studocu"])
def test_lecture_and_studocu_install_and_remove_independently(
    home: Path, first_installed: str, first_removed: str
) -> None:
    from tum_mcp.extensions import lecture_enabled

    install_client("cursor", home, announce=False)
    runner = CliRunner()
    install_commands = {
        "lecture": ["install", "lecture", "--no-asr"],
        "studocu": ["install", "studocu"],
    }
    second_installed = "studocu" if first_installed == "lecture" else "lecture"
    for name in (first_installed, second_installed):
        result = runner.invoke(app, install_commands[name])
        assert result.exit_code == 0, result.output or repr(result.exception)
    skills = home / ".cursor/skills"
    assert lecture_enabled() and studocu_enabled()
    assert (skills / "prepare-lecture/SKILL.md").is_file()
    assert (skills / "sync-studocu/SKILL.md").is_file()
    commands = {
        "lecture": ["uninstall", "lecture"],
        "studocu": ["extensions", "remove", "studocu"],
    }
    second_removed = "studocu" if first_removed == "lecture" else "lecture"
    result = runner.invoke(app, commands[first_removed])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert lecture_enabled() == (first_removed != "lecture")
    assert studocu_enabled() == (first_removed != "studocu")
    assert (skills / "prepare-lecture/SKILL.md").exists() == (first_removed != "lecture")
    assert (skills / "sync-studocu/SKILL.md").exists() == (first_removed != "studocu")
    result = runner.invoke(app, commands[second_removed])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert not lecture_enabled() and not studocu_enabled()
    assert (skills / "prepare-study/SKILL.md").is_file()
