"""A thread-owned course task and a local, evidence-based completion guard."""

import os
import shlex
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal

from pydantic import Field, model_validator

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
# A requested video or audio track, by the stem its plan or script names.
MediaRef = Annotated[str, Field(pattern=r"^(video|audio)/[a-z0-9][a-z0-9_.-]{0,99}$")]


class Task(Frozen):
    """A requested batch of course content, or published media with checked listening."""

    owner: str = Field(min_length=1, max_length=200)
    batch: Key | None = None
    media: tuple[MediaRef, ...] = Field(default=(), max_length=40)
    review_rounds: int = Field(default=0, ge=0, le=20)
    phase: Literal["pending", "ready", "complete", "paused", "stalled"] = "pending"
    inputs: Digest | None = None
    review_before: Digest | None = None
    review_requested_at: datetime | None = None
    review_closed_before: datetime | None = None
    # The review's round budget when this task began; an extension adds this task's rounds.
    review_budget_before: int = Field(default=0, ge=0, le=40)
    last_inputs: Digest | None = None
    stagnant: int = Field(default=0, ge=0, le=3)
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def one_scope(self) -> "Task":
        if (self.batch is None) == (not self.media):
            raise ValueError("A task names either a batch or its media.")
        if self.media and self.review_rounds:
            raise ValueError("Media tasks have no review rounds.")
        return self


def read_task(root: Path) -> Task | None:
    body = read_bytes(confined(root, NAME))
    return Task.model_validate_json(body) if body is not None else None


def checker_task_batch(root: Path) -> str | None:
    """The active batch in the calling author’s hook context, if any."""
    task = read_task(root)
    identity = os.environ.get("CODEX_THREAD_ID")
    owner = os.environ.get("TUM_MCP_TASK_OWNER") or (f"codex:{identity}" if identity else None)
    if task and task.phase in {"pending", "ready"} and task.owner == owner:
        return task.batch
    return None


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


def begin(
    root: Path,
    batch: str | None,
    review_rounds: int = 0,
    *,
    owner: str | None = None,
    media: tuple[str, ...] = (),
) -> Task:
    task = Task(owner=_owner(owner), batch=batch, media=media, review_rounds=review_rounds)
    state = load_state(root)
    if task.batch is not None:
        body = read_bytes(private_path(root, f"batches/{task.batch}.json"))
        if body is None:
            raise CampusError(Code.ACTION_REQUIRED, "Record the batch before starting its task.")
        if Batch.model_validate_json(body).course_key != state.course.key:
            raise CampusError(Code.SCOPE_DENIED, "The task belongs to another course.")
    scope = (task.batch, task.media, task.review_rounds)
    existing = read_task(root)
    if (
        existing
        and existing.owner == task.owner
        and existing.phase in {"paused", "stalled"}
        and (existing.batch, existing.media, existing.review_rounds) == scope
    ):
        if not existing.review_rounds or existing.review_requested_at is not None:
            return _save(
                root, existing.model_copy(update={"phase": "pending", "stagnant": 0, "reason": ""})
            )
    if existing and existing.phase in {"pending", "ready"}:
        if existing.owner != task.owner:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Another thread owns this active course task."
            )
        if (existing.batch, existing.media, existing.review_rounds) != scope:
            raise CampusError(
                Code.ACTION_REQUIRED, "Pause the existing task before changing its scope."
            )
        if not existing.review_rounds or existing.review_requested_at is not None:
            return existing
    review = read_state(root)
    closed = [entry.closed for entry in review.rounds if entry.closed is not None] if review else []
    return _save(
        root,
        task.model_copy(
            update={
                "review_before": digest(review.model_dump_json().encode()) if review else None,
                "review_requested_at": datetime.now(UTC),
                "review_closed_before": max(closed, default=None),
                "review_budget_before": review.budget if review else 0,
            }
        ),
    )


def _owned(root: Path, owner: str | None = None) -> Task:
    task = read_task(root)
    if task is None or task.owner != _owner(owner):
        raise CampusError(Code.SCOPE_DENIED, "No course task is owned by this thread.")
    return task


def media_problems(root: Path, media: tuple[str, ...]) -> list[str]:
    return _media_completion(root, media)[0]


