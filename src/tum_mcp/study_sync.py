"""Reconcile source snapshots without overwriting notes or inferring remote deletion."""

from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock
from pydantic import ValidationError

from tum_mcp.course_context import scaffold
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_models import (
    FOLDERS,
    Resource,
    ResourceState,
    Snapshot,
    StudyState,
    material_path,
    resolved_material_path,
)
from tum_mcp.study_store import (
    Write,
    agent_pointer,
    apply,
    confined,
    digest,
    generation_for,
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
        if snapshot.retained_bindings and previous is None:
            raise CampusError(Code.SCOPE_DENIED, "Cannot retain bindings in a new project.")
        if previous is not None and not set(snapshot.retained_bindings) <= {
            item.key for item in previous.course.bindings
        }:
            raise CampusError(Code.SCOPE_DENIED, "A retained binding must already exist.")
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
    root: Path,
    path: Path,
    snapshot: Snapshot,
    previous: StudyState | None,
    *,
    before_writes: tuple[Write, ...] = (),
    extra_writes: tuple[Write, ...] = (),
    require_no_conflicts: bool = False,
    alias_of: str | None = None,
) -> SyncReport:
    old = {item.resource.key: item for item in previous.resources} if previous else {}
    current: list[ResourceState] = []
    writes: list[Write] = []
    imported = 0
    conflicts: list[str] = []
    for resource in snapshot.resources:
        prior = old.pop(resource.key, None)
        if (
            prior is not None
            and prior.resource.binding != resource.binding
            and (
                prior.resource.binding in snapshot.retained_bindings
                or prior.resource.studocu is not None
                or resource.studocu is not None
            )
        ):
            raise CampusError(Code.SCOPE_DENIED, "A resource key belongs to another binding.")
        data, suffix = payload(resource, path)
        if resource.studocu is not None and data is not None:
            from tum_mcp.moodle.extract_worker import validate_pdf

            source = resource.studocu
            if (
                prior is not None
                and prior.resource.studocu is not None
                and prior.resource.studocu.storage_group != source.storage_group
            ):
                raise CampusError(
                    Code.ACTION_REQUIRED, "Reclassify Studocu material through studocu plan."
                )
            if prior and prior.sha256 != digest(data) and not before_writes:
                raise CampusError(
                    Code.ACTION_REQUIRED, "Refresh Studocu originals through the Studocu workflow."
                )
            if suffix != ".pdf" or source.file_sha256 != digest(data) or source.acquired_at is None:
                raise CampusError(
                    Code.INVALID_RESPONSE, "A validated original PDF receipt is required."
                )
            if validate_pdf(data) != source.page_count:
                raise CampusError(
                    Code.INVALID_RESPONSE, "PDF page count does not match the receipt."
                )
        prior_path = resolved_material_path(previous, prior) if previous and prior else None
        if prior is not None and prior_path is not None:
            previous_data = read_bytes(confined(root, prior_path))
            edited = previous_data is None or digest(previous_data) != prior.sha256
            if edited and (previous_data is None or previous_data != data):
                conflicts.append(resource.key)
                current.append(prior.model_copy(update={"status": "local_edit"}))
                continue
        relative = material_path(resource, suffix)
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
            if alias_of is not None:
                if prior and prior.path and before is not None:
                    writes.append(Write(relative, before, None))
                elif before is not None:
                    raise CampusError(Code.WORKSPACE_CONFLICT, "The alias destination is occupied.")
            else:
                writes.append(Write(relative, before, data))
            imported += data != before
            current.append(
                ResourceState(
                    resource=clean,
                    path=None if alias_of else relative,
                    alias_of=alias_of,
                    sha256=digest(data),
                    status="current",
                )
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
    retained = set(snapshot.retained_bindings)
    coverage = tuple(snapshot.coverage) + (
        tuple(item for item in previous.coverage if item.binding in retained) if previous else ()
    )
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
    generation = generation_for(snapshot.course, ordered, coverage)
    state = StudyState(
        schema_version=max(snapshot.schema_version, previous.schema_version if previous else 1),
        course=snapshot.course,
        coverage=coverage,
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
    for item in ordered:
        if item.path is not None and item.resource.studocu is not None:
            confined(root, str(Path(item.path).parent)).mkdir(
                mode=0o700, parents=True, exist_ok=True
            )
    context = private_path(root, "course.md")
    if not context.exists():
        writes.append(
            Write(private_name(root, "course.md"), None, scaffold(snapshot.course).encode())
        )
    if conflicts and require_no_conflicts:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Local source edits need review before import.")
    apply(root, (*before_writes, *writes, *extra_writes))
    return SyncReport(
        imported=imported,
        retained=len(ordered) - imported,
        conflicts=tuple(conflicts),
        withdrawn=sum(item.status == "withdrawn" for item in ordered),
        generation=generation,
    )
