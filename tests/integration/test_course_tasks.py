import json
from pathlib import Path

import pytest
from test_preparation_workflow import bounded_scope, write
from test_review_loop import answer, edit_first_block, packets

from tum_mcp.course.app.build import build
from tum_mcp.course.checks.plans import plan_packet, record_gate
from tum_mcp.course.review import loop
from tum_mcp.course.workflow import tasks
from tum_mcp.course.workflow.hooks import handle
from tum_mcp.errors import CampusError


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
