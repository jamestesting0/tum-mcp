"""Answer keys, plans and digests: the checks an author runs while writing one item."""

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.checks.plans import Plan, gate_status, plan_problems
from tum_mcp.course.content.store import read_document


def invoke(*args: str) -> dict:
    json_flag = args[0] == "study" and args[1] != "schedule"
    result = CliRunner().invoke(app, [*args, "--json"] if json_flag else list(args))
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(project)]).exit_code == 0
    return project


def write_key(project: Path, item: str, output: dict) -> None:
    path = project / ".tum-mcp/checks" / f"{item}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"import json\nprint(json.dumps({output!r}))\n", encoding="utf-8")


def test_an_answer_key_catches_a_wrong_value_and_a_wrong_trace_state(demo: Path) -> None:
    unit = read_document(demo, "study")["units"][0]
    item = f"study/{unit['key']}"
    walk = next(b for b in unit["blocks"] if b.get("key") == "walkthrough-graph")
    table = next(i for i, b in enumerate(unit["blocks"]) if b.get("key") == "walkthrough-table")
    states = [{"Frontier": step["state"][0]["value"]} for step in walk["steps"]]
    # Given a key that computes what the content already says.
    right = {
        "values": {f"blocks[{table}].stage.rows[3][1]": 1},
        "walkthroughs": {"walkthrough-graph": states},
    }
    write_key(demo, item, right)
    assert invoke("study", "verify", str(demo), "--item", item)["passed"]
    # When the key computes a different value and a different trace state, both are named.
    states[2] = {"Frontier": "C, B"}
    write_key(demo, item, right | {"values": {f"blocks[{table}].stage.rows[3][1]": 2}})
    result = invoke("study", "verify", str(demo), "--item", item)
    problems = result["items"][0]["problems"]
    assert not result["passed"] and len(problems) == 2
    assert "step 3: Frontier" in problems[1]
    # A key that prints nothing usable is a failure, not a pass.
    (demo / ".tum-mcp/checks" / f"{item}.py").write_text("print('done')\n")
    assert not invoke("study", "verify", str(demo), "--item", item)["passed"]


def test_lint_reports_one_items_plan_links_and_kind_defaults(demo: Path) -> None:
    unit = read_document(demo, "study")["units"][0]
    item = f"study/{unit['key']}"
    plan = {
        "item": item,
        "concepts": [
            {
                "name": "Breadth-first order",
                "kind": "algorithm",
                "instance": "S to G",
                "blocks": ["graph-trace"],
            },
        ],
    }
    path = demo / ".tum-mcp/plans" / f"{item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan))
    # A two-frame diagram is a stepped trace, so the algorithm's default is met.
    result = invoke("study", "lint", str(demo), "--item", item)
    assert result["plan"] == {"status": "unchecked", "problems": []}
    # An unknown block is a broken link; a one-frame picture would not teach the algorithm.
    plan["concepts"][0]["blocks"] = ["missing"]
    path.write_text(json.dumps(plan))
    assert invoke("study", "lint", str(demo), "--item", item)["plan"]["problems"]
    value = {"blocks": [{"key": "pic", "kind": "diagram", "frames": [{}]}]}
    checked = Plan.model_validate(plan | {"concepts": [plan["concepts"][0] | {"blocks": ["pic"]}]})
    assert "is taught with" in plan_problems(checked, value, None)[0]
    skipped = checked.model_copy(
        update={
            "concepts": (
                checked.concepts[0].model_copy(update={"skip": "Shown in the lecture video."}),
            )
        }
    )
    assert plan_problems(skipped, value, None) == []
    # A definition restated is not its worked instance: an example or case shows it.
    term = {"name": "Agent", "kind": "definition", "instance": "It acts.", "blocks": ["agent"]}
    defined = Plan.model_validate({"item": item, "concepts": [term]})
    shown = {"blocks": [{"key": "agent", "kind": "definition"}, {"key": "use", "kind": "text"}]}
    assert "example or case" in plan_problems(defined, shown, None)[0]
    term["blocks"] = ["agent", "use"]
    assert plan_problems(Plan.model_validate({"item": item, "concepts": [term]}), shown, None) == []
    # A bare key names its one item, and without --item every item is linted.
    assert invoke("study", "lint", str(demo), "--item", unit["key"])["item"] == item
    assert item in invoke("study", "lint", str(demo))["items"]
    # An unknown item names the items there are.
    missing = CliRunner().invoke(app, ["study", "lint", str(demo), "--item", "exam/entry"])
    assert missing.exit_code != 0 and "exam/sheet" in str(missing.exception)


