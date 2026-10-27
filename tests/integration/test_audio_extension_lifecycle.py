import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.extensions import audio_notes_enabled, lecture_enabled, studocu_enabled
from tum_mcp.skills import export_pack, inspect_skills


@pytest.fixture
def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr("tum_mcp.updates.is_wsl", lambda: False)
    return home


@pytest.mark.parametrize("client", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_audio_is_opt_in_and_exports_its_complete_workflow(
    profile: Path,
    tmp_path: Path,
    client: str,
) -> None:
    install_client(client, profile, announce=False)
    assert not audio_notes_enabled()
    assert len(inspect_skills()) == 5
    runner = CliRunner()
    result = runner.invoke(app, ["install", "audio-notes"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert audio_notes_enabled()
    destination = tmp_path / "export"
    export_pack(destination)
    assert (destination / "audio-notes/references/voices.md").is_file()
    assert (destination / "audio-notes/references/workflow.md").is_file()
    report = json.loads(runner.invoke(app, ["doctor", "--json"]).output)
    assert (
        next(item["state"] for item in report["runtime"] if item["label"] == "Audio Notes")
        == "Enabled"
    )


@pytest.mark.parametrize("first", ["studocu", "audio-notes"])
def test_all_three_extensions_preserve_each_others_selection(profile: Path, first: str) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    second = "audio-notes" if first == "studocu" else "studocu"
    for name in ("lecture", first, second):
        command = ["install", name, *(["--no-asr"] if name == "lecture" else [])]
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output or repr(result.exception)
    assert audio_notes_enabled() and lecture_enabled() and studocu_enabled()
    assert len(inspect_skills()) == 8
    result = runner.invoke(app, ["uninstall", "studocu"])
    assert result.exit_code == 0, result.output
    assert audio_notes_enabled() and lecture_enabled() and not studocu_enabled()
    result = runner.invoke(app, ["uninstall", "audio-notes"])
    assert result.exit_code == 0, result.output
    assert lecture_enabled() and not audio_notes_enabled()


def test_audio_removal_preserves_recordings_and_customized_workflow(profile: Path) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "audio-notes"]).exit_code == 0
    recording = profile / "course/audio/01-topic.m4a"
    recording.parent.mkdir(parents=True)
    recording.write_bytes(b"synthetic-personal-audio")
    skill = profile / ".cursor/skills/audio-notes/SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nPersonal voice preference.\n", encoding="utf-8"
    )
    before = skill.read_bytes()
    result = runner.invoke(app, ["uninstall", "audio-notes"])
    assert result.exit_code == 2
    assert not audio_notes_enabled()
    assert skill.read_bytes() == before
    assert recording.read_bytes() == b"synthetic-personal-audio"
    assert (profile / ".cursor/skills/prepare-study/SKILL.md").is_file()


def test_invalid_audio_customization_cannot_activate_the_extension(
    profile: Path, tmp_path: Path
) -> None:
    install_client("cursor", profile, announce=False)
    override = tmp_path / "config/skills/audio-notes/SKILL.md"
    override.parent.mkdir(parents=True)
    override.write_text("invalid", encoding="utf-8")
    result = CliRunner().invoke(app, ["install", "audio-notes"])
    assert result.exit_code != 0
    assert not audio_notes_enabled()
    assert not (profile / ".cursor/skills/audio-notes").exists()
