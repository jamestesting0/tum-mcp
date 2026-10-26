import json
import shutil
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp import study_cli
from tum_mcp.cli import app
from tum_mcp.study_content import StudyContent


def test_bundled_course_offers_four_choices_for_every_practice_question() -> None:
    # Given the content that supplies new synthetic study sites.
    source = files("tum_mcp") / "bundled/course_app/example/content.json"

    # When the same schema used by the site build loads that course.
    content = StudyContent.model_validate_json(source.read_bytes())

    # Then every question offers four distinct choices and one valid correct key.
    for unit in content.units:
        for question in unit.questions:
            assert len(question.options) == 4, (unit.key, question.key)
            assert len({option.text.casefold() for option in question.options}) == 4
            assert sum(option.key == question.correct for option in question.options) == 1


def test_template_is_available_without_auth_and_fingerprints_packaged_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "no-campus-state"))
    source = Path(str(files("tum_mcp")))
    copied = tmp_path / "package"
    relative = "bundled/course_app/site"
    shutil.copytree(source / relative, copied / relative)
    monkeypatch.setattr(study_cli, "files", lambda name: copied)
    result = CliRunner().invoke(app, ["study", "template"])
    assert result.exit_code == 0
    before = json.loads(result.output)
    assert {"app.mjs", "flashcards.mjs", "navigation.mjs", "revision.mjs", "styles.css"} <= set(
        before["files"]
    )
    assert before["author"] == "app/content.json"
    stylesheet = copied / relative / "styles.css"
    stylesheet.write_text(
        stylesheet.read_text(encoding="utf-8") + "\n/* changed template */\n", encoding="utf-8"
    )
    after = json.loads(CliRunner().invoke(app, ["study", "template"]).output)
    assert before["revision"] != after["revision"]
    assert not (tmp_path / "no-campus-state").exists()
