import json
from pathlib import Path

import pytest
from material_fixture import material_project, minimal_unit, pdf_bytes
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_build import build
from tum_mcp.study_import import import_file
from tum_mcp.study_publish_site import export_site
from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync


@pytest.fixture
def course(tmp_path: Path) -> Path:
    return material_project(tmp_path, {"slides": ("content", pdf_bytes(["Observer"]))})


def test_import_adds_a_private_local_exam_once(course: Path, tmp_path: Path) -> None:
    exam = tmp_path / "Klausur WS23.pdf"
    exam.write_bytes(pdf_bytes(["Endterm WS23 Task 1"]))
    result = CliRunner().invoke(
        app,
        [
            "study",
            "import",
            str(course),
            "--file",
            str(exam),
            "--kind",
            "exam",
            "--title",
            "Endterm WS23",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["imported"] and report["key"] == "local-endterm-ws23"
    assert report["path"] == "materials/exams/material-local-endterm-ws23.pdf"
    assert (course / report["path"]).read_bytes() == exam.read_bytes()
    state = load_state(course)
    binding = next(item for item in state.course.bindings if item.provider == "local")
    assert {item.binding for item in state.coverage} == {"moodle", binding.key}
    again = import_file(course, exam, "exam", "A different title")
    assert not again.imported and again.key == report["key"]
    assert len(load_state(course).resources) == 2
    solution = tmp_path / "solution.pdf"
    solution.write_bytes(pdf_bytes(["Solution"]))
    assert import_file(course, solution, "exam", "Prüfung Lösung").key == "local-prufung-losung"
    statuses = {item.resource.key: item.status for item in load_state(course).resources}
    assert statuses[report["key"]] == statuses["local-prufung-losung"] == "current"


def test_campus_sync_keeps_local_files_or_refuses_safely(course: Path, tmp_path: Path) -> None:
    exam = tmp_path / "exam.pdf"
    exam.write_bytes(pdf_bytes(["Task"]))
    key = import_file(course, exam, "exam", "Retake").key
    snapshot = tmp_path / "incoming/snapshot.json"
    incoming = json.loads(snapshot.read_text(encoding="utf-8"))
    with pytest.raises(CampusError):
        sync(course, snapshot)
    incoming["course"]["bindings"] = [
        item.model_dump(mode="json", exclude_none=True)
        for item in load_state(course).course.bindings
    ]
    incoming["retained_bindings"] = ["local"]
    snapshot.write_text(json.dumps(incoming), encoding="utf-8")
    sync(course, snapshot)
    assert (
        next(i for i in load_state(course).resources if i.resource.key == key).status == "current"
    )


def test_local_sources_are_labelled_and_never_published(course: Path, tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes", encoding="utf-8")
    report = import_file(course, notes, "other", "My notes")
    state = load_state(course)
    (course / "app").mkdir()
    (course / "app/content.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course_key": state.course.key,
                "organization": "topics",
                "introduction": "Synthetic.",
                "units": [minimal_unit("notes", report.key, report.sha256)],
            }
        ),
        encoding="utf-8",
    )
    build(course, publish=False)
    data = (course / "app/data.mjs").read_text(encoding="utf-8")
    assert "My notes (local file)" in data and '"url":""' in data
    with pytest.raises(CampusError) as error:
        export_site(course)
    assert error.value.code == Code.SCOPE_DENIED
