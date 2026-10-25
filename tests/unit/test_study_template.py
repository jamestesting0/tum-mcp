import json
import shutil
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp import study_cli
from tum_mcp.cli import app


def test_template_is_available_without_auth_and_fingerprints_packaged_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "no-campus-state"))
    source = Path(str(files("tum_mcp")))
    copied = tmp_path / "package"
    relative = "bundled/skills/prepare-study/assets/site"
    shutil.copytree(source / relative, copied / relative)
    monkeypatch.setattr(study_cli, "files", lambda name: copied)
    result = CliRunner().invoke(app, ["study", "template"])
    assert result.exit_code == 0
    before = json.loads(result.output)
    assert {"app.mjs", "flashcards.mjs", "navigation.mjs", "styles.css"} <= set(before["files"])
    assert before["author"] == "study/content.json"
    stylesheet = copied / relative / "styles.css"
    stylesheet.write_text(stylesheet.read_text() + "\n/* changed template */\n")
    after = json.loads(CliRunner().invoke(app, ["study", "template"]).output)
    assert before["revision"] != after["revision"]
    assert not (tmp_path / "no-campus-state").exists()
