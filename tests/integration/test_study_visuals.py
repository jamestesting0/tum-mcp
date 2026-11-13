"""The render check: it passes a synthetic FAI-style corpus, follows the content and the app
it measured, and catches the broken layouts of review-course's calibration gallery."""

import json
import os
from pathlib import Path

import pytest
from documents import content_file
from playwright.sync_api import Page
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.browser_evidence import read_receipt
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


@browser
def test_formula_layout_rejects_clipped_tiny_and_scrolling_math_in_revealed_content(
    exercise_project: Path,
) -> None:
    project = exercise_project
    study_file = content_file(project, "study")
    study = json.loads(study_file.read_bytes())
    unit = next(unit for unit in study["units"] if unit["key"] == "graphs")
    unit["questions"][0]["hint"] = r"The practice expression is \(u+v=7\)."
    unit["blocks"].append(
        {
            "kind": "table",
            "caption": "Wide table",
            "sources": [unit["sources"][0]["key"]],
            "columns": ["Case", "Expression"],
            "rows": [["Trial", r"\(a+b=3\)"]],
        }
    )
    graph = next(
        block for block in json.loads(CORPUS.read_bytes())["blocks"] if block["kind"] == "diagram"
    )
    graph["sources"] = [unit["sources"][0]["key"]]
    graph["edges"][0]["label"] = r"\(X_{1}<Y\)"
    unit["blocks"].append(graph)
    study_file.write_text(json.dumps(study), encoding="utf-8")
    exercise_file = content_file(project, "exercises")
    exercises = json.loads(exercise_file.read_bytes())
    steps = exercises["sets"][0]["exercises"][0]["steps"]
    steps[1]["hints"].append(r"The second step uses \(p+q=9\).")
    exercise_file.write_text(json.dumps(exercises), encoding="utf-8")
    build(project, publish=False)
    css = project / "app/styles.css"
    wide = (
        css.read_text(encoding="utf-8")
        + """
      .table-region { max-width: 150px; }
      .table-region table { min-width: 700px; }
      .graph-region { max-width: 150px; }
    """
    )
    css.write_text(wide, encoding="utf-8")
    args = (
        "visuals",
        str(project),
        "--interact",
        "--unit",
        "graphs",
        "--exercise",
        "sheet-1/sample-relaxation",
        "--phone",
        "--json",
    )
    clean = invoke(*args)
    assert clean["passed"], clean["problems"]

    css.write_text(
        wide
        + """
      .question-hint .inline-math { width: 14px; overflow: hidden; }
      .question-hint .inline-math > .tex { font-size: 18px !important; }
      .exercise-hints .inline-math { overflow: scroll; }
      .solution-answer { max-width: 150px; overflow-x: auto; }
      .solution-answer .inline-math:first-of-type > .tex { font-size: 6px !important; }
      .solution-answer .inline-math:nth-of-type(2) > .tex { position: relative; left: 180px; }
    """,
        encoding="utf-8",
    )
    broken = invoke(*args)

    assert not broken["passed"]
    problems = [issue for issue in broken["problems"] if issue["control"] == "math"]
    guide = "#exercises/sheet-1/sample-relaxation"
    for route, state, reason in (
        ("#graphs/content", "Practice question 1", "is clipped"),
        (guide, "Step 2", "has its own scrollbar"),
        (guide, "Solution", "is too small"),
        (guide, "Solution", "requires horizontal scrolling"),
    ):
        assert any(
            issue["route"] == route and state in issue["problem"] and reason in issue["problem"]
            for issue in problems
        ), problems
    receipt = read_receipt(project)
    assert receipt is not None
    for width in ("phone", "narrow", "desktop"):
        assert receipt.states[f"interact/{width}/#graphs/content"] is False
        assert receipt.states[f"interact/{width}/{guide}"] is False


