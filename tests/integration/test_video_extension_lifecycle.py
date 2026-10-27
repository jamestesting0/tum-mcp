import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.extensions import audio_notes_enabled, studocu_enabled, video_notes_enabled
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
def test_video_notes_is_opt_in_and_exports_its_complete_workflow(
    profile: Path, tmp_path: Path, client: str
) -> None:
    install_client(client, profile, announce=False)
    assert not video_notes_enabled()
    assert len(inspect_skills()) == 5
    runner = CliRunner()
    blocked = runner.invoke(app, ["video-notes", "plan", str(tmp_path), "--selection", "x"])
    assert blocked.exit_code != 0 and "install video-notes" in str(blocked.exception)
    result = runner.invoke(app, ["install", "video-notes"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert video_notes_enabled() and len(inspect_skills()) == 6
    destination = tmp_path / "export"
    export_pack(destination)
    for name in ("SKILL.md", "references/manim.md", "references/narration.md"):
        assert (destination / "video-notes" / name).is_file()
    report = json.loads(runner.invoke(app, ["doctor", "--json"]).output)
    row = next(item for item in report["extensions"] if item["label"] == "Video Notes")
    assert row["state"] == "Enabled"
    status = json.loads(runner.invoke(app, ["status", "--json"]).output)
    assert status["extensions"]["video-notes"] is True


def test_four_extensions_keep_each_others_selection(profile: Path) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    for name in ("video-notes", "studocu", "audio-notes"):
        assert runner.invoke(app, ["install", name]).exit_code == 0
    assert video_notes_enabled() and studocu_enabled() and audio_notes_enabled()
    assert runner.invoke(app, ["uninstall", "audio-notes"]).exit_code == 0
    assert video_notes_enabled() and studocu_enabled() and not audio_notes_enabled()
    assert runner.invoke(app, ["uninstall", "video-notes"]).exit_code == 0
    assert not video_notes_enabled() and studocu_enabled()
    stored = json.loads((profile.parent / "config/extensions.json").read_text(encoding="utf-8"))
    assert "video_notes" not in stored


def test_removal_keeps_videos_and_a_customized_workflow(profile: Path) -> None:
    install_client("cursor", profile, announce=False)
    runner = CliRunner()
    assert runner.invoke(app, ["install", "video-notes"]).exit_code == 0
    track = profile / "course/videos/tracks/01_topic.mp4"
    track.parent.mkdir(parents=True)
    track.write_bytes(b"synthetic-personal-video")
    skill = profile / ".cursor/skills/video-notes/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nPersonal style.\n", encoding="utf-8")
    before = skill.read_bytes()
    result = runner.invoke(app, ["uninstall", "video-notes"])
    assert result.exit_code == 2
    assert not video_notes_enabled()
    assert skill.read_bytes() == before
    assert track.read_bytes() == b"synthetic-personal-video"


def test_invalid_customization_cannot_activate(profile: Path, tmp_path: Path) -> None:
    install_client("cursor", profile, announce=False)
    override = tmp_path / "config/skills/video-notes/SKILL.md"
    override.parent.mkdir(parents=True)
    override.write_text("invalid", encoding="utf-8")
    result = CliRunner().invoke(app, ["install", "video-notes"])
    assert result.exit_code != 0
    assert not video_notes_enabled()
    assert not (profile / ".cursor/skills/video-notes").exists()
