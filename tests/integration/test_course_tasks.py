import json
import sys
from pathlib import Path

import pytest
from documents import content_file
from test_preparation_workflow import bounded_scope, write
from test_review_loop import answer, edit_first_block, packets
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.browser_evidence import browser_identity, save_receipt
from tum_mcp.course.app.build import build
from tum_mcp.course.app.publish import unreviewed
from tum_mcp.course.checks.plans import plan_packet, record_gate
from tum_mcp.course.checks.preparation import _browser_problems
from tum_mcp.course.project.store import load_state
from tum_mcp.course.review import loop
from tum_mcp.course.workflow import tasks
from tum_mcp.course.workflow.hooks import handle
from tum_mcp.errors import CampusError
from tum_mcp.moodle.browsers import BrowserChoice


@pytest.fixture
def task_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-a")
    _, scope = bounded_scope(project)
    plan = project / ".tum-mcp/plans/study/graphs.json"
    write(plan, {"item": "study/graphs", "preparation": "bounded", "outcomes": ["apply"]})
    write(
        project / ".tum-mcp/batches/selected.json",
        {
            "course_key": scope["course_key"],
            "request": "Prepare the selected lesson.",
            "items": ["study/graphs"],
            "preparations": ["bounded"],
        },
    )
    (entry,) = plan_packet(project)["plans"]
    record_gate(
        project,
        [
            {
                "item": entry["item"],
                "fingerprint": entry["fingerprint"],
                "coverage_fingerprint": entry["coverage_fingerprint"],
                "verdict": "pass",
            }
        ],
        "fresh",
    )
    monkeypatch.setattr("tum_mcp.course.checks.preparation._browser_problems", lambda *a: [])
    build(project, publish=False)
    return project


def event(project: Path, owner: str = "thread-a", kind: str = "Stop") -> dict:
    return {"session_id": f"codex:{owner}", "cwd": str(project.parent), "hook_event_name": kind}


def test_guard_requires_receipt_and_never_starts_an_unapproved_review(task_project: Path) -> None:
    project = task_project
    tasks.begin(project, "selected")
    assert tasks.stop(event(project))["decision"] == "block"
    assert loop.read_state(project) is None
    assert tasks.finish(project)["ready"]
    edit_first_block(project)
    assert tasks.stop(event(project))["decision"] == "block"
    with pytest.raises(CampusError, match="built app"):
        tasks.finish(project)
    build(project, publish=False)
    tasks.finish(project)
    assert tasks.stop(event(project)) == {}
    assert tasks.read_task(project).phase == "complete"
    assert loop.read_state(project) is None
    edit_first_block(project)
    assert tasks.stop(event(project)) == {}