@browser
def test_math_graph_labels_are_measured_as_painted_math(project: Path) -> None:
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    unit = json.loads(CORPUS.read_bytes())
    graph = next(block for block in unit["blocks"] if block["kind"] == "diagram")
    graph["nodes"][0]["label"] = r"Cloudy \(X_{1}\)"
    graph["edges"][0]["label"] = r"\(X<Y\)"
    unit["blocks"] = [graph]
    content["units"].append(unit)
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)

    result = invoke("visuals", str(project), "--unit", unit["key"], "--phone", "--json")

    assert result["passed"], result["defects"]


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
    assert invoke("visuals", str(project), "--unit", "visuals", "--json") == checked
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    content["units"][0]["summary"] += " Revised."
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)
    reused = invoke("visuals", str(project), "--unit", "visuals", "--json")
    assert reused["passed"] and reused["unchanged"] == ["study/visuals"]
    # When the unit changes, its check is stale until it runs again.
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
@pytest.mark.parametrize("long", [False, True], ids=["dots", "jump-menu"])
def test_walkthrough_last_steps_are_measured_and_captured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, long: bool
) -> None:
    from tum_mcp.course.app import visuals

    project = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(project)]).exit_code == 0
    if long:
        path = content_file(project, "study")
        content = json.loads(path.read_bytes())
        walk = next(
            block
            for block in content["units"][0]["blocks"]
            if block.get("key") == "walkthrough-graph"
        )
        for count, run in ((8, walk), (9, walk["variant"])):
            steps = run["steps"]
            steps[-1:-1] = [
                steps[-2] | {"action": f"Inspect pending branch {index}."}
                for index in range(count - len(steps))
            ]
        path.write_text(json.dumps(content), encoding="utf-8")
        build(project, publish=False)
    css = project / "app" / "styles.css"
    clean_css = css.read_text(encoding="utf-8")
    css.write_text(
        clean_css
        + '\n.graph g.active[data-node-key="g"] text { font-size: 6px !important; }\n'
        + '.graph-region:has([data-node-key="g"]) { width: 120px !important; }\n',
        encoding="utf-8",
    )
    captions: list[str] = []
    original = visuals._sheets

    def sheets(page: Page, shots: list[tuple[str, bytes]], width: int, stem: Path) -> list[Path]:
        captions.extend(caption for caption, _ in shots)
        return original(page, shots, width, stem)

    monkeypatch.setattr(visuals, "_sheets", sheets)
    result = invoke("visuals", str(project), "--unit", "components", "--json")
    unit = next(unit for unit in read_content(project).units if unit.key == "components")
    index = next(i for i, block in enumerate(unit.blocks) if block.key == "walkthrough-graph")
    visual_id = f"block:{index}"
    assert any(
        defect["visual"] == visual_id
        and defect["code"] == "tiny_text"
        and defect["detail"].endswith(" (last step)")
        for defect in result["defects"]
    )
    assert (
        sum(
            f" · {visual_id} · " in caption and caption.endswith(" · last step")
            for caption in captions
        )
        == 2
    )
    assert (
        sum(
            f" · {visual_id} · " in caption and caption.endswith(" · last step · whole drawing")
            for caption in captions
        )
        == 2
    )
    assert any(note["visual"] == visual_id for note in result["notes"])
    assert all(defect["code"] != "scrolls" for defect in result["defects"])
    if long:
        # The interaction checker must count menu entries rather than absent dots too.
        css.write_text(clean_css, encoding="utf-8")
        interacted = invoke("visuals", str(project), "--unit", "components", "--interact", "--json")
        assert interacted["problems"] == []


@browser
def test_grid_walkthroughs_receive_first_and_last_step_captures(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.app import visuals

    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    unit = content["units"][0]
    scenario = json.loads((CORPUS.parent / "grid_scenarios.json").read_bytes())["walkthroughs"][0]
    scenario["sources"] = [unit["sources"][0]["key"]]
    unit["blocks"] = [scenario]
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)
    captions: list[str] = []
    original = visuals._sheets

    def sheets(page: Page, shots: list[tuple[str, bytes]], width: int, stem: Path) -> list[Path]:
        captions.extend(caption for caption, _ in shots)
        return original(page, shots, width, stem)

    monkeypatch.setattr(visuals, "_sheets", sheets)
    result = invoke("visuals", str(project), "--unit", unit["key"], "--json")

    assert result["passed"], result["defects"]
    record = json.loads(report_path(project).read_bytes())["items"][f"study/{unit['key']}"]
    assert [(entry["id"], entry["kind"]) for entry in record["visuals"]] == [("block:0", "grid")]
    assert sum(caption.endswith(" · last step") for caption in captions) == 1
    assert len(captions) == 2


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
