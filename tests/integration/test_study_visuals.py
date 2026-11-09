"""The render check: it passes a synthetic FAI-style corpus, follows the content and the app
it measured, and catches the broken layouts of review-course's calibration gallery."""

import json
import os
from pathlib import Path

import pytest
from documents import content_file
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import build, read_content
from tum_mcp.course.app.visuals import _visits, app_revision, report_path, visual_ids
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.review.models import revision

CORPUS = Path(__file__).parents[1] / "fixtures/visual-corpus.json"
browser = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def invoke(*args: str) -> dict:
    result = CliRunner().invoke(app, ["study", *args])
    assert result.exit_code == 0, result.output
    # The result is the JSON on stdout; `result.output` also interleaves stderr, where a
    # Windows CI run once found text after the JSON.
    return json.loads(result.stdout)


def render(project: Path) -> dict:
    return invoke("report", str(project), "--section", "render")["render"]


def add_corpus(project: Path) -> None:
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    content["units"].append(json.loads(CORPUS.read_bytes()))
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)


def test_answer_visuals_are_listed_and_injected() -> None:
    payload = json.loads((CORPUS.parent / "exercises.json").read_bytes())
    exercise = payload["sets"][0]["exercises"][0]
    table = {
        "kind": "table",
        "caption": "Path costs",
        "sources": ["weighted"],
        "columns": ["Existing", "Candidate"],
        "rows": [["5", "3"]],
    }
    exercise["solution"]["answers"][0]["blocks"] = [table]
    step = next(step for step in exercise["steps"] if step["check"]["kind"] == "self_check")
    step["check"]["model_answer"] = [table]
    exercise["transfer"] = {"prompt": "Compare the costs.", "answer": [table]}
    parsed = ExerciseContent.model_validate(payload)
    item = "exercises/sheet-1/sample-relaxation"
    expected = {"solution:0", f"compare:{step['key']}:0", "transfer:0"}
    assert expected <= set(visual_ids(None, parsed)[item])
    visits, revisions = _visits(None, parsed)
    injected = {str(entry["id"]) for visit in visits for entry in visit.inject}
    assert expected <= injected
    assert revisions[item] == revision(parsed.sets[0].exercises[0])
    assert _visits(None, parsed, tasks=frozenset({"other/missing"})) == ([], {})


def test_render_report_follows_the_content_and_the_app(project: Path) -> None:
    # Given a course whose units draw visuals, nothing has been checked yet.
    first = render(project)
    assert first["checked"] is False and first["passed"] is False
    unchecked = set(first["unchecked"])
    assert unchecked == {
        f"study/{key}" for key in ("bfs", "dfs", "graphs", "weighted", "probability")
    }
    # When a check of the current app recorded every unit, only its defects remain.
    units = {f"study/{unit.key}": unit for unit in read_content(project).units}
    defect = {"code": "label_overlap", "detail": '"2" overlaps "12"'}
    items = {
        item: {
            "revision": revision(units[item]),
            "checked_at": "2026-10-30",
            "sheets": [],
            "visuals": [
                {
                    "id": "block:1",
                    "kind": "diagram",
                    "title": "A graph",
                    "widths": {
                        "phone": {"findings": [defect] if item == "study/bfs" else [], "facts": {}}
                    },
                }
            ],
        }
        for item in unchecked
    }
    site = project / "app"
    record = {"schema_version": 1, "app": app_revision(site), "items": items}
    report_path(project).write_text(json.dumps(record), encoding="utf-8")
    measured = render(project)
    assert measured["unchecked"] == [] and measured["stale"] == []
    assert [(d["item"], d["code"]) for d in measured["defects"]] == [("study/bfs", "label_overlap")]
    # Then a changed app makes every record stale until the check runs again.
    report_path(project).write_text(json.dumps(record | {"app": "0" * 16}), encoding="utf-8")
    stale = render(project)
    assert stale["stale"] == sorted(unchecked) and stale["defects"] == []


@browser
def test_wide_solution_table_is_measured(exercise_project: Path) -> None:
    path = content_file(exercise_project, "exercises")
    payload = json.loads(path.read_bytes())
    exercise = payload["sets"][0]["exercises"][0]
    source = exercise["sources"][0]["key"]
    exercise["solution"]["answers"][0]["blocks"] = [
        {
            "kind": "table",
            "caption": "Classification cases",
            "sources": [source],
            "columns": [f"Classification criterion {index}" for index in range(8)],
            "rows": [["A substantially longer classification value"] * 8],
        }
    ]
    path.write_text(json.dumps(payload))
    build(exercise_project, publish=False)
    checked = invoke(
        "visuals",
        str(exercise_project),
        "--exercise",
        "sheet-1/sample-relaxation",
        "--phone",
        "--json",
    )
    record = json.loads(report_path(exercise_project).read_bytes())
    visuals = record["items"]["exercises/sheet-1/sample-relaxation"]["visuals"]
    answer = next(visual for visual in visuals if visual["id"] == "solution:0")
    assert set(answer["widths"]) == {"phone", "narrow", "desktop"}
    assert any(
        finding["code"] == "table_scrolls" for finding in answer["widths"]["phone"]["findings"]
    )
    assert checked["passed"] is False