def test_finish_requires_each_demanded_answer_target_to_be_compared(task_project: Path) -> None:
    root = task_project
    scope_path = root / ".tum-mcp/preparation/bounded.json"
    scope = json.loads(scope_path.read_bytes())
    unit = json.loads((root / "app/study/units/graphs.json").read_bytes())
    target = "questions[0].explanation"
    scope["demands"][0]["values"] = [target]
    study = content_file(root, "study")
    content = json.loads(study.read_bytes())
    checked = next(u for u in content["units"] if u["key"] == "graphs")
    checked["questions"][0]["explanation"] = "The count is 12 items."
    sibling = next(u for u in content["units"] if u["key"] == "bfs")
    sibling["blocks"][0]["key"] = "frontier-model"
    study.write_text(json.dumps(content), encoding="utf-8")
    ledger = root / ".tum-mcp/coverage.json"
    coverage = json.loads(ledger.read_bytes())
    coverage["sources"].append(
        {
            "source": "bfs",
            "status": {"availability": "released", "checked_at": "2026-11-06"},
            "outcomes": [
                {"key": "frontier", "text": "Trace the queue.", "locator": "1", "units": ["bfs"]}
            ],
        }
    )
    write(ledger, coverage)
    scope["inventory"][1].update(
        disposition="required", basis="source", reason="Selected queue lesson.", locator="1"
    )
    scope["demands"].append(
        {
            "kind": "study",
            "id": "queue",
            "source": "bfs",
            "text": "Trace the queue.",
            "locator": "1",
            "outcome": "frontier",
            "level": "apply",
            "target": {
                "unit": "bfs",
                "blocks": ["frontier-model"],
                "objective": "queue",
                "question": "frontier",
                "reason": "Explain the order of waiting vertices.",
            },
        }
    )
    write(scope_path, scope)
    write(
        root / ".tum-mcp/plans/study/bfs.json",
        {"item": "study/bfs", "preparation": "bounded", "outcomes": ["frontier"]},
    )
    batch = root / ".tum-mcp/batches/selected.json"
    request = json.loads(batch.read_bytes())
    request["items"].append("study/bfs")
    write(batch, request)
    entries = plan_packet(root)["plans"]
    record_gate(root, [dict(entry, verdict="pass") for entry in entries], "fresh")
    build(root, publish=False)
    tasks.begin(root, "selected")

    path = root / ".tum-mcp/checks/study/graphs.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_name("bfs.py").write_text(
        f"import json\nprint(json.dumps({{'exact_values': {{'title': {sibling['title']!r}}}}}))\n"
    )
    runner = CliRunner()
    for script, status, reason in (
        (
            "print('{\"exact_values\":{}}')",
            "no_checks",
            "answer key compares nothing",
        ),
        (
            f"import json\nprint(json.dumps({{'exact_values': {{'title': {unit['title']!r}}}}}))",
            "passed",
            "missing or failed answer-key values",
        ),
        (
            f"import json\nprint(json.dumps({{'values': {{{target!r}: {10**309}}}}}))",
            "failed",
            f"study/graphs: {target}:",
        ),
        (
            r"import sys; sys.stdout.buffer.write(b'\xff')",
            "failed",
            "study/graphs: the answer key did not print UTF-8",
        ),
    ):
        path.write_text(script + "\n")
        verify = runner.invoke(app, ["study", "verify", str(root), "--json"])
        assert verify.exit_code == 0, verify.output or repr(verify.exception)
        entries = {item["item"]: item["status"] for item in json.loads(verify.output)["items"]}
        assert entries == {"study/graphs": status, "study/bfs": "passed"}
        result = runner.invoke(app, ["study", "task", "finish", str(root)])
        assert result.exit_code != 0 and reason in str(result.exception)
        assert "study/bfs" not in str(result.exception)

    expected = checked["questions"][0]["explanation"]
    path.write_text(
        f"import json\nprint(json.dumps({{'exact_values': {{{target!r}: {expected!r}}}}}))\n"
    )
    result = runner.invoke(app, ["study", "task", "finish", str(root)])
    assert result.exit_code == 0, result.output
    assert tasks.stop(event(root)) == {}


def test_mixed_batch_lists_the_next_prerequisite_for_each_workspace(task_project: Path) -> None:
    root = task_project
    batch = root / ".tum-mcp/batches/selected.json"
    request = json.loads(batch.read_bytes())
    request["items"] += ["exercises/sheet-1/blocked-item", "lecture/live-42-11"]
    write(batch, request)
    tasks.begin(root, "selected")
    tasks.pause(root, "The tie rule is missing.")
    tasks.begin(root, "selected")
    result = CliRunner().invoke(
        app,
        ["study", "report", str(root), "--section", "readiness", "--batch", "selected", "--json"],
    )
    assert result.exit_code == 0, result.output or repr(result.exception)
    readiness = json.loads(result.output)["readiness"]
    actions = readiness["workspace_actions"]
    assert not readiness["ready"]
    assert actions["study"]["status"] == "prepared"
    assert "exercises/sheet-1/blocked-item" in actions["exercises"]["prerequisite"]
    assert "lecture/live-42-11" in actions["lecture"]["prerequisite"]
    assert "Finish feasible siblings" in tasks.stop(event(root))["reason"]


