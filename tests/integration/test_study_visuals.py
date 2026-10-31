"""The render check: it passes a synthetic FAI-style corpus, follows the content and the app
it measured, and catches the broken layouts of review-course's calibration gallery."""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.study_build import build, read_content
from tum_mcp.study_review import revision
from tum_mcp.study_visuals import _visits, app_revision, report_path, visual_ids

CORPUS = Path(__file__).parents[1] / "fixtures/visual-corpus.json"
browser = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def invoke(*args: str) -> dict:
    result = CliRunner().invoke(app, ["study", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def render(project: Path) -> dict:
    return invoke("report", str(project), "--section", "render")["render"]


def add_corpus(project: Path) -> None:
    path = project / "study/content.json"
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
    site = project / "study"
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
    path = exercise_project / "study/exercises.json"
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
    checked = invoke("visuals", str(exercise_project), "--exercise", "sheet-1/sample-relaxation")
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
    checked = invoke("visuals", str(project), "--unit", "visuals")
    # Then every visual is drawn as authored, clear and legible at every width.
    assert checked["passed"] is True, checked["defects"]
    assert checked["checked"] == ["study/visuals"]
    assert checked["sheets"] and all((project / sheet).is_file() for sheet in checked["sheets"])
    record = json.loads(report_path(project).read_bytes())["items"]["study/visuals"]
    assert len(record["visuals"]) == 19
    widths = {width for visual in record["visuals"] for width in visual["widths"]}
    assert widths == {"phone", "narrow", "desktop"}
    assert "study/visuals" not in render(project)["unchecked"]
    # When the unit changes, its check is stale until it runs again.
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    content["units"][-1]["summary"] += " Revised."
    path.write_text(json.dumps(content), encoding="utf-8")
    assert "study/visuals" in render(project)["stale"]


@browser
def test_gallery_shows_what_the_check_catches_and_what_needs_a_reviewer(project: Path) -> None:
    findings = invoke("visuals", str(project), "--gallery")["findings"]
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
