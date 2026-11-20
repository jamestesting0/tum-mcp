import json
import uuid
from pathlib import Path

import pytest
from documents import content_file
from material_fixture import exam_document, exam_project, minimal_unit, pdf_bytes
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import build
from tum_mcp.course.app.comment_models import OPERATION
from tum_mcp.course.app.comments import change_comment, read_comments
from tum_mcp.course.app.publish_site import export_site
from tum_mcp.course.checks.batch import assess_batch
from tum_mcp.course.checks.plans import Plan, record_gate
from tum_mcp.course.content.exam import ExamContent
from tum_mcp.course.content.exam_data import exam_revisions
from tum_mcp.course.project.store import load_state, private_path
from tum_mcp.course.workflow import tasks
from tum_mcp.errors import CampusError, Code


@pytest.fixture
def course(tmp_path: Path) -> Path:
    root = exam_project(tmp_path)
    (root / "app").mkdir()
    document = exam_document(root)
    content_file(root, "exam").write_text(json.dumps(document), encoding="utf-8")
    private_path(root, "coverage.json").write_text(
        json.dumps(
            {
                "course_key": document["course_key"],
                "sources": [
                    {
                        "source": "slides",
                        "status": {"checked_at": "2026-10-28"},
                        "exam": [
                            {
                                "key": c["key"],
                                "text": c["line"],
                                "locator": "1",
                                "concepts": [c["key"]],
                            }
                            for c in document["concepts"]
                        ],
                    }
                ],
            }
        )
    )
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


def select_exam_item(course: Path, item: str) -> None:
    batch = private_path(course, "batches/selected.json")
    batch.parent.mkdir(parents=True, exist_ok=True)
    batch.write_text(
        json.dumps(
            {
                "course_key": load_state(course).course.key,
                "request": "Prepare the selected Exam material.",
                "items": [item],
            }
        )
    )


def exam_pdf(course: Path, key: str) -> Path:
    source = next(item for item in load_state(course).resources if item.resource.key == key)
    assert source.path is not None
    return course / source.path