@pytest.mark.parametrize("combined", [False, True], ids=["separate", "combined"])
def test_mixed_readiness_assigns_missing_study_contact_sheet(
    task_project: Path, monkeypatch: pytest.MonkeyPatch, combined: bool
) -> None:
    root = task_project
    batch = root / ".tum-mcp/batches/selected.json"
    request = json.loads(batch.read_bytes())
    exercise = "exercises/sheet-1/blocked-item"
    request["items"].append(exercise)
    if combined:
        scope_path = root / ".tum-mcp/preparation/bounded.json"
        scope = json.loads(scope_path.read_bytes())
        source = next(
            row for row in load_state(root).resources if row.resource.key == "exercise-graph"
        )
        scope["workspaces"].append("exercises")
        scope["inventory"].append(
            {
                "source": source.resource.key,
                "sha256": source.sha256,
                "disposition": "required",
                "basis": "source",
                "reason": "Selected original exercise.",
                "locator": "Exercise 1",
            }
        )
        scope["demands"].append(
            {
                "kind": "exercises",
                "id": "blocked-item",
                "source": source.resource.key,
                "label": "Exercise 1",
                "locator": "Exercise 1",
                "text": "Trace the search.",
                "blocked_reason": "The sheet omits the tie rule.",
                "target": {
                    "set": "sheet-1",
                    "exercise": "blocked-item",
                    "statement": "question",
                    "step": "trace",
                    "answer_block": 0,
                },
            }
        )
        ledger_path = root / ".tum-mcp/coverage.json"
        ledger = json.loads(ledger_path.read_bytes())
        ledger["sources"].append(
            {
                "source": source.resource.key,
                "status": {"availability": "released", "checked_at": "2026-11-06"},
                "items": [{"label": "Exercise 1", "status": "unavailable", "note": "No tie rule."}],
            }
        )
        write(ledger_path, ledger)
        write(scope_path, scope)
        (entry,) = plan_packet(root)["plans"]
        record_gate(root, [dict(entry, verdict="pass")], "fresh")
        build(root, publish=False)
    write(batch, request)
    browser = BrowserChoice("Synthetic browser", sys.executable)
    monkeypatch.setattr("tum_mcp.course.checks.preparation.browser_choice", lambda: browser)
    monkeypatch.setattr("tum_mcp.course.checks.preparation._browser_problems", _browser_problems)
    save_receipt(
        root,
        browser_identity(root, browser),
        {
            f"{state}/desktop/{target}": True
            for state, target in (
                ("interact", "#graphs/content"),
                ("shell", "light/study"),
                ("shell", "dark/study"),
            )
        },
    )
    result = CliRunner().invoke(
        app,
        ["study", "report", str(root), "--section", "readiness", "--batch", "selected", "--json"],
    )
    assert result.exit_code == 0, result.output or repr(result.exception)
    readiness = json.loads(result.output)["readiness"]
    problem = "visual/desktop/study/graphs: browser evidence is missing."
    workspace = readiness["workspace_problems"]
    assert workspace["study"] == [problem]
    assert f"{exercise}: requested draft is missing." in workspace["exercises"]
    if combined:
        assert any("omits the tie rule" in issue for issue in workspace["exercises"])
    assert not readiness["ready"]
    assert readiness["workspace_actions"]["study"] == {
        "status": "pending",
        "prerequisite": problem,
        "command": "tum-mcp study visuals .",
        "problems": 1,
    }


def test_schema_suggestion_executes() -> None:
    runner = CliRunner()
    unknown = runner.invoke(app, ["study", "schema", "preparaton"])
    assert unknown.exit_code != 0
    assert "tum-mcp study schema preparation" in str(unknown.exception)
    suggested = runner.invoke(app, ["study", "schema", "preparation"])
    assert suggested.exit_code == 0, suggested.output or repr(suggested.exception)
    assert json.loads(suggested.output)["title"] == "Preparation"


@pytest.mark.parametrize("decision", ["schedule", "links"])
def test_changed_course_decision_invalidates_the_finish_receipt(
    task_project: Path, decision: str
) -> None:
    project = task_project
    tasks.begin(project, "selected")
    assert tasks.finish(project)["ready"]
    path = project / f".tum-mcp/{decision}.json"
    path.write_bytes((path.read_bytes() if path.exists() else b"{}") + b"\n")
    assert tasks.stop(event(project))["decision"] == "block"


