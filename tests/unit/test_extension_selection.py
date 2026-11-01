import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.errors import CampusError
from tum_mcp.extension_selection import (
    ExtensionSelection,
    require_video_notes,
    selection,
    video_notes_enabled,
)


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr("tum_mcp.updates.is_wsl", lambda: False)
    (tmp_path / "config").mkdir()
    return tmp_path / "config"


def test_disabled_video_flag_keeps_the_previous_file_format() -> None:
    value = ExtensionSelection(audio_notes=True)
    assert value.serialized() == b'{\n  "schema_version": 1,\n  "audio_notes": true\n}'
    enabled = json.loads(value.model_copy(update={"video_notes": True}).serialized())
    assert enabled["video_notes"] is True


def test_future_boolean_flags_load_and_survive_rewrites(config: Path) -> None:
    (config / "extensions.json").write_text(
        '{"schema_version":1,"retired_tool":true,"future_tool":true}', encoding="utf-8"
    )
    loaded = selection()
    assert loaded.model_extra == {"retired_tool": True, "future_tool": True}
    assert not loaded.video_notes
    rewritten = json.loads(loaded.model_copy(update={"audio_notes": True}).serialized())
    assert rewritten == {
        "schema_version": 1,
        "retired_tool": True,
        "audio_notes": True,
        "future_tool": True,
    }


@pytest.mark.parametrize(
    "document",
    [
        '{"schema_version":1,"future_tool":"yes"}',
        '{"schema_version":1,"Future-Tool":true}',
        '{"schema_version":1,"video_notes":1}',
        '{"schema_version":1,"course_memory":1}',
        '{"schema_version":2}',
    ],
)
def test_malformed_selections_still_need_local_review(config: Path, document: str) -> None:
    (config / "extensions.json").write_text(document, encoding="utf-8")
    with pytest.raises(CampusError, match="Invalid extension selection"):
        selection()
    assert not video_notes_enabled()


def test_video_gate_names_the_install_command(config: Path) -> None:
    with pytest.raises(CampusError, match="tum-mcp install video-notes"):
        require_video_notes()
    (config / "extensions.json").write_text(
        '{"schema_version":1,"video_notes":true}', encoding="utf-8"
    )
    require_video_notes()


def test_installing_another_workflow_preserves_future_flags(config: Path) -> None:
    install_client("cursor", Path.home(), announce=False)
    (config / "extensions.json").write_text(
        '{"schema_version":1,"retired_tool":false,"audio_notes":false,"future_tool":true}',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["install", "audio-notes"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    stored = json.loads((config / "extensions.json").read_text(encoding="utf-8"))
    assert stored == {
        "schema_version": 1,
        "retired_tool": False,
        "audio_notes": True,
        "future_tool": True,
    }
