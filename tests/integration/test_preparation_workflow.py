import json
import os
from pathlib import Path

import pytest
from documents import content_file
from test_review_loop import answer, packets
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import build
from tum_mcp.course.checks.plans import read_plan, record_gate
from tum_mcp.course.project.store import load_state
from tum_mcp.course.review import loop
from tum_mcp.errors import CampusError


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def bounded_scope(project: Path) -> tuple[Path, dict]:
    content = content_file(project, "study")
    data = json.loads(content.read_bytes())
    unit = next(unit for unit in data["units"] if unit["key"] == "graphs")
    unit["blocks"][0]["key"] = "model-example"
    content.write_text(json.dumps(data), encoding="utf-8")

    state = load_state(project)
    write(
        project / ".tum-mcp/coverage.json",
        {
            "course_key": state.course.key,
            "sources": [
                {
                    "source": "graphs",
                    "status": {"availability": "released", "checked_at": "2026-11-06"},
                    "outcomes": [
                        {
                            "key": "apply",
                            "text": "Apply the degree rule.",
                            "locator": "2",
                            "units": ["graphs"],
                        },
                        {"key": "later", "text": "Solve later topics.", "locator": "1"},
                    ],
                },
            ],
        },
    )
    plans = project / ".tum-mcp/plans/study/graphs.json"
    write(plans, {"item": "study/graphs", "outcomes": ["apply"]})
    plan = read_plan(project, "study/graphs")
    assert plan is not None
    record_gate(
        project, [{"item": plan.item, "fingerprint": plan.fingerprint(), "verdict": "pass"}], "same"
    )
    resources = {entry.resource.key: entry.sha256 for entry in state.resources}
    scope = {
        "course_key": state.course.key,
        "semester": state.course.semester,
        "workspaces": ["study"],
        "mode": "selected_sources",
        "inventory": [
            {
                "source": "graphs",
                "sha256": resources["graphs"],
                "disposition": "required",
                "basis": "source",
                "reason": "Selected first lecture.",
                "locator": "2",
                "deferred_outcomes": {"later": "Semester roadmap."},
            },
            {
                "source": "bfs",
                "sha256": resources["bfs"],
                "disposition": "unresolved",
                "basis": "unknown",
                "reason": "Teaching date unverified.",
                "locator": "Listing",
            },
        ],
        "demands": [
            {
                "kind": "study",
                "id": "degree",
                "source": "graphs",
                "text": "Apply the degree rule.",
                "locator": "2",
                "outcome": "apply",
                "level": "apply",
                "target": {
                    "unit": "graphs",
                    "blocks": ["model-example"],
                    "objective": "model",
                    "question": "degree-sum",
                    "reason": "Computes the sum of degrees on the question graph.",
                },
            },
        ],
    }
    path = project / ".tum-mcp/preparation/bounded.json"
    write(path, scope)
    return path, scope