def test_guard_requires_requested_round_and_keeps_its_budget(task_project: Path) -> None:
    project = task_project
    tasks.begin(project, "selected", 1)
    with pytest.raises(CampusError, match="authorized combined review"):
        tasks.finish(project)
    loop.start(project, batch="selected")
    for packet in packets(project, loop.next_round(project)):
        loop.record(project, answer(packet), "fresh")
    loop.close_round(project)
    tasks.finish(project)
    assert tasks.stop(event(project)) == {}
    state = loop.read_state(project)
    assert state.budget == state.round == 1

    batch = project / ".tum-mcp/batches/selected.json"
    request = json.loads(batch.read_bytes())
    request["request"] += " Also teach another boundary."
    write(batch, request)
    (entry,) = plan_packet(project)["plans"]
    record_gate(project, [dict(entry, verdict="pass")], "fresh")
    with pytest.raises(CampusError, match="authorized combined review"):
        tasks.finish(project)


def test_a_later_task_finishes_the_round_it_added_to_an_earlier_review(task_project: Path) -> None:
    # A student asked for one more review; the new task's round extended a review that already
    # had one, and finish compared the task's 1 with the review's 2.
    project = task_project
    tasks.begin(project, "selected", 1)
    loop.start(project, batch="selected")
    for packet in packets(project, loop.next_round(project)):
        loop.record(project, answer(packet), "fresh")
    # A repair after the last check leaves the spent round waiting for verification.
    edit_first_block(project)
    build(project, publish=False)
    assert loop.close_round(project)["status"] == "budget_spent"
    tasks.finish(project)
    assert tasks.stop(event(project)) == {}

    tasks.begin(project, "selected", 1)
    loop.extend(project, 1)
    for packet in packets(project, loop.next_round(project)):
        loop.record(project, answer(packet), "fresh")
    loop.close_round(project)

    assert tasks.finish(project)["ready"]
    state = loop.read_state(project)
    assert state and state.budget == state.round == 2


def test_budget_change_cannot_finish_an_additional_review_task(task_project: Path) -> None:
    root = task_project
    tasks.begin(root, "selected", 1)
    loop.start(root, batch="selected")
    for packet in packets(root, loop.next_round(root)):
        loop.record(root, answer(packet), "fresh")
    assert loop.close_round(root)["status"] == "passed"
    assert tasks.finish(root)["ready"]
    assert tasks.stop(event(root)) == {}
    held = unreviewed(root)
    assert held and "study/graphs" not in held

    tasks.begin(root, "selected", 1)
    loop.extend(root, 1)
    with pytest.raises(CampusError, match="authorized combined review"):
        tasks.finish(root)
    loop.start(root, budget=1, batch="selected")
    fresh = packets(root, loop.next_round(root))
    assert fresh
    for packet in fresh:
        loop.record(root, answer(packet), "fresh")
    loop.close_round(root)
    assert tasks.finish(root)["ready"]


def test_over_limit_review_extension_preserves_state(task_project: Path) -> None:
    root = task_project
    loop.start(root, budget=20, batch="selected")
    path = root / ".tum-mcp/loop.json"
    before = path.read_bytes()
    with pytest.raises(CampusError, match="20"):
        loop.extend(root, 1)
    assert path.read_bytes() == before
    assert loop.read_state(root).budget == 20


def test_guard_respects_other_threads_and_user_interruptions(task_project: Path) -> None:
    project = task_project
    tasks.begin(project, "selected", 1)
    before = (project / tasks.NAME).read_bytes()
    assert tasks.stop(event(project, "thread-b")) == {}
    assert (project / tasks.NAME).read_bytes() == before
    assert tasks.stop(event(project, kind="Interrupt")) == {}
    assert tasks.read_task(project).phase == "paused"
    assert tasks.stop(event(project)) == {}
    resumed = tasks.begin(project, "selected", 1)
    assert resumed.phase == "pending" and resumed.review_before is None


def test_guard_stops_a_stalled_task_instead_of_looping_forever(task_project: Path) -> None:
    project = task_project
    tasks.begin(project, "selected")
    for _ in range(3):
        assert tasks.stop(event(project))["decision"] == "block"
    stopped = tasks.stop(event(project))
    assert stopped["continue"] is False
    assert tasks.read_task(project).phase == "stalled"


