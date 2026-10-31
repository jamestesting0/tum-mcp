import json
import uuid
from pathlib import Path

import pytest
from material_fixture import exam_document, exam_project, minimal_unit, pdf_bytes
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.exam_content import ExamContent
from tum_mcp.exam_data import exam_revisions
from tum_mcp.study_build import build
from tum_mcp.study_comment_models import OPERATION
from tum_mcp.study_comments import change_comment, read_comments
from tum_mcp.study_publish_projection import project
from tum_mcp.study_publish_site import export_site
from tum_mcp.study_store import load_state


@pytest.fixture
def course(tmp_path: Path) -> Path:
    root = exam_project(tmp_path)
    (root / "app").mkdir()
    (root / "app/exam.json").write_text(json.dumps(exam_document(root)), encoding="utf-8")
    return root


def payload(root: Path) -> dict:
    data = (root / "app/data.mjs").read_bytes()
    return json.loads(data.removeprefix(b"export default ").removesuffix(b";\n"))


def test_exam_prep_builds_as_its_own_workspace_with_derived_statistics(course: Path) -> None:
    report = build(course, publish=False)
    assert report.exam == {"concepts": 6, "patterns": 3, "past_papers": 4, "practice_exams": 1}
    value = payload(course)
    assert value["workspaces"] == ["exam"]
    exam = value["exam"]
    assert exam["statistics"]["pattern_order"][0] == "observer-design"
    assert {node["key"] for node in exam["map"]["nodes"]} >= {"observer", "decorator"}
    assert "mathml" in next(c for c in exam["concepts"] if c["key"] == "cohesion")["formula"]
    assert all(len(concept["revision"]) == 64 for concept in exam["concepts"])
    assert {"slides", "exam-ws23", "exam-ws22-upload"} <= set(value["sources"])
    assert not exam["sittings"][0]["variants"][0]["replayable"]


def test_changed_sources_block_the_build_and_name_only_stale_items(course: Path) -> None:
    build(course, publish=False)
    (course / "materials/content/material-slides.pdf").write_bytes(pdf_bytes(["New slides"]))
    with pytest.raises(CampusError) as error:
        build(course, publish=False)
    assert error.value.code == Code.STALE_RESULT
    assert "concept:observer" in error.value.message and "variant:" not in error.value.message


def test_exam_prep_is_never_published(course: Path) -> None:
    build(course, publish=False)
    with pytest.raises(CampusError) as error:
        project(
            (course / "app/data.mjs").read_bytes(), include_exercises=True, include_lectures=True
        )
    assert error.value.code == Code.ACTION_REQUIRED
    slides = next(
        item for item in load_state(course).resources if item.resource.key == "slides"
    ).sha256
    unit = minimal_unit("observer", "slides", slides)
    study = {
        "schema_version": 1,
        "course_key": "synthetic-pse-ws26",
        "organization": "topics",
        "introduction": "Synthetic.",
        "units": [unit],
    }
    (course / "app/content.json").write_text(json.dumps(study), encoding="utf-8")
    build(course, publish=False)
    data = (course / "app/data.mjs").read_bytes()
    published = project(data, include_exercises=True, include_lectures=True)
    assert "exam" not in published and published["workspaces"] == ["study"]
    site = export_site(course, include_exercises=True)["data.mjs"].decode()
    assert '"exam"' not in site and "Endterm" not in site


def test_cli_schema_report_and_inspect(course: Path) -> None:
    runner = CliRunner()
    schema = json.loads(runner.invoke(app, ["study", "schema", "exam"]).output)
    assert "sittings" in schema["properties"]
    report = json.loads(runner.invoke(app, ["study", "exam-report", str(course)]).output)
    assert report["prepared"] and report["stats"]["sittings_considered"] == 2
    assert "exam" in report["materials"] and report["stale"] == []
    stale = json.loads(
        runner.invoke(app, ["study", "exam-report", str(course), "--section", "stale"]).output
    )
    assert set(stale) == {"exam_path", "prepared", "stale"}
    near = json.loads(
        runner.invoke(app, ["study", "exam-report", str(course), "--section", "duplicates"]).output
    )
    assert "near" in near["duplicates"]
    inspected = json.loads(runner.invoke(app, ["study", "inspect", str(course)]).output)
    assert inspected["stale_exam"] == []


def test_exam_comments_round_trip_with_current_revisions(course: Path) -> None:
    build(course, publish=False)
    content = ExamContent.model_validate_json((course / "app/exam.json").read_bytes())
    revision = exam_revisions(content)["concept:observer"]
    state = read_comments(course)
    identity = json.loads(
        (course / "app/data.mjs").read_bytes().removeprefix(b"export default ").removesuffix(b";\n")
    )["course"]["identity"]
    operation = OPERATION.validate_python(
        {
            "op": "create",
            "id": str(uuid.uuid4()),
            "course_identity": identity,
            "expected_revision": state["revision"],
            "anchor": {
                "workspace": "exam",
                "view": "exam",
                "item_key": "concept:observer",
                "item_revision": revision,
                "field": "line",
                "block_title": "Cheatsheet",
                "quote": "notifies",
            },
            "text": "Mention push versus pull.",
        }
    )
    change_comment(course, operation)
    listed = json.loads(
        CliRunner().invoke(app, ["study", "comments", "list", str(course), "--view", "exam"]).output
    )
    assert [item["content_state"] for item in listed["comments"]] == ["current"]


def test_exam_guidance_cannot_use_an_optional_only_study_block(course: Path) -> None:
    from tum_mcp.exam_data import check_unit_links
    from tum_mcp.study_content import StudyContent

    state = load_state(course)
    source = next(item for item in state.resources if item.resource.key == "slides")
    from material_fixture import with_guided_paper

    document = with_guided_paper(exam_document(course))
    unit = minimal_unit("observer", "slides", source.sha256)
    unit["explore"] = [
        {
            "key": "context",
            "title": "Historical context",
            "sources": unit["sources"],
            "blocks": [
                {
                    "kind": "text",
                    "key": "origin",
                    "sources": ["slides"],
                    "paragraphs": ["Background."],
                }
            ],
        }
    ]
    exam = ExamContent.model_validate(document)
    # Supply every linked unit while keeping the requested block solely optional.
    keys = {key for concept in exam.concepts for key in concept.units}
    keys.update(key for topic in exam.topics for key in topic.units)
    keys.update(
        p.unit
        for _, _, question in exam.past_questions().values()
        if question.guidance
        for p in question.guidance.prerequisites
    )
    units = [
        unit if key == "observer" else minimal_unit(key, "slides", source.sha256)
        for key in keys | {"observer"}
    ]
    study = StudyContent.model_validate(
        {
            "course_key": state.course.key,
            "organization": "topics",
            "introduction": "Synthetic Study.",
            "units": units,
        }
    )
    raw = exam.model_dump(mode="json")
    first = next(
        question
        for sitting in raw["sittings"]
        for variant in sitting["variants"]
        for question in variant["questions"]
        if question.get("guidance")
    )
    first["guidance"]["prerequisites"] = [
        {"unit": "observer", "block": "origin", "explanation": "Requires background."}
    ]
    with pytest.raises(CampusError, match="does not have"):
        check_unit_links(ExamContent.model_validate(raw), study)
