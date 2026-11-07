"""A thread-owned course task and a local, evidence-based completion guard."""

import os
import shlex
from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import Field

from tum_mcp.course.checks.batch import Batch, assess_batch
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.course.project.store import (
    Write,
    apply,
    confined,
    digest,
    load_state,
    private_path,
    read_bytes,
)
from tum_mcp.course.review.ledger import read_record
from tum_mcp.course.review.loop import read_state
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.browsers import is_wsl, wsl_path
from tum_mcp.settings import Frozen

NAME = ".tum-mcp/task.json"


class Task(Frozen):
    owner: str = Field(min_length=1, max_length=200)
    batch: Key
    review_rounds: int = Field(default=0, ge=0, le=20)
    phase: Literal["pending", "ready", "complete", "paused", "stalled"] = "pending"
    inputs: Digest | None = None
    review_before: Digest | None = None
    last_inputs: Digest | None = None
    stagnant: int = Field(default=0, ge=0, le=3)
    reason: str = Field(default="", max_length=2000)


def read_task(root: Path) -> Task | None:
    body = read_bytes(confined(root, NAME))
    return Task.model_validate_json(body) if body is not None else None


def _save(root: Path, task: Task) -> Task:
    apply(root, (Write(NAME, read_bytes(confined(root, NAME)), task.model_dump_json().encode()),))
    return task


def _owner(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    owner = os.environ.get("CODEX_THREAD_ID")
    if not owner:
        raise CampusError(
            Code.ACTION_REQUIRED, "Supply the --owner identity from your host's hook context."
        )
    return f"codex:{owner}"


def begin(root: Path, batch: str, review_rounds: int = 0, *, owner: str | None = None) -> Task:
    task = Task(owner=_owner(owner), batch=batch, review_rounds=review_rounds)
    body = read_bytes(private_path(root, f"batches/{task.batch}.json"))
    if body is None:
        raise CampusError(Code.ACTION_REQUIRED, "Record the batch before starting its task.")
    request = Batch.model_validate_json(body)
    if request.course_key != load_state(root).course.key:
        raise CampusError(Code.SCOPE_DENIED, "The task belongs to another course.")
    existing = read_task(root)
    if (
        existing
        and existing.owner == task.owner
        and existing.phase in {"paused", "stalled"}
        and (existing.batch, existing.review_rounds) == (task.batch, task.review_rounds)
    ):
        return _save(
            root, existing.model_copy(update={"phase": "pending", "stagnant": 0, "reason": ""})
        )
    if existing and existing.phase in {"pending", "ready"}:
        if existing.owner != task.owner:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Another thread owns this active course task."
            )
        if (existing.batch, existing.review_rounds) != (task.batch, task.review_rounds):
            raise CampusError(
                Code.ACTION_REQUIRED, "Pause the existing task before changing its scope."
            )
        return existing
    review = read_state(root)
    return _save(
        root,
        task.model_copy(
            update={"review_before": digest(review.model_dump_json().encode()) if review else None}
        ),
    )


def _owned(root: Path, owner: str | None = None) -> Task:
    task = read_task(root)
    if task is None or task.owner != _owner(owner):
        raise CampusError(Code.SCOPE_DENIED, "No course task is owned by this thread.")
    return task


def inputs(root: Path) -> str:
    """Hash authoring and checked evidence, excluding raw media, caches and this task."""
    paths = set((root / "app").rglob("*")) if (root / "app").exists() else set()
    for pattern in (
        "state.json",
        "course.md",
        "digests/*.json",
        "coverage.json",
        "batches/*.json",
        "preparation/*.json",
        "plans/**/*.json",
        "checks/**/*.py",
        "lecture-review/*.json",
        "loop.json",
        "review/items/**/*.json",
        "browser-check.json",
        "visual-check.json",
        "lectures/*/receipt.json",
        "lectures/*/transcript.json",
        "lectures/*/frames.json",
        "lecture-assets/*",
    ):
        paths.update(private_path(root, "").glob(pattern))
    paths.update(confined(root, entry.path) for entry in load_state(root).resources if entry.path)
    records = []
    for path in sorted(paths):
        if path.is_file():
            name = path.relative_to(root).as_posix()
            records.append((name, digest(confined(root, name).read_bytes())))
    return digest(repr(records).encode())


