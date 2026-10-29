import io
import json
import re
from pathlib import Path

import pytest
from rich.console import Console
from rich.theme import Theme
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import audio_notes_enabled, lecture_enabled
from tum_mcp.ui import STYLES, State, status_rows


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))


@pytest.mark.parametrize(
    "command",
    [
        [],
        ["status"],
        ["doctor"],
        ["uninstall"],
        ["manage", "tumonline"],
        ["skills", "validate"],
        ["study", "build"],
        ["lecture", "runtime", "status"],
        ["uninstall"],
    ],
)
def test_help_uses_canonical_paths_without_touching_user_state(
    command: list[str],
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(app, [*command, "--help"], prog_name="tum-mcp")
    assert result.exit_code == 0, result.output
    assert result.output.startswith("TUM MCP")
    assert "tum-mcp " + " ".join(command) in result.output
    assert "python -m" not in result.output
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "config").exists()


@pytest.mark.parametrize("command", [["status"], ["skills", "list"], ["skills", "validate"]])
def test_management_output_has_human_and_parseable_json_forms(command: list[str]) -> None:
    human = CliRunner().invoke(app, command)
    machine = CliRunner().invoke(app, [*command, "--json"])
    assert human.exit_code == machine.exit_code == 0, human.output + machine.output
    assert human.output.startswith("TUM MCP")
    assert json.loads(machine.output) is not None
    assert "\x1b[" not in machine.output


def test_unverified_dot_is_blue_while_label_uses_the_terminal_foreground() -> None:
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=True,
        no_color=False,
        color_system="standard",
        theme=Theme(STYLES),
    )
    status_rows(console, [("Synthetic service", State.CONFIGURED, "Session saved.")])
    assert re.search(r"\x1b\[34m● \x1b\[0mNot verified", stream.getvalue())


def test_removal_without_names_in_a_pipe_cannot_change_extensions() -> None:
    result = CliRunner().invoke(app, ["uninstall"])
    assert isinstance(result.exception, CampusError)
    assert result.exception.code == Code.ACTION_REQUIRED
    assert not lecture_enabled() and not audio_notes_enabled()


def test_explicit_removal_accepts_both_extensions_and_returns_json() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["install", "lecture", "--no-asr"]).exit_code == 0
    assert runner.invoke(app, ["install", "audio-notes"]).exit_code == 0
    result = runner.invoke(app, ["uninstall", "lecture", "audio-notes", "--json"])
    assert result.exit_code == 0, result.output
    assert {item["extension"] for item in json.loads(result.output)} == {"lecture", "audio-notes"}
    assert not lecture_enabled() and not audio_notes_enabled()


def test_cancelled_picker_preserves_both_enabled_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    runner.invoke(app, ["install", "lecture", "--no-asr"])
    runner.invoke(app, ["install", "audio-notes"])
    monkeypatch.setattr("tum_mcp.extension_management.interactive_terminal", lambda: True)
    monkeypatch.setattr("tum_mcp.extension_management.select_many", lambda *args, **kwargs: None)
    result = runner.invoke(app, ["uninstall"])
    assert result.exit_code == 130
    assert lecture_enabled() and audio_notes_enabled()


def test_invalid_extension_state_is_reported_without_hiding_the_other_extension(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "lecture-extension.json").write_text("invalid", encoding="utf-8")
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert State.FAILED.value in result.output and "Audio Notes" in result.output
    assert (config / "lecture-extension.json").read_text() == "invalid"


def test_requested_credential_cleanup_cannot_select_an_individual_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    for name in ("lecture", "audio-notes", "video-notes"):
        result = runner.invoke(app, ["install", name, *(["--no-asr"] if name == "lecture" else [])])
        assert result.exit_code == 0, result.output
    monkeypatch.setattr("tum_mcp.extension_management.interactive_terminal", lambda: True)
    monkeypatch.setenv("TUM_MCP_NPM_LAUNCHER", "1")

    def choose(title, choices, **kwargs):
        assert {value for value, _, _, enabled in choices if enabled} == {"all"}
        return ("all",)

    monkeypatch.setattr("tum_mcp.extension_management.select_many", choose)
    result = runner.invoke(app, ["uninstall", "--forget-credentials"])
    assert result.exit_code == 20
    assert lecture_enabled() and audio_notes_enabled()