def test_the_plan_gate_holds_only_for_the_plan_it_read(demo: Path, tmp_path: Path) -> None:
    item = "study/components"
    path = demo / ".tum-mcp/plans" / f"{item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"item": item, "cases": ["One case."]}))
    packet = invoke("review", "plans", str(demo))
    entry = packet["plans"][0]
    answer = tmp_path / "answer.json"
    answer.write_text(
        json.dumps(
            {"items": [{"item": item, "fingerprint": entry["fingerprint"], "verdict": "pass"}]}
        )
    )
    # The author checking its own plan leaves it provisional.
    invoke("review", "plan-record", str(demo), "--file", str(answer))
    assert gate_status(Plan.model_validate_json(path.read_bytes())) == "provisional"
    # A fresh headless checker reads the waiting plans and its verdict approves them.
    script = tmp_path / "checker.py"
    script.write_text(
        "import json, re, sys\n"
        "packet = json.load(open(re.search(r'at (\\S+\\.json)', sys.argv[1]).group(1)))\n"
        "items = [{'item': p['item'], 'fingerprint': p['fingerprint'], 'verdict': 'pass'}\n"
        "         for p in packet['plans']]\n"
        "print(json.dumps({'items': items}))\n"
    )
    command = f"{sys.executable} {script} {{prompt}}"
    assert invoke("review", "run-checker", str(demo), "--plans", "--command", command)[
        "recorded"
    ] == [item]
    stored = Plan.model_validate_json(path.read_bytes())
    assert gate_status(stored) == "approved" and invoke("review", "plans", str(demo))["plans"] == []
    # Editing the plan after its check reopens the gate.
    path.write_text(json.dumps(stored.model_dump(mode="json") | {"cases": ["Two cases."]}))
    assert gate_status(Plan.model_validate_json(path.read_bytes())) == "changed"


def test_digests_go_stale_with_their_source(demo: Path) -> None:
    from tum_mcp.course.project.store import load_state

    source = next(item for item in load_state(demo).resources if item.status == "current")
    folder = demo / ".tum-mcp/digests"
    folder.mkdir(parents=True)
    body = {"source": source.resource.key, "sha256": source.sha256, "outcomes": ["Trace a search."]}
    (folder / f"{source.resource.key}.json").write_text(json.dumps(body))
    rows = {
        row["source"]: row["status"] for row in invoke("study", "digests", str(demo))["sources"]
    }
    assert rows[source.resource.key] == "current"
    (folder / f"{source.resource.key}.json").write_text(json.dumps(body | {"sha256": "0" * 64}))
    rows = {
        row["source"]: row["status"] for row in invoke("study", "digests", str(demo))["sources"]
    }
    assert rows[source.resource.key] == "stale"