def _media_completion(root: Path, media: tuple[str, ...]) -> tuple[list[str], str]:
    """Check the requested artifacts and bind readiness to the evidence that passed."""
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.content.store import present
    from tum_mcp.course.media.inventory import discover
    from tum_mcp.course.media.listening import verify_listening

    content = read_content(root) if present(root, "study") else None
    inventory = discover(root, load_state(root), content)
    problems: list[str] = []
    revisions: list[tuple[str, str, str]] = []
    for ref in media:
        item = inventory.requested(ref)
        if isinstance(item, str):
            problems.append(f"{ref}: {item}")
            continue
        try:
            evidence = verify_listening(root, item)
        except CampusError as error:
            problems.append(f"{ref}: {error.message}")
        except OSError as error:
            problems.append(f"{ref}: {error}")
        else:
            revisions.append((ref, item.revision, evidence))
    return problems, digest(repr(revisions).encode())


# Media progress: what an author writes and what publish records, not renders or audio.
MEDIA_INPUTS = (
    "videos/plan.json",
    "videos/manifest.json",
    "videos/voice.json",
    "videos/style.json",
    "videos/storyboards/*.json",
    "videos/scenes/*/*.py",
    "videos/.build/*/timing.json",
    "audio/plan.json",
    "audio/manifest.json",
    "audio/voice.json",
    "audio/categories/*.json",
)


def inputs(root: Path, media: bool = False) -> str:
    """Hash authoring and checked evidence, excluding raw media, caches and this task."""
    paths = set((root / "app").rglob("*")) if (root / "app").exists() else set()
    if media:
        paths.update(path for pattern in MEDIA_INPUTS for path in root.glob(pattern))
    for pattern in (
        "state.json",
        "schedule.json",
        "links.json",
        "progress-continuity.json",
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
    if task.media:
        problems, media_inputs = _media_completion(root, task.media)
        if problems:
            raise CampusError(
                Code.ACTION_REQUIRED,
                " ".join([*problems, "Continue its workflow through publish and listen."]),
            )
        _save(root, task.model_copy(update={"phase": "ready", "inputs": media_inputs}))
        return {
            "ready": True,
            "next_action": "Report each published item with its path, duration and checks.",
        }
    readiness = assess_batch(root, task.batch)
    if not readiness.ready:
        raise CampusError(Code.ACTION_REQUIRED, readiness.report()["next_action"])
    if task.review_rounds:
        from tum_mcp.course.review.repair_scope import contract

        review = read_state(root)
        if task.review_requested_at is None:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Run study task begin again to bind this older task, then finish a fresh review.",
            )
        fresh = [
            entry
            for entry in (review.rounds if review else ())
            if entry.started >= task.review_requested_at
            and entry.closed is not None
            and (task.review_closed_before is None or entry.closed > task.review_closed_before)
            and entry.answered is not None
            and not entry.pending_packets
            and bool(entry.packets)
        ]
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
            or review.budget
            not in {task.review_rounds, task.review_budget_before + task.review_rounds}
            or review.status == "running"
            or not review.rounds
            or review.rounds[-1].closed is None
            or review.rounds[-1].pending_packets
            or not fresh
            or (
                len(fresh) < task.review_rounds
                and not (task.review_budget_before == 0 and review.status == "passed")
            )
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
        problems, media_inputs = _media_completion(root, task.media) if task.media else ([], "")
        current = (
            media_inputs if task.media and task.phase == "ready" else inputs(root, bool(task.media))
        )
        if task.phase == "ready" and not problems and task.inputs == current:
            _save(root, task.model_copy(update={"phase": "complete"}))
            continue
        if task.media and task.phase == "ready":
            if not problems:
                problems = [
                    f"Media or listening evidence changed since finish: {', '.join(task.media)}."
                ]
            current = inputs(root, True)
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
        if task.media:
            reasons.append(
                f"The registered media task in {root} is unfinished: "
                + " ".join(problems)
                + " Continue the existing request through each stage: storyboard or script, "
                "narration, scenes, render, publish and listen. "
                f"Run tum-mcp study task finish {shlex.quote(str(root))} "
                f"--owner {shlex.quote(owner)} before the final report. "
                "A failed local check is pending work, not an external blocker. "
                "If the user asks to pause, or a concrete external blocker needs their input, "
                f"use study task pause PROJECT --owner {shlex.quote(owner)} "
                "--reason REASON and report the evidence."
            )
            continue
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
            f"Use workspace_actions to choose the next feasible prerequisite in every requested "
            f"workspace. Finish feasible siblings while a concrete external blocker is open. "
            f"The combined gate still requires all requested work. {review} "
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