@browser
def test_corpus_passes_and_an_edit_makes_its_check_stale(project: Path) -> None:
    # Given the FAI-style corpus: seven graphs, five UML diagrams and seven plots.
    add_corpus(project)
    checked = invoke("visuals", str(project), "--unit", "visuals", "--json")
    # Then every visual is drawn as authored, clear and legible at desktop, the default width.
    assert checked["passed"] is True, checked["defects"]
    assert checked["checked"] == ["study/visuals"]
    assert checked["sheets"] and all((project / sheet).is_file() for sheet in checked["sheets"])
    assert all(sheet.startswith(".tum-mcp/visuals/") for sheet in checked["sheets"])
    record = json.loads(report_path(project).read_bytes())["items"]["study/visuals"]
    assert len(record["visuals"]) == 19
    widths = {width for visual in record["visuals"] for width in visual["widths"]}
    assert widths == {"desktop"}
    assert "study/visuals" not in render(project)["unchecked"]
    # When the unit changes, its check is stale until it runs again.
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    content["units"][-1]["summary"] += " Revised."
    path.write_text(json.dumps(content), encoding="utf-8")
    assert "study/visuals" in render(project)["stale"]


@browser
def test_gallery_shows_what_the_check_catches_and_what_needs_a_reviewer(project: Path) -> None:
    findings = invoke("visuals", str(project), "--gallery", "--json")["findings"]
    # A scrambled map breaks measurable rules; its lattice version passes.
    assert any(code.startswith("coincident_edges") for code in findings["gallery:map-scrambled"])
    assert findings["gallery:map-lattice"] == []
    # Three worded boxes in a row scroll on a phone; with the third on the next row they fit.
    assert "scrolls (phone)" in findings["gallery:mdp-row-on-phone"]
    assert findings["gallery:mdp-two-rows"] == []
    # An invented state or a dropped class draws cleanly: only the visual review catches them.
    assert findings["gallery:mdp-fake-state"] == []
    assert not [
        code for code in findings["gallery:composite-without-client"] if "scrolls" not in code
    ]


def test_an_untitled_exam_visual_is_drawn_under_its_key() -> None:
    # The check heads each injected visual with its title; an untitled Exam figure crashed it.
    from tum_mcp.course.content.exam import ExamContent

    example = Path(__file__).parents[2] / "src/tum_mcp/bundled/course_app/example/exam.json"
    payload = json.loads(example.read_bytes())
    for example_ in payload["patterns"][1]["examples"]:
        for block in example_.get("blocks", []):
            block.pop("title", None)
    visits, _ = _visits(None, None, ExamContent.model_validate(payload), with_exam=True)
    titles = [entry["title"] for visit in visits for entry in visit.inject]
    assert titles and all(titles)


@browser
def test_walkthrough_stages_are_measured_without_losing_their_authored_geometry(
    tmp_path: Path,
) -> None:
    # A real trial crashed by comparing its painted graph to the walkthrough wrapper,
    # which has no nodes or edges; plot marks live in the stage as well.
    project = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(project)]).exit_code == 0
    invoke("visuals", str(project), "--unit", "components", "--json")
    content = read_content(project)
    unit = next(unit for unit in content.units if unit.key == "components")
    record = json.loads(report_path(project).read_bytes())["items"]["study/components"]
    by_id = {entry["id"]: entry for entry in record["visuals"]}
    for index, block in enumerate(unit.blocks):
        if block.kind != "walkthrough" or block.stage.kind not in {"diagram", "plot"}:
            continue
        measured = by_id[f"block:{index}"]["widths"]["desktop"]
        assert measured["facts"]["minTextPx"] >= 12
        assert not any(f["code"] == "fidelity" for f in measured["findings"])
    assert any(
        block.kind == "walkthrough" and block.stage.kind == "diagram" for block in unit.blocks
    )


@browser
def test_every_stepper_pill_and_search_on_the_demo_responds(tmp_path: Path) -> None:
    # Given the component demo, which shows every stepper, pill and the search.
    project = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(project)]).exit_code == 0
    # When the smoke uses each control as a student would.
    result = invoke("visuals", str(project), "--interact", "--json")
    # Then every control responds, with no script errors.
    assert result["problems"] == [] and result["controls"] >= 10


@browser
def test_visuals_find_a_guide_block_nested_under_its_statement(exercise_project: Path) -> None:
    # A per-part guide lives inside the exercise statement in the rendered app.
    path = content_file(exercise_project, "exercises")
    payload = json.loads(path.read_bytes())
    exercise = payload["sets"][0]["exercises"][0]
    exercise["parts"] = ["(a)"]
    exercise["part_blocks"] = {"(a)": "question"}
    exercise["statement"][0]["key"] = "question"
    exercise["solution"]["answers"][0]["label"] = "(a)"
    for step in exercise["steps"]:
        step["part"] = "(a)"
    step = exercise["steps"][1]
    step["blocks"] = [
        {
            "kind": "table",
            "caption": "Path costs",
            "sources": exercise["statement"][0]["sources"],
            "columns": ["Existing", "Candidate"],
            "rows": [["5", "3"]],
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    build(exercise_project, publish=False)

    result = invoke(
        "visuals", str(exercise_project), "--exercise", "sheet-1/sample-relaxation", "--json"
    )
    assert result["passed"], result["defects"]
    record = json.loads(report_path(exercise_project).read_bytes())["items"][
        "exercises/sheet-1/sample-relaxation"
    ]
    assert f"step:{step['key']}:0" in {visual["id"] for visual in record["visuals"]}
