"""Shared lifecycle of the optional media workflows; lecture and course memory keep their own."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.extensions import audio_notes_enabled, lecture_enabled, video_notes_enabled
from tum_mcp.skills import export_pack, inspect_skills


@dataclass(frozen=True)
class Extension:
    label: str
    enabled: Callable[[], bool]
    files: tuple[str, ...]
    personal: str


EXTENSIONS = {
    "audio-notes": Extension(
        "Audio Notes",
        audio_notes_enabled,
        ("SKILL.md", "references/voices.md", "references/workflow.md"),
        "course/audio/01-topic.m4a",
    ),
    "video-notes": Extension(
        "Video Notes",
        video_notes_enabled,
        ("SKILL.md", "references/manim.md", "references/narration.md"),
        "course/videos/tracks/01_topic.mp4",
    ),
}


@pytest.fixture
def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr("tum_mcp.updates.is_wsl", lambda: False)
    return home


@pytest.mark.parametrize("client", ["codex", "claude", "cursor", "antigravity", "generic"])
def test_media_workflows_are_opt_in_and_export_complete_workflows(
    profile: Path, tmp_path: Path, client: str
) -> None:
    install_client(client, profile, announce=False)
    runner = CliRunner()
    assert len(inspect_skills()) == 7
    blocked = runner.invoke(app, ["video-notes", "plan", str(tmp_path), "--selection", "x"])
    assert blocked.exit_code != 0 and "install video-notes" in str(blocked.exception)
    for count, (name, extension) in enumerate(EXTENSIONS.items(), start=8):
        assert not extension.enabled()
        result = runner.invoke(app, ["install", name])
        assert result.exit_code == 0, result.output or repr(result.exception)
        assert extension.enabled() and len(inspect_skills()) == count
    destination = tmp_path / "export"
    export_pack(destination)
    report = json.loads(runner.invoke(app, ["doctor", "--json"]).output)
    status = json.loads(runner.invoke(app, ["status", "--json"]).output)
    for name, extension in EXTENSIONS.items():
        assert all((destination / name / file).is_file() for file in extension.files)
        row = next(item for item in report["extensions"] if item["label"] == extension.label)
        assert row["state"] == "Enabled"
        assert status["extensions"][name] is True


@pytest.mark.parametrize("first", ["video-notes", "audio-notes"])
def test_all_three_extensions_preserve_each_others_selection(profile: Path, first: str) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    second = "audio-notes" if first == "video-notes" else "video-notes"
    for name in ("lecture", first, second):
        command = ["install", name, *(["--no-asr"] if name == "lecture" else [])]
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output or repr(result.exception)
    assert audio_notes_enabled() and lecture_enabled() and video_notes_enabled()
    assert len(inspect_skills()) == 10
    result = runner.invoke(app, ["uninstall", "video-notes"])
    assert result.exit_code == 0, result.output
    assert audio_notes_enabled() and lecture_enabled() and not video_notes_enabled()
    stored = json.loads((profile.parent / "config/extensions.json").read_text(encoding="utf-8"))
    assert "video_notes" not in stored
    result = runner.invoke(app, ["uninstall", "audio-notes"])
    assert result.exit_code == 0, result.output
    assert lecture_enabled() and not audio_notes_enabled()


@pytest.mark.parametrize("name", EXTENSIONS)
def test_removal_preserves_personal_media_and_customized_workflow(profile: Path, name: str) -> None:
    extension = EXTENSIONS[name]
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", name]).exit_code == 0
    personal = profile / extension.personal
    personal.parent.mkdir(parents=True)
    personal.write_bytes(b"synthetic-personal-media")
    skill = profile / f".cursor/skills/{name}/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nPersonal style.\n", encoding="utf-8")
    before = skill.read_bytes()
    result = runner.invoke(app, ["uninstall", name])
    assert result.exit_code == 2
    assert not extension.enabled()
    assert skill.read_bytes() == before
    assert personal.read_bytes() == b"synthetic-personal-media"
    assert (profile / ".cursor/skills/prepare-study/SKILL.md").is_file()


@pytest.mark.parametrize("name", EXTENSIONS)
def test_invalid_customization_cannot_activate(profile: Path, tmp_path: Path, name: str) -> None:
    install_client("cursor", profile, announce=False)
    override = tmp_path / f"config/skills/{name}/SKILL.md"
    override.parent.mkdir(parents=True)
    override.write_text("invalid", encoding="utf-8")
    result = CliRunner().invoke(app, ["install", name])
    assert result.exit_code != 0
    assert not EXTENSIONS[name].enabled()
    assert not (profile / f".cursor/skills/{name}").exists()
