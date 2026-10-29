import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.clients import install_client
from tum_mcp.extensions import lecture_enabled
from tum_mcp.skill_catalog import CURRENT_SKILLS


@pytest.fixture
def extension_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "data"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(data))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(data / "config"))
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path / "moodle"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_cli_opt_in_repeat_update_and_removal_preserve_base_and_personal_files(
    extension_home: Path,
) -> None:
    install_client("claude", extension_home, announce=False)
    skills = extension_home / ".claude/skills"
    assert {path.name for path in skills.iterdir()} == set(CURRENT_SKILLS)
    notes = extension_home / "my-course/notes.txt"
    notes.parent.mkdir()
    notes.write_text("Personal lecture notes")
    runner = CliRunner()
    for _ in range(2):
        installed = runner.invoke(app, ["install", "lecture", "--no-asr"])
        assert installed.exit_code == 0, installed.output or repr(installed.exception)
    assert lecture_enabled() and (skills / "prepare-lecture/SKILL.md").is_file()
    assert len(list(skills.iterdir())) == 8
    refreshed = runner.invoke(app, ["update"])
    assert refreshed.exit_code == 0, refreshed.output
    assert (skills / "prepare-lecture/SKILL.md").is_file()
    result = runner.invoke(app, ["uninstall", "lecture", "--json"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert not lecture_enabled() and {path.name for path in skills.iterdir()} == set(CURRENT_SKILLS)
    assert notes.read_text() == "Personal lecture notes"
    config = json.loads((extension_home / ".claude.json").read_text())
    assert "tum" in config["mcpServers"]


def test_extension_removal_preserves_customized_optional_skill(extension_home: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["install", "lecture", "--no-asr"])
    install_client("cursor", extension_home, announce=False)
    skill = extension_home / ".cursor/skills/prepare-lecture/SKILL.md"
    skill.write_text(skill.read_text() + "\nMy personal lecture workflow.\n")
    before = skill.read_bytes()
    result = runner.invoke(app, ["uninstall", "lecture", "--json"])
    assert result.exit_code == 2 and "preserved" in result.output
    assert not lecture_enabled() and skill.read_bytes() == before
    assert (extension_home / ".cursor/skills/prepare-study/SKILL.md").is_file()


def test_disabled_lecture_command_returns_install_handoff_without_creating_course_data(
    extension_home: Path, tmp_path: Path
) -> None:
    project = tmp_path / "course"
    result = CliRunner().invoke(
        app,
        [
            "lecture",
            "prepare",
            str(project),
            "--recording",
            "https://live.rbg.tum.de/w/synthetic/11",
        ],
    )
    assert result.exit_code != 0 and "install lecture" in str(result.exception)
    assert not project.exists()


def test_base_and_optional_catalog_validation_do_not_claim_activation(extension_home: Path) -> None:
    runner = CliRunner()
    base = runner.invoke(app, ["skills", "validate", "--json"])
    optional = runner.invoke(app, ["skills", "validate", "--all", "--json"])
    assert base.exit_code == optional.exit_code == 0
    assert len(json.loads(base.output)["checked_skills"]) == 7
    report = json.loads(optional.output)
    assert len(report["checked_skills"]) == 10 and not report["activation_evaluated"]


def test_real_mcp_process_exposes_live_tools_only_after_opt_in(extension_home: Path) -> None:
    async def names() -> set[str]:
        parameters = StdioServerParameters(
            command=sys.executable, args=["-I", "-m", "tum_mcp", "serve"], env=dict(os.environ)
        )
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            await session.initialize()
            return {tool.name for tool in (await session.list_tools()).tools}

    base = anyio.run(names)
    assert not any(name.startswith("tum_live_") for name in base)
    installed = CliRunner().invoke(app, ["install", "lecture", "--no-asr"])
    assert installed.exit_code == 0, installed.output
    extended = anyio.run(names)
    assert extended - base == {"tum_live_courses", "tum_live_recordings", "tum_live_recording"}
    assert {"moodle_list_courses", "artemis_list_lectures", "zulip_search_messages"} <= base
