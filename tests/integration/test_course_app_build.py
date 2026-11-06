import json
from pathlib import Path

from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import RETIRED_TEMPLATE_FILES, build, read_content, unit_revision
from tum_mcp.course.project.store import digest


def test_rebuild_keeps_learning_identities_and_paths(project: Path) -> None:
    # Given an authored course with unchanged content.
    before = read_content(project)
    # When building with the existing service.
    build(project, publish=False)
    payload = json.loads(
        (project / "app/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    # Then the existing renderer fields and learning identities remain intact.
    assert [item["revision"] for item in payload["units"]] == [
        unit_revision(unit) for unit in before.units
    ]
    assert payload["course"]["key"] == before.course_key
    inspected = CliRunner().invoke(app, ["study", "inspect", str(project)])
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.output)["exercises_path"] == "app/exercises/sets.json"


def test_retired_template_files_are_removed_unless_edited(project: Path) -> None:
    # Given a site built by an older template that still owns two retired files.
    site = project / "app"
    record_path = site / ".managed.json"
    record = json.loads(record_path.read_bytes())
    unedited, edited = RETIRED_TEMPLATE_FILES[:2]
    for name in (unedited, edited):
        (site / name).write_bytes(b"synthetic retired font")
        record["files"][name] = digest(b"synthetic retired font")
    (site / edited).write_bytes(b"locally edited font")
    record_path.write_text(json.dumps(record), encoding="utf-8")
    # When the current template builds the same project, twice.
    build(project, publish=False)
    build(project, publish=False)
    # Then the unedited copy is gone, the edit stays and neither remains managed.
    assert not (site / unedited).exists()
    assert (site / edited).read_bytes() == b"locally edited font"
    managed = json.loads(record_path.read_bytes())["files"]
    assert not set(managed) & set(RETIRED_TEMPLATE_FILES)


def test_exercise_schema_is_available_without_changing_the_study_schema() -> None:
    # Given the existing schema command used by authoring skills.
    runner = CliRunner()
    # When requesting the new exercise contract.
    result = runner.invoke(app, ["study", "schema", "exercises"])
    # Then callers receive a real schema while the old content contract stays version 1.
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["properties"]["schema_version"]["const"] == 1
    study = runner.invoke(app, ["study", "schema", "content"])
    assert study.exit_code == 0, study.output
    assert json.loads(study.output)["properties"]["schema_version"]["const"] == 1