def test_wsl_guard_resolves_the_windows_client_workspace(
    task_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks.begin(task_project, "selected")
    monkeypatch.setattr(tasks, "is_wsl", lambda: True)
    monkeypatch.setattr(tasks, "wsl_path", lambda path: str(task_project.parent))
    payload = event(task_project)
    payload["cwd"] = "C:\\Courses"
    assert tasks.stop(payload)["decision"] == "block"


def native_payload(host: str, project: Path) -> dict:
    if host == "cursor":
        return {
            "conversation_id": "native",
            "workspace_roots": [str(project.parent)],
            "status": "completed",
        }
    if host == "antigravity":
        return {
            "conversationId": "native",
            "workspacePaths": [str(project.parent)],
            "fullyIdle": True,
            "terminationReason": "model_stop",
        }
    return {"session_id": "native", "cwd": str(project.parent)}


@pytest.mark.parametrize("host", ["codex", "claude", "cursor", "antigravity"])
def test_native_hosts_continue_only_their_registered_task(task_project: Path, host: str) -> None:
    owner = f"{host}:native"
    tasks.begin(task_project, "selected", owner=owner)
    payload = native_payload(host, task_project)
    result = handle(host, payload, "Stop" if host != "cursor" else "stop")
    if host == "cursor":
        assert result["followup_message"]
    else:
        assert result["decision"] == ("continue" if host == "antigravity" else "block")
    tasks.finish(task_project, owner=owner)
    assert handle(host, payload, "Stop") == ({"decision": "stop"} if host == "antigravity" else {})


@pytest.mark.parametrize("host", ["codex", "claude", "cursor", "antigravity"])
def test_native_cancellation_never_continues(task_project: Path, host: str) -> None:
    tasks.begin(task_project, "selected", owner=f"{host}:native")
    payload = native_payload(host, task_project)
    kind = "Interrupt" if host == "codex" else "SessionEnd" if host == "claude" else "Stop"
    if host == "cursor":
        payload["status"] = "aborted"
    if host == "antigravity":
        payload["terminationReason"] = "max_steps_exceeded"
    result = handle(host, payload, kind)
    assert "followup_message" not in result and result.get("decision") != "continue"
    assert tasks.read_task(task_project).phase == "paused"


@pytest.mark.parametrize("host", ["codex", "claude", "cursor", "antigravity"])
def test_native_context_supplies_identity_without_starting_a_task(
    task_project: Path, host: str
) -> None:
    import json

    result = handle(host, native_payload(host, task_project), "SessionStart")
    assert f"--owner {host}:native" in json.dumps(result)
    assert tasks.read_task(task_project) is None


def test_antigravity_waits_for_background_tasks(task_project: Path) -> None:
    tasks.begin(task_project, "selected", owner="antigravity:native")
    payload = native_payload("antigravity", task_project)
    payload["fullyIdle"] = False
    before = (task_project / tasks.NAME).read_bytes()
    assert handle("antigravity", payload, "Stop") == {}
    assert (task_project / tasks.NAME).read_bytes() == before


def test_removed_derived_item_does_not_block_completed_repairs(task_project: Path) -> None:
    import json

    from tum_mcp.course.review.ledger import Finding, ItemRecord, read_record, save

    tasks.begin(task_project, "selected", 1)
    loop.start(task_project, batch="selected")
    for packet in packets(task_project, loop.next_round(task_project)):
        loop.record(task_project, answer(packet), "fresh")
    loop.close_round(task_project)
    path = task_project / ".tum-mcp/loop.json"
    state = json.loads(path.read_text())
    retired = "lecture/recording/removed-highlight"
    state["scope"].append(retired)
    path.write_text(json.dumps(state))
    finding = Finding(
        id="F1",
        check="integration.lecture_links",
        quote="Removed clip",
        location="teaches",
        why="No matching prepared passage.",
        fix="Remove the redundant clip.",
        opened=1,
        block="teaches",
    )
    save(task_project, [ItemRecord(item=retired, findings=(finding,))])

    assert tasks.finish(task_project)["ready"]

    current = read_record(task_project, "study/graphs")
    save(task_project, [current.model_copy(update={"findings": (finding,)})])
    with pytest.raises(CampusError, match="remaining review findings"):
        tasks.finish(task_project)