@pytest.mark.parametrize("gate", ["readiness", "finish"])
def test_selected_sheet_rechecks_cited_pdf_bytes(
    course: Path, monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    monkeypatch.setattr("tum_mcp.course.checks.batch._browser_problems", lambda *args: [])
    select_exam_item(course, "exam/sheet")
    build(course, publish=False)
    assert payload(course)["workspaces"] == ["exam"]
    assert len(payload(course)["exam"]["concepts"]) == 6
    tasks.begin(course, "selected", owner="exam-author")
    reading = assess_batch(course, "selected")
    assert reading.ready, reading.problems
    assert tasks.finish(course, owner="exam-author")["ready"]

    data = (course / "app/data.mjs").read_bytes()
    receipt = private_path(course, "task.json").read_bytes()
    cited = exam_pdf(course, "slides")
    original = cited.read_bytes()
    cited.write_bytes(pdf_bytes(["Changed concept source"]))
    if gate == "readiness":
        reading = assess_batch(course, "selected")
        assert not reading.ready
        assert any(
            p.startswith("exam/sheet:") and "concept:observer" in p and "slides" in p
            for p in reading.problems
        )
    else:
        with pytest.raises(CampusError, match=r"exam/sheet:.*concept:observer.*slides"):
            tasks.finish(course, owner="exam-author")
    assert (course / "app/data.mjs").read_bytes() == data
    assert private_path(course, "task.json").read_bytes() == receipt

    cited.write_bytes(original)
    assert assess_batch(course, "selected").ready
    assert tasks.finish(course, owner="exam-author")["ready"]


def test_unrelated_paper_leaves_sheet_ready_but_blocks_full_build(
    course: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tum_mcp.course.checks.batch._browser_problems", lambda *args: [])
    select_exam_item(course, "exam/sheet")
    build(course, publish=False)
    exam_pdf(course, "exam-ss19").write_bytes(pdf_bytes(["Changed outdated paper"]))

    assert assess_batch(course, "selected").ready
    with pytest.raises(CampusError) as error:
        build(course, publish=False)
    assert error.value.code == Code.STALE_RESULT
    assert "variant:" in error.value.message


def test_paper_counted_in_sheet_badges_is_checked(
    course: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tum_mcp.course.checks.batch._browser_problems", lambda *args: [])
    select_exam_item(course, "exam/sheet")
    build(course, publish=False)
    exam_pdf(course, "exam-ws23-b").write_bytes(pdf_bytes(["Changed counted variant"]))

    (problem,) = assess_batch(course, "selected").problems
    assert problem.startswith("exam/sheet: variant:") and "exam-ws23-b" in problem


def test_exam_pattern_derives_sheet_and_reports_its_stale_workflow_source(
    course: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tum_mcp.course.checks.batch._browser_problems", lambda *args: [])
    item = "exam/pattern/observer-design"
    select_exam_item(course, item)
    plan = Plan(item=item)
    path = private_path(course, f"plans/{item}.json")
    path.parent.mkdir(parents=True)
    path.write_text(plan.model_dump_json())
    record_gate(
        course, [{"item": item, "fingerprint": plan.fingerprint(), "verdict": "pass"}], "fresh"
    )
    document = exam_document(course)
    extra = next(s for s in load_state(course).resources if s.resource.key == "exam-ss19")
    document["patterns"][0]["sources"].append({"key": extra.resource.key, "sha256": extra.sha256})
    content_file(course, "exam").write_text(json.dumps(document))
    build(course, publish=False)
    before = assess_batch(course, "selected")
    assert "exam/sheet" in before.items
    assert not any("cited source bytes" in p for p in before.problems)

    exam_pdf(course, "exam-ss19").write_bytes(pdf_bytes(["Changed workflow source"]))
    after = assess_batch(course, "selected")
    new_problems = set(after.problems) - set(before.problems)
    assert {p.partition(":")[0] for p in new_problems} == {item, "exam/sheet"}
    assert all("pattern:observer-design" in p and "exam-ss19" in p for p in new_problems)


@pytest.mark.parametrize("practice", [False, True], ids=["mock", "untimed-practice"])
def test_mock_checks_its_own_source_and_only_the_displayed_profile(
    course: Path, monkeypatch: pytest.MonkeyPatch, practice: bool
) -> None:
    monkeypatch.setattr("tum_mcp.course.checks.batch._browser_problems", lambda *args: [])
    item = "exam/mock/forecast-1/f1-1"
    document = exam_document(course)
    resources = {s.resource.key: s.sha256 for s in load_state(course).resources}
    mock = document["mocks"][0]
    mock["sources"].append({"key": "exam-ws22", "sha256": resources["exam-ws22"]})
    if practice:
        mock.update(kind="practice", duration_minutes=None, instructions=None)
    document["profile"]["sources"] = [{"key": "exam-ss19", "sha256": resources["exam-ss19"]}]
    content_file(course, "exam").write_text(json.dumps(document))
    select_exam_item(course, item)
    build(course, publish=False)
    assert assess_batch(course, "selected").ready

    own_source = exam_pdf(course, "exam-ws22")
    original = own_source.read_bytes()
    own_source.write_bytes(pdf_bytes(["Changed mock source"]))
    assert any(
        p.startswith(f"{item}: mock:forecast-1 ") and "exam-ws22" in p
        for p in assess_batch(course, "selected").problems
    )
    own_source.write_bytes(original)

    exam_pdf(course, "exam-ss19").write_bytes(pdf_bytes(["Changed profile source"]))
    reading = assess_batch(course, "selected")
    if practice:
        assert reading.ready, reading.problems
    else:
        (problem,) = reading.problems
        assert problem.startswith(f"{item}: profile ") and "exam-ss19" in problem


def test_exam_prep_exports_alone_and_with_study_without_document_references(course: Path) -> None:
    from PIL import Image

    image = course / "app/figures/exam-only.png"
    image.parent.mkdir()
    Image.new("RGB", (16, 16), "white").save(image)
    authored = content_file(course, "exam")
    exam = json.loads(authored.read_bytes())
    exam["concepts"][0].setdefault("details", []).append(
        {
            "kind": "figure",
            "sources": ["slides"],
            "alt": "An exam-only synthetic white square.",
            "image": "figures/exam-only.png",
        }
    )
    authored.write_text(json.dumps(exam))
    build(course, publish=False)
    exported = export_site(course)
    assert exported["figures/exam-only.png"] == image.read_bytes()
    site = exported["data.mjs"]
    published = json.loads(site.removeprefix(b"const data = ").split(b";\ndata.hosted")[0])
    assert published["workspaces"] == ["exam"]
    assert published["sources"] == {}
    assert published["exam"]["statistics"] == payload(course)["exam"]["statistics"]
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
    (content_file(course, "study")).write_text(json.dumps(study), encoding="utf-8")
    build(course, publish=False)
    site = export_site(course)["data.mjs"]
    published = json.loads(site.removeprefix(b"const data = ").split(b";\ndata.hosted")[0])
    assert published["workspaces"] == ["study", "exam"]
    assert published["sources"] == {}
    assert published["exam"]["sittings"] and b"Endterm" in site
    assert b"materials/" not in site and b"www.moodle.tum.de" not in site


def test_cli_schema_report_and_inspect(course: Path) -> None:
    runner = CliRunner()
    schema = json.loads(runner.invoke(app, ["study", "schema", "exam"]).output)
    assert "sittings" in schema["properties"]
    report = json.loads(runner.invoke(app, ["study", "exam-report", str(course), "--json"]).output)
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
    content = ExamContent.model_validate_json((content_file(course, "exam")).read_bytes())
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
    from tum_mcp.course.content.exam_data import check_unit_links
    from tum_mcp.course.content.study import StudyContent

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
    # A concept's Recall passage is held to the same rule: a core block of its own units.
    first["guidance"]["prerequisites"] = []
    concept = raw["concepts"][0]
    concept["units"] = sorted({*concept["units"], "observer"})
    concept["passages"] = [{"unit": "observer", "block": "origin"}]
    with pytest.raises(CampusError, match="does not have"):
        check_unit_links(ExamContent.model_validate(raw), study)
    concept["passages"] = [{"unit": "elsewhere", "block": "origin"}]
    with pytest.raises(ValueError, match="passages come from the units it names"):
        ExamContent.model_validate(raw)


def test_cheatsheet_exercise_links_require_a_prepared_target(
    course: Path, exercise_project: Path
) -> None:
    from tum_mcp.course.content.exam_data import check_exercise_links
    from tum_mcp.course.content.exercises import ExerciseContent

    exercises = ExerciseContent.model_validate_json(
        content_file(exercise_project, "exercises").read_bytes()
    )
    group = exercises.sets[0]
    target = {"set": group.key, "exercise": group.exercises[0].key}
    document = exam_document(course)
    document["concepts"][0]["exercises"] = [target]
    check_exercise_links(ExamContent.model_validate(document), exercises)
    content_file(course, "exam").write_text(json.dumps(document))
    # The same link cannot build when this project has no prepared Exercises workspace.
    with pytest.raises(CampusError, match="links to an unprepared exercise"):
        build(course, publish=False)


def test_pattern_review_tracks_the_actual_past_question_it_teaches(course: Path) -> None:
    from tum_mcp.course.review.items import collect

    document = exam_document(course)
    question = document["sittings"][0]["variants"][1]["questions"][0]
    question["statement"] = [
        {
            "kind": "text",
            "sources": ["exam-ws23-b"],
            "paragraphs": ["A stock ticker notifies registered displays when its price changes."],
        }
    ]
    before = collect(course, exam=ExamContent.model_validate(document))
    key = "exam/pattern/observer-design"
    # Past questions remain reviewable even when the maker chose synthetic worked examples.
    questions = before[key].value["past_questions"]
    assert questions[0]["statement"] and questions[0]["source_versions"]
    source_hash = document["sittings"][0]["variants"][1]["sources"][0]["sha256"]
    assert all(text != source_hash for _, text in before[key].passages())
    question["statement"][0]["paragraphs"].append("Each display needs the current price.")
    after = collect(course, exam=ExamContent.model_validate(document))
    assert (
        before[key].blocks["past_questions:ws23-b-1"]
        != after[key].blocks["past_questions:ws23-b-1"]
    )
    assert before["exam/pattern/strategy-swap"].blocks == after["exam/pattern/strategy-swap"].blocks