def test_the_shipped_exemplar_passes_its_plan_answer_key_and_flags() -> None:
    import subprocess
    import sys
    from importlib.resources import files

    from tum_mcp.course.checks.answers import compare
    from tum_mcp.course.checks.report import quality_flags
    from tum_mcp.course.content.study import StudyContent
    from tum_mcp.course.review.models import INVARIANT_FLAGS

    folder = files("tum_mcp") / "bundled/exemplars"
    content = StudyContent.model_validate_json((folder / "study.json").read_bytes())
    unit = content.units[0].model_dump(mode="json")
    plan = Plan.model_validate_json((folder / "plans/study/bfs.json").read_bytes())
    assert plan_problems(plan, unit, None) == []
    output = subprocess.run(  # noqa: S603 - the packaged exemplar's answer key
        [sys.executable, "-I", str(folder / "checks/study/bfs.py")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    problems, compared = compare(unit, json.loads(output))
    assert problems == [] and compared >= 10
    assert not {flag["flag"] for flag in quality_flags(content, None)} & set(INVARIANT_FLAGS)


def test_this_week_resolves_from_the_recorded_schedule(demo: Path) -> None:
    from tum_mcp.course.project.store import load_state

    source = load_state(demo).resources[0].resource.key
    sessions = [
        {"on": "2026-11-02", "sources": [source], "basis": "tumonline", "label": "Lecture 3"},
        {"on": "2026-11-12", "sources": [source], "basis": "release"},
    ]
    (demo / ".tum-mcp/schedule.json").write_text(json.dumps({"sessions": sessions}))
    week = invoke("study", "schedule", str(demo), "--today", "2026-11-05")
    assert [s["label"] for s in week["this_week"]] == ["Lecture 3"]
    assert week["taught"] == [source] and week["next"]["on"] == "2026-11-12"
    assert week["proxy_dates"] == [source]
    sessions[0]["sources"] = ["no-such-source"]
    (demo / ".tum-mcp/schedule.json").write_text(json.dumps({"sessions": sessions}))
    result = CliRunner().invoke(app, ["study", "schedule", str(demo)])
    assert result.exit_code != 0 and "unknown sources" in str(result.exception)


def test_situation_questions_and_guides_without_a_picture_are_flagged(demo: Path) -> None:
    from tum_mcp.course.checks.report import quality_flags
    from tum_mcp.course.content.exercises import ExerciseContent
    from tum_mcp.course.content.study import StudyContent

    study, exercises = read_document(demo, "study"), read_document(demo, "exercises")

    def flagged() -> list[str]:
        found = quality_flags(
            StudyContent.model_validate(study), ExerciseContent.model_validate(exercises)
        )
        return [flag["item"] for flag in found if flag["flag"] == "text_only_question"]

    assert flagged() == []
    # Given a situation question and a guided exercise whose pictures are taken away.
    question = study["units"][0]["questions"][0]
    question["blocks"] = []
    exercise = exercises["sets"][0]["exercises"][0]
    exercise["statement"] = [block for block in exercise["statement"] if block["kind"] == "text"]
    for step in exercise["steps"]:
        step["blocks"] = []
    assert flagged() == [f"{study['units'][0]['key']}/{question['key']}", exercise["key"]]
    # A recall label cannot waive missing context.
    question["level"] = "recall"
    assert flagged() == [f"{study['units'][0]['key']}/{question['key']}", exercise["key"]]


def test_invalid_content_names_the_item_file(demo: Path) -> None:
    unit = read_document(demo, "study")["units"][0]
    path = demo / "app/study/units" / f"{unit['key']}.json"
    body = json.loads(path.read_bytes())
    body["blocks"][0]["pages"] = "page one"
    path.write_text(json.dumps(body))
    result = CliRunner().invoke(app, ["study", "build", str(demo)])
    assert result.exit_code != 0
    assert f"app/study/units/{unit['key']}.json at blocks.0" in str(result.exception)


def test_lists_in_sentences_and_shorter_definitions_are_flagged(demo: Path) -> None:
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review import loop

    document = read_document(demo, "study")
    unit = document["units"][0]
    path = demo / "app/study/units" / f"{unit['key']}.json"
    text = next(i for i, b in enumerate(unit["blocks"]) if b["kind"] == "text")
    term = next(i for i, b in enumerate(unit["blocks"]) if b["kind"] == "definition")
    unit["blocks"][text]["paragraphs"] = [
        "A capable agent needs language processing, knowledge representation, "
        "automated reasoning and machine learning.",
        "Premise 1: Socrates is a man. Premise 2: All men are mortal. Conclusion: He is mortal.",
    ]
    path.write_text(json.dumps(unit))
    # Given a later lecture's digest that defines the same term with its conditions.
    source = next(item for item in load_state(demo).resources if item.status == "current")
    name = unit["blocks"][term]["term"]
    fuller = (
        f"A {name} is one that keeps every condition the course states, holds for each input "
        "the method receives, and stays fixed while the procedure runs to completion."
    )
    folder = demo / ".tum-mcp/digests"
    folder.mkdir(parents=True)
    (folder / f"{source.resource.key}.json").write_text(
        json.dumps(
            {
                "source": source.resource.key,
                "sha256": source.sha256,
                "definitions": [{"pages": "2", "text": fuller}],
            }
        )
    )
    flags = {(f["flag"], f["item"]) for f in loop.load(demo).flags_by_item[f"study/{unit['key']}"]}
    assert ("inline_list", f"{unit['key']}#{text}") in flags
    assert ("inline_steps", f"{unit['key']}#{text}") in flags
    assert ("definition_refined", f"{unit['key']}#{term}") in flags


def test_a_broken_plan_holds_the_review_gate(demo: Path) -> None:
    from tum_mcp.course.review import loop

    unit = read_document(demo, "study")["units"][0]
    item = f"study/{unit['key']}"
    term = next(b["key"] for b in unit["blocks"] if b["kind"] == "definition")
    plan = {
        "item": item,
        "concepts": [{"name": "Term", "kind": "definition", "instance": "x", "blocks": [term]}],
    }
    path = demo / ".tum-mcp/plans" / f"{item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan))
    assert any(p.startswith("plan: Term") for p in loop.item_gate(loop.load(demo), item))
