import copy
import json
from pathlib import Path

import pytest
from documents import content_file
from test_preparation_workflow import bounded_scope, write
from test_review_loop import answer, packets
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import build
from tum_mcp.course.checks.plans import plan_packet, record_gate
from tum_mcp.course.review import loop
from tum_mcp.course.review.repair_scope import repair_scope
from tum_mcp.course.workflow import tasks
from tum_mcp.errors import CampusError


@pytest.fixture
def splitting(project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path, scope = bounded_scope(project)
    second = copy.deepcopy(scope["demands"][0])
    second["id"] = "degree-boundary"
    scope["demands"].append(second)
    write(path, scope)
    write(
        project / ".tum-mcp/batches/selected.json",
        {
            "course_key": scope["course_key"],
            "request": "Teach the degree rule and its boundary.",
            "items": ["study/graphs"],
            "preparations": ["bounded"],
        },
    )
    write(
        project / ".tum-mcp/plans/study/graphs.json",
        {
            "item": "study/graphs",
            "preparation": "bounded",
            "outcomes": ["apply"],
        },
    )
    approve(project)
    monkeypatch.setattr("tum_mcp.course.checks.preparation._browser_problems", lambda *args: [])
    build(project, publish=False)
    tasks.begin(project, "selected", 1, owner="test")
    loop.start(project, batch="selected")
    return project


def approve(project: Path) -> None:
    record_gate(
        project, [dict(entry, verdict="pass") for entry in plan_packet(project)["plans"]], "fresh"
    )


def split(project: Path) -> None:
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    unit = copy.deepcopy(next(unit for unit in content["units"] if unit["key"] == "graphs"))
    unit["key"] = "graphs-boundary"
    unit["title"] = "Degree rule boundary"
    content["units"].append(unit)
    path.write_text(json.dumps(content), encoding="utf-8")
    path = project / ".tum-mcp/preparation/bounded.json"
    scope = json.loads(path.read_bytes())
    scope["demands"][1]["target"]["unit"] = unit["key"]
    write(path, scope)
    path = project / ".tum-mcp/coverage.json"
    ledger = json.loads(path.read_bytes())
    ledger["sources"][0]["outcomes"][0]["units"].append(unit["key"])
    write(path, ledger)
    path = project / ".tum-mcp/batches/selected.json"
    batch = json.loads(path.read_bytes())
    batch["items"].append("study/graphs-boundary")
    write(path, batch)
    write(
        project / ".tum-mcp/plans/study/graphs-boundary.json",
        {
            "item": "study/graphs-boundary",
            "preparation": "bounded",
            "outcomes": ["apply"],
        },
    )
    approve(project)
    build(project, publish=False)


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("corroboration", [False, True])
def test_split_repair_finishes_same_round_without_copying_scores(
    splitting: Path, closed: bool, corroboration: bool
) -> None:
    sent = packets(splitting, loop.next_round(splitting))
    requirements = sent[0]["items"][0]["preparation"]["demands"]
    assert {entry["id"] for entry in requirements if "id" in entry} == {"degree", "degree-boundary"}
    assert any(entry.get("source") == "graphs" for entry in sent[0]["scope_dispositions"])
    for packet in sent:
        loop.record(splitting, answer(packet), "fresh")
    if closed:
        loop.close_round(splitting)
    split(splitting)
    if corroboration:
        path = splitting / ".tum-mcp/state.json"
        state = json.loads(path.read_bytes())
        source = copy.deepcopy(state["resources"][0])
        original = splitting / source["path"]
        source["resource"].update(key="corroboration", kind="other")
        source["path"] = "materials/other/material-corroboration.pdf"
        target = splitting / source["path"]
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(original.read_bytes())
        state["resources"].append(source)
        write(path, state)
        build(splitting, publish=False)
    result = CliRunner().invoke(
        app,
        ["review", "repair-scope", str(splitting), "--reason", "Separate the boundary decision."],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["added"] == ["study/graphs-boundary"]
    card = (
        loop.scorecard(loop.load(splitting), loop.read_state(splitting))
        if closed
        else loop.close_round(splitting)
    )
    state = loop.read_state(splitting)
    assert state and state.budget == state.round == 1 and len(state.rounds) == 1
    assert card["preparation"]["ready"]
    assert card["structural_repairs"][0]["added"] == ["study/graphs-boundary"]
    rows = {row["item"]: row for row in card["items"]}
    assert rows["study/graphs"]["fresh"]
    assert not rows["study/graphs-boundary"]["fresh"]
    assert rows["study/graphs-boundary"]["scores"] == {}
    assert not card["gate"] and not card["score_coverage"]["complete"]
    assert tasks.finish(splitting, owner="test")["ready"]


@pytest.mark.parametrize("violation", ["pending", "request", "source", "drop", "incomplete"])
def test_structural_repair_cannot_weaken_or_skip_checks(splitting: Path, violation: str) -> None:
    sent = packets(splitting, loop.next_round(splitting))
    if violation != "pending":
        for packet in sent:
            loop.record(splitting, answer(packet), "fresh")
    split(splitting)
    if violation in {"request", "drop"}:
        path = splitting / ".tum-mcp/batches/selected.json"
        batch = json.loads(path.read_bytes())
        if violation == "request":
            batch["request"] = "Only teach the easy part."
        else:
            batch["items"].remove("study/graphs")
        write(path, batch)
    if violation == "source":
        path = splitting / ".tum-mcp/preparation/bounded.json"
        scope = json.loads(path.read_bytes())
        scope["demands"].pop()
        write(path, scope)
    if violation == "incomplete":
        (splitting / ".tum-mcp/plans/study/graphs-boundary.json").unlink()
    before = loop.read_state(splitting)
    with pytest.raises(CampusError):
        repair_scope(splitting, "Split the boundary.")
    assert loop.read_state(splitting) == before