def readiness(project: Path) -> dict:
    result = CliRunner().invoke(
        app, ["study", "report", str(project), "--section", "readiness", "--preparation", "bounded"]
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["readiness"]


def test_a_coverage_link_alone_does_not_make_a_preparation_ready(project: Path) -> None:
    legacy = loop.start(project, budget=3)
    assert not readiness(project)["ready"]
    path, scope = bounded_scope(project)
    scope["demands"][0]["level"] = "reason"
    write(path, scope)
    result = readiness(project)
    assert not result["ready"] and any("action level" in problem for problem in result["problems"])
    with pytest.raises(CampusError, match="not ready"):
        loop.start(project, preparation="bounded")
    assert loop.read_state(project) == legacy
    scope["demands"][0]["level"] = "apply"
    scope["demands"][0]["values"] = ["questions[0].explanation"]
    write(path, scope)
    assert any("answer-key" in problem for problem in readiness(project)["problems"])


def test_preflight_requires_each_exercise_part_and_its_own_evidence(exercise_project: Path) -> None:
    root = exercise_project
    state = load_state(root)
    sheet = next(
        resource for resource in state.resources if resource.resource.key == "exercise-graph"
    )
    source = {"key": sheet.resource.key, "sha256": sheet.sha256}
    document = content_file(root, "exercises")
    content = json.loads(document.read_bytes())
    group = content["sets"][0]
    group["sheet"] = source["key"]
    exercise = group["exercises"][0]
    exercise["sources"].append(source)
    exercise["parts"] = ["(a)", "(b)"]
    exercise["part_blocks"] = {"(a)": "cost", "(b)": "decision"}
    statement = exercise["statement"][0]
    exercise["statement"] = [
        statement | {"key": "cost"},
        statement | {"key": "decision", "title": "Compare the candidate with the current cost"},
    ]
    for step, part in zip(exercise["steps"], ["(a)", "(a)", "(b)"], strict=True):
        step["part"] = part
    solution = exercise["solution"]["answers"][0]
    exercise["solution"]["answers"] = [solution | {"label": part} for part in exercise["parts"]]
    document.write_text(json.dumps(content))
    write(
        root / ".tum-mcp/coverage.json",
        {
            "course_key": state.course.key,
            "sources": [
                {
                    "source": source["key"],
                    "status": {"availability": "released", "checked_at": "2026-11-06"},
                    "items": [{"label": "Exercise 1", "exercise": exercise["key"]}],
                }
            ],
        },
    )
    demands = [
        {
            "kind": "exercises",
            "id": block,
            "source": source["key"],
            "text": "Solve the original part.",
            "locator": "Exercise 1 " + part,
            "label": "Exercise 1",
            "part": part,
            "target": {
                "set": group["key"],
                "exercise": exercise["key"],
                "part": part,
                "statement": block,
                "step": step,
                "answer_block": 0,
            },
        }
        for part, block, step in (
            ("(a)", "cost", "candidate"),
            ("(b)", "decision", "transfer-choice"),
        )
    ]
    scope = {
        "course_key": state.course.key,
        "semester": state.course.semester,
        "workspaces": ["exercises"],
        "mode": "selected_sources",
        "inventory": [
            {
                "source": source["key"],
                "sha256": source["sha256"],
                "disposition": "required",
                "basis": "source",
                "reason": "Selected exercise.",
                "locator": "Exercise 1",
            }
        ],
        "demands": demands[:1],
    }
    path = root / ".tum-mcp/preparation/bounded.json"
    write(path, scope)
    assert any("missing original part mappings (b)" in p for p in readiness(root)["problems"])

    scope["demands"] = demands
    demands[1]["target"]["step"] = "candidate"
    write(path, scope)
    assert any("guide step does not belong" in p for p in readiness(root)["problems"])

    demands[1]["target"]["step"] = "transfer-choice"
    demands[1]["target"]["answer_block"] = len(solution["blocks"])
    write(path, scope)
    assert any("answer block is missing" in p for p in readiness(root)["problems"])

    demands[1]["target"]["answer_block"] = 0
    write(path, scope)
    assert len(readiness(root)["items"]["exercises/sheet-1/sample-relaxation"]) == 2


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Owned browser QA."
)
def test_prepared_review_uses_current_build_and_scope(project: Path) -> None:
    path, scope = bounded_scope(project)
    build(project, publish=False)
    runner = CliRunner()

    def check_draft() -> None:
        for extra in ([], ["--interact"]):
            result = runner.invoke(
                app,
                ["study", "visuals", str(project), "--unit", "graphs", "--phone", "--json", *extra],
            )
            assert result.exit_code == 0, result.output
            assert json.loads(result.output)["passed"], result.output

    check_draft()
    report = readiness(project)
    assert report["ready"], report
    assert report["dispositions"][1]["disposition"] == "unresolved"
    result = runner.invoke(app, ["review", "start", str(project), "--preparation", "bounded"])
    assert result.exit_code == 0, result.output
    state = loop.read_state(project)
    assert state and state.scope == ("study/graphs",) and state.budget == 1
    assert loop.start(project, preparation="bounded") == state
    opened = loop.next_round(project)
    sent = packets(project, opened)
    assert [item["item"] for packet in sent for item in packet["items"]] == ["study/graphs"]
    assert sent[0]["scope_dispositions"][1]["disposition"] == "unresolved"

    target = scope["demands"][0]["target"]
    old_reason = target["reason"]
    target["reason"] = "A changed mapping makes the packet stale."
    write(path, scope)
    with pytest.raises(CampusError, match="content changed since the packet"):
        loop.record(project, answer(sent[0]), "fresh")
    target["reason"] = old_reason
    write(path, scope)
    loop.record(project, answer(sent[0], fail={"study/graphs": "clarity.one_reading"}), "same")
    card = loop.close_round(project)
    assert card["status"] == "budget_spent" and card["scope_type"] == "prepared"
    assert card["items_by_provenance"]["provisional"] == 1
    assert card["rounds"][0]["answered_packets"] == 1

    record = loop.load(project).record("study/graphs")
    finding = record.findings[0]
    content = content_file(project, "study")
    value = json.loads(content.read_bytes())
    unit = next(unit for unit in value["units"] if unit["key"] == "graphs")
    index = int(finding.location.split("[", 1)[1].split("]", 1)[0])
    unit["blocks"][index]["paragraphs"][0] += " A clearer reading."
    content.write_text(json.dumps(value))
    fixed = runner.invoke(
        app, ["review", "fix", str(project), "--item", record.item, "--finding", finding.id]
    )
    assert fixed.exit_code == 0, fixed.output
    assert loop.status(project)["fixes_to_verify"] == 1
    assert any("built app" in problem for problem in readiness(project)["problems"])
    loop.extend(project, 1)
    with pytest.raises(CampusError, match="built app"):
        loop.next_round(project)

    build(project, publish=False)
    check_draft()
    follow_up = packets(project, loop.next_round(project))
    assert [
        repair["id"]
        for packet in follow_up
        for entry in packet["items"]
        for repair in entry["verify"]
    ] == [finding.id]
    for packet in follow_up:
        loop.record(project, answer(packet), "fresh")
    loop.close_round(project)
    assert loop.load(project).record(record.item).findings[0].status == "verified"