def finish(root: Path, *, owner: str | None = None) -> dict:
    task = _owned(root, owner)
    readiness = assess_batch(root, task.batch)
    if not readiness.ready:
        raise CampusError(Code.ACTION_REQUIRED, readiness.report()["next_action"])
    if task.review_rounds:
        from tum_mcp.course.review.repair_scope import contract

        review = read_state(root)
        if (
            review is None
            or review.batch is None
            or review.batch.identifier != task.batch
            or review.batch != readiness.scope
            or not set(readiness.items) <= set(review.scope)
            or (
                review.batch_contract is not None
                and review.batch_contract != contract(root, task.batch, review.batch_sources)
            )
            or review.budget != task.review_rounds
            or review.status == "running"
            or not review.rounds
            or review.rounds[-1].closed is None
            or review.rounds[-1].pending_packets
            or digest(review.model_dump_json().encode()) == task.review_before
        ):
            raise CampusError(
                Code.ACTION_REQUIRED, "Finish the authorized combined review and repair."
            )
        if any(
            finding.status in {"open", "reopened"}
            for key in review.scope
            if key in readiness.items
            for finding in read_record(root, key).findings
        ):
            raise CampusError(
                Code.ACTION_REQUIRED, "Repair or explicitly address the remaining review findings."
            )
    _save(root, task.model_copy(update={"phase": "ready", "inputs": inputs(root)}))
    return {
        "ready": True,
        "next_action": (
            "Report review scores, repairs and remaining verification; do not extend the budget."
            if task.review_rounds
            else "Report the complete draft and ask whether to review once."
        ),
    }


def pause(root: Path, reason: str, *, owner: str | None = None) -> Task:
    if not reason.strip():
        raise CampusError(
            Code.ACTION_REQUIRED, "Record the user's stop or the concrete external blocker."
        )
    return _save(root, _owned(root, owner).model_copy(update={"phase": "paused", "reason": reason}))


def stop(payload: dict) -> dict:
    """Only an explicitly registered task of this thread may request continuation."""
    owner, cwd = payload.get("session_id"), payload.get("cwd")
    if not isinstance(owner, str) or not isinstance(cwd, str):
        return {}
    roots = payload.get("workspace_roots", [cwd])
    locations = set()
    for workspace_root in roots:
        workspace = Path(
            wsl_path(workspace_root)
            if is_wsl() and PureWindowsPath(workspace_root).is_absolute()
            else workspace_root
        ).resolve()
        locations.update((workspace / NAME, *workspace.glob("*/" + NAME)))
    reasons, stalled = [], []
    for location in sorted(locations):
        root = location.parent.parent
        task = read_task(root)
        if task is None or task.owner != owner or task.phase in {"complete", "paused", "stalled"}:
            continue
        if payload.get("hook_event_name") == "Interrupt":
            _save(
                root, task.model_copy(update={"phase": "paused", "reason": "The user interrupted."})
            )
            continue
        current = inputs(root)
        if task.phase == "ready" and task.inputs == current:
            _save(root, task.model_copy(update={"phase": "complete"}))
            continue
        stagnant = task.stagnant + 1 if task.last_inputs == current else 0
        if stagnant >= 3:
            _save(root, task.model_copy(update={"phase": "stalled", "stagnant": stagnant}))
            stalled.append(f"{root}: three continuations made no progress; report its blocker.")
            continue
        _save(
            root,
            task.model_copy(
                update={"phase": "pending", "last_inputs": current, "stagnant": stagnant}
            ),
        )
        review = (
            "Then complete the already authorized combined review "
            f"(budget {task.review_rounds}) and repairs."
            if task.review_rounds
            else "Stop after the draft is ready and ask about one review round."
        )
        reasons.append(
            f"The registered course task in {root} is unfinished. Continue the existing request. "
            f"Run tum-mcp study report {shlex.quote(str(root))} "
            f"--section readiness --batch {task.batch}; "
            f"perform its next action until the entire batch is ready. {review} "
            f"Run tum-mcp study task finish {shlex.quote(str(root))} "
            f"--owner {shlex.quote(owner)} before the final report. "
            "A failed local check is pending work, not an external blocker. "
            "If the user asks to pause, or a concrete external blocker needs their input, "
            f"use study task pause PROJECT --owner {shlex.quote(owner)} "
            "--reason REASON and report the evidence."
        )
    if reasons:
        return {"decision": "block", "reason": "\n".join([*reasons, *stalled])}
    return {"continue": False, "systemMessage": "\n".join(stalled)} if stalled else {}
