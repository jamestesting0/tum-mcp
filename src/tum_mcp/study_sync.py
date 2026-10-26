"""Reconcile source snapshots without overwriting notes or inferring remote deletion."""

import json
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock
from pydantic import ValidationError

from tum_mcp.course_context import scaffold
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_models import FOLDERS, Resource, ResourceState, Snapshot, StudyState
from tum_mcp.study_store import (
    Write,
    agent_pointer,
    apply,
    confined,
    digest,
    load_state,
    private_folder,
    private_name,
    private_path,
    read_bytes,
    replace_agents,
)

MAX_SOURCE = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SyncReport:
    imported: int
    retained: int
    conflicts: tuple[str, ...]
    withdrawn: int
    generation: str


def read_snapshot(path: Path) -> Snapshot:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.INVALID_RESPONSE, "Study snapshot exceeds 8 MiB.")
    try:
        return Snapshot.model_validate_json(path.read_bytes())
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid course snapshot; check study schema."
        ) from None


def payload(resource: Resource, snapshot: Path) -> tuple[bytes | None, str]:
    if resource.text is not None:
        return resource.text.encode(), ".md"
    if resource.source_file is not None:
        path = confined(snapshot.parent.resolve(), resource.source_file)
        if not path.is_file() or path.stat().st_size > MAX_SOURCE:
            raise CampusError(Code.INVALID_RESPONSE, "Import file is missing or exceeds 50 MiB.")
        suffix = path.suffix.lower()
        if suffix not in {".pdf", ".md", ".txt", ".csv", ".png", ".jpg", ".pptx", ".docx"}:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Convert this study import to PDF or text."
            )
        return path.read_bytes(), suffix
    return None, ".md"


def sync(root: Path, snapshot_path: Path, *, course_input: str | None = None) -> SyncReport:
    root = root.expanduser().resolve()
    snapshot_path = snapshot_path.resolve()
    snapshot = read_snapshot(snapshot_path)
    if (
        course_input is not None
        and course_input.strip().casefold() != snapshot.course.title.casefold()
    ):
        raise CampusError(Code.SCOPE_DENIED, "Explicit course input does not match the snapshot.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_path(root, "state.json").parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = private_path(root, "update.lock")
    with FileLock(str(lock)):
        record = private_path(root, "state.json")
        previous = load_state(root) if record.exists() else None
        if previous is None and course_input is None:
            raise CampusError(Code.ACTION_REQUIRED, "Use study init with an explicit course first.")
        if previous is not None and (
            previous.course.key != snapshot.course.key
            or previous.course.semester != snapshot.course.semester
            or not {item.key: item for item in previous.course.bindings}.items()
            <= {item.key: item for item in snapshot.course.bindings}.items()
        ):
            raise CampusError(Code.SCOPE_DENIED, "This project is bound to a different course.")
        return _reconcile(root, snapshot_path, snapshot, previous)


def _reconcile(
    root: Path, path: Path, snapshot: Snapshot, previous: StudyState | None
) -> SyncReport:
    old = {item.resource.key: item for item in previous.resources} if previous else {}
    current: list[ResourceState] = []
    writes: list[Write] = []
    imported = 0
    conflicts: list[str] = []
    for resource in snapshot.resources:
        prior = old.pop(resource.key, None)
        data, suffix = payload(resource, path)
        if prior is not None and prior.path is not None:
            previous_data = read_bytes(confined(root, prior.path))
            edited = previous_data is None or digest(previous_data) != prior.sha256
            if edited and (previous_data is None or previous_data != data):
                conflicts.append(resource.key)
                current.append(prior.model_copy(update={"status": "local_edit"}))
                continue
        relative = f"materials/{FOLDERS[resource.kind]}/material-{resource.key}{suffix}"
        if (
            data is None
            and prior is not None
            and prior.path
            and prior.resource.kind == resource.kind
        ):
            relative = prior.path
        before = read_bytes(confined(root, relative))
        clean = resource.model_copy(update={"text": None, "source_file": None})
        if (
            before is not None
            and (prior is None or prior.sha256 != digest(before))
            and before != data
        ):
            conflicts.append(resource.key)
            current.append(
                ResourceState(
                    resource=clean,
                    path=relative,
                    sha256=prior.sha256 if prior else None,
                    status="local_edit",
                )
            )
            continue
        if data is not None:
            writes.append(Write(relative, before, data))
            imported += data != before
            current.append(
                ResourceState(resource=clean, path=relative, sha256=digest(data), status="current")
            )
        else:
            unchanged = bool(
                prior
                and prior.status == "current"
                and before is not None
                and resource.binding == prior.resource.binding
                and resource.url == prior.resource.url
                and resource.locator == prior.resource.locator
                and resource.revision is not None
                and resource.revision == prior.resource.revision
            )
            current.append(
                ResourceState(
                    resource=clean,
                    path=relative if before is not None else None,
                    sha256=prior.sha256 if prior else None,
                    status="current" if unchanged else "needs_fetch",
                )
            )
    complete = {item.binding for item in snapshot.coverage if item.status == "complete"}
    for item in old.values():
        status = "withdrawn" if item.resource.binding in complete else item.status
        current.append(item.model_copy(update={"status": status}))
    ordered = tuple(sorted(current, key=lambda item: item.resource.key))
    block = agent_pointer(private_folder(root))
    agents = confined(root, "AGENTS.md")
    before_agents = read_bytes(agents)
    try:
        existing_agents = (before_agents or b"").decode("utf-8")
    except UnicodeDecodeError:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Existing AGENTS.md is not UTF-8; it was preserved."
        ) from None
    updated_agents = replace_agents(existing_agents, block, previous).encode()
    generation = digest(
        json.dumps(
            {
                "course": snapshot.course.model_dump(mode="json"),
                "resources": [r.model_dump(mode="json") for r in ordered],
                "coverage": [c.model_dump(mode="json") for c in snapshot.coverage],
            },
            sort_keys=True,
        ).encode()
    )
    state = StudyState(
        schema_version=max(snapshot.schema_version, previous.schema_version if previous else 1),
        course=snapshot.course,
        coverage=snapshot.coverage,
        resources=ordered,
        generation=generation,
        agents_block_sha256=digest(block.encode()),
    )
    record = private_path(root, "state.json")
    writes.extend(
        (
            Write("AGENTS.md", before_agents, updated_agents),
            Write(
                private_name(root, "state.json"),
                read_bytes(record),
                state.model_dump_json(indent=2).encode(),
            ),
        )
    )
    for folder in FOLDERS.values():
        confined(root, f"materials/{folder}").mkdir(mode=0o700, parents=True, exist_ok=True)
    context = private_path(root, "course.md")
    if not context.exists():
        writes.append(
            Write(private_name(root, "course.md"), None, scaffold(snapshot.course).encode())
        )
    apply(root, tuple(writes))
    return SyncReport(
        imported=imported,
        retained=len(ordered) - imported,
        conflicts=tuple(conflicts),
        withdrawn=sum(item.status == "withdrawn" for item in ordered),
        generation=generation,
    )
