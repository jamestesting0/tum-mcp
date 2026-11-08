import json
from pathlib import Path

import pytest
from test_preparation_workflow import bounded_scope, write
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.checks.coverage_plan import assess_plan
from tum_mcp.course.checks.plans import gate_status, plan_packet, read_plan, record_gate
from tum_mcp.course.checks.preparation import assess
from tum_mcp.course.content.store import remove_document
from tum_mcp.errors import CampusError


def test_source_coverage_is_determined_without_an_authored_draft(project: Path) -> None:
    bounded_scope(project)
    remove_document(project, "study")

    result = CliRunner().invoke(
        app,
        ["study", "report", str(project), "--section", "coverage-plan", "--preparation", "bounded"],
    )

    assert result.exit_code == 0, result.output
    planned = json.loads(result.output)["coverage_plan"]
    assert planned["ready"] and list(planned["items"]) == ["study/graphs"]
    assert not assess(project, "bounded").ready


def test_plan_approval_binds_source_coverage_and_refuses_a_weakened_scope(project: Path) -> None:
    path, scope = bounded_scope(project)
    plan_path = project / ".tum-mcp/plans/study/graphs.json"
    write(plan_path, {"item": "study/graphs", "preparation": "bounded", "outcomes": ["apply"]})
    packet = plan_packet(project)
    (plan,) = packet["plans"]
    assert packet["answer"]["items"][0]["coverage_fingerprint"] == plan["coverage_fingerprint"]
    assert (
        packet["coverage"]["bounded"]["items"]["study/graphs"][0]["text"]
        == "Apply the degree rule."
    )
    answer = {
        "item": plan["item"],
        "fingerprint": plan["fingerprint"],
        "coverage_fingerprint": plan["coverage_fingerprint"],
        "verdict": "pass",
    }
    record_gate(project, [answer], "fresh")
    checked = read_plan(project, "study/graphs")
    assert checked and checked.gate
    assert checked.gate.coverage_fingerprint == assess_plan(project, "bounded").scope.fingerprint

    scope["demands"][0]["text"] = "Recall only the degree rule."
    write(path, scope)

    with pytest.raises(CampusError, match="coverage changed"):
        record_gate(project, [answer], "fresh")
    assert (
        plan_packet(project)["plans"][0]["coverage_fingerprint"] != answer["coverage_fingerprint"]
    )
    assert any(
        "source coverage changed" in problem for problem in assess(project, "bounded").problems
    )
    lint = CliRunner().invoke(
        app, ["study", "lint", str(project), "--item", "study/graphs", "--json"]
    )
    assert lint.exit_code == 0, lint.output
    assert json.loads(lint.output)["plan"]["status"] == "changed"


def test_plan_checker_sees_the_original_request_and_request_changes_reopen_approval(
    project: Path,
) -> None:
    _, scope = bounded_scope(project)
    batch_path = project / ".tum-mcp/batches/selected.json"
    batch = {
        "course_key": scope["course_key"],
        "request": "Prepare the whole degree-rule lesson, including its conditions.",
        "items": ["study/graphs"],
        "preparations": ["bounded"],
    }
    write(batch_path, batch)
    write(
        project / ".tum-mcp/plans/study/graphs.json",
        {"item": "study/graphs", "preparation": "bounded", "outcomes": ["apply"]},
    )
    packet = plan_packet(project)
    assert packet["coverage"]["bounded"]["request"]["request"] == batch["request"]
    (entry,) = packet["plans"]
    record_gate(project, [dict(entry, verdict="pass")], "fresh")
    batch["request"] += " Include a counterexample too."
    write(batch_path, batch)
    with pytest.raises(CampusError, match="coverage changed"):
        record_gate(project, [dict(entry, verdict="pass")], "fresh")
    assert plan_packet(project)["plans"]


def test_a_task_for_another_batch_keeps_plan_approval(project: Path) -> None:
    # In a trial every approved lesson plan reported "source coverage changed" once the
    # student started a task for the next workspace.
    from tum_mcp.course.workflow.tasks import begin, pause

    _, scope = bounded_scope(project)
    lessons = {
        "course_key": scope["course_key"],
        "request": "Prepare the degree lesson.",
        "items": ["study/graphs"],
        "preparations": ["bounded"],
    }
    write(project / ".tum-mcp/batches/lessons.json", lessons)
    sheet = dict(lessons, request="Prepare the first sheet.", items=["exercises/one/a"])
    write(project / ".tum-mcp/batches/sheet.json", dict(sheet, preparations=[]))
    write(
        project / ".tum-mcp/plans/study/graphs.json",
        {"item": "study/graphs", "preparation": "bounded", "outcomes": ["apply"]},
    )
    begin(project, "lessons", owner="codex:first")
    (entry,) = plan_packet(project)["plans"]
    record_gate(project, [dict(entry, verdict="pass")], "fresh")
    pause(project, "The lesson draft is done.", owner="codex:first")
    begin(project, "sheet", owner="codex:second")

    plan = read_plan(project, "study/graphs")
    assert plan and gate_status(plan, project) == "approved"

    # A later batch that groups this one for a combined review keeps the approval too.
    everything = dict(lessons, request="Review everything.", items=["study/graphs"])
    write(project / ".tum-mcp/batches/everything.json", everything)
    assert gate_status(plan, project) == "approved"
    lessons["request"] += " Include its proof."
    write(project / ".tum-mcp/batches/lessons.json", lessons)
    assert gate_status(plan, project) == "changed"


def test_invalid_outcome_mapping_names_the_overlap_and_accepted_ids(project: Path) -> None:
    path, scope = bounded_scope(project)
    scope["inventory"][0]["deferred_outcomes"] = {"apply": "Incorrectly deferred."}
    write(path, scope)
    report = assess_plan(project, "bounded")
    assert not report.ready
    assert any(
        "both required and deferred: apply" in problem and "core outcome IDs:" in problem
        for problem in report.problems
    )


def test_artifact_reorganization_preserves_source_plan_approval(project: Path) -> None:
    _, scope = bounded_scope(project)
    batch_path = project / ".tum-mcp/batches/selected.json"
    batch = {
        "course_key": scope["course_key"],
        "request": "Prepare the degree lesson and an exam forecast.",
        "items": ["study/graphs", "exam/mock/retake/q1"],
        "preparations": ["bounded"],
    }
    write(batch_path, batch)
    write(
        project / ".tum-mcp/plans/study/graphs.json",
        {"item": "study/graphs", "preparation": "bounded", "outcomes": ["apply"]},
    )
    (entry,) = plan_packet(project)["plans"]
    record_gate(project, [dict(entry, verdict="pass")], "fresh")
    batch["items"][1] = "exam/mock/forecast/q1"
    write(batch_path, batch)

    assert plan_packet(project)["plans"] == []


def test_recording_a_rejected_plan_reports_its_failure_and_next_action(project: Path) -> None:
    bounded_scope(project)
    write(
        project / ".tum-mcp/plans/study/graphs.json",
        {"item": "study/graphs", "preparation": "bounded", "outcomes": ["apply"]},
    )
    (entry,) = plan_packet(project)["answer"]["items"]
    entry.update(verdict="fail", reasons=["The example does not show the result."])
    result = record_gate(project, [entry], "fresh")
    assert result["verdicts"]["study/graphs"] == {"verdict": "fail", "reasons": entry["reasons"]}
    assert "Repair the rejected plans" in result["next"]
