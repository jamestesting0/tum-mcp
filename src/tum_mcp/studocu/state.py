"""Explicit, project-scoped collection decisions and resumable status."""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from filelock import FileLock
from pydantic import Field, StrictBool, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.studocu.aliases import (
    cleanup_completed_promotions,
    cleanup_staging,
    consolidate_alias,
    consolidate_moving,
    consolidate_reclassified,
    promote_alias,
)
from tum_mcp.study_models import (
    Binding,
    Course,
    Coverage,
    Resource,
    ResourceState,
    Snapshot,
    StudocuProvenance,
    StudyState,
    material_path,
    validate_provenance,
)
from tum_mcp.study_store import (
    Write,
    apply,
    confined,
    digest,
    generation_for,
    load_state,
    private_name,
    private_path,
    read_bytes,
)


class Document(Frozen):
    document_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(max_length=4000)
    group: Literal["summaries", "exams", "other"]
    document_type: Literal["exam", "mock", "solution", "summary", "other"] = "other"
    raw_category: str = Field(default="", max_length=200)
    year: int | None = Field(default=None, ge=1900, le=2100)
    lecturer: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=50)
    decision: Literal["include", "exclude", "review"]
    reason: str = Field(min_length=1, max_length=1000, pattern=r".*\S.*")
    state: Literal[
        "pending",
        "acquiring",
        "action_required",
        "downloaded",
        "imported",
        "duplicate",
        "unavailable",
        "failed",
        "outcome_unknown",
    ] = "pending"
    duplicate_of: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")] | None = None
    staged_name: Annotated[str, Field(pattern=r"^[a-f0-9]{32}\.pdf$")] | None = None
    validation: Literal["pending", "validated"] | None = None
    attempt_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")] | None = None
    refresh: StrictBool = False


class Selection(Frozen):
    schema_version: Literal[1] = 1
    course_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    confirmed_course: StrictBool = False
    documents: tuple[Document, ...] = Field(max_length=10000)
    discovery: Literal["partial"] = "partial"

    @model_validator(mode="after")
    def validate_documents(self) -> "Selection":
        ids = [item.document_id for item in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Document IDs must be unique.")
        course = Course(
            key="selected-course",
            title="Selected course",
            semester="Unknown",
            bindings=(Binding(key="studocu", provider="studocu", course_id=self.course_id),),
        )
        for item in self.documents:
            resource = Resource(
                key=f"studocu-{item.document_id}",
                binding="studocu",
                kind="other",
                title=item.title,
                url=item.url,
                studocu=StudocuProvenance(
                    document_id=item.document_id, course_id=self.course_id, storage_group=item.group
                ),
            )
            validate_provenance(course, (resource,))
        return self


def queue_path(root: Path) -> Path:
    return private_path(root, "studocu/queue.json")


class SearchObservation(Frozen):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(ge=1, le=50)
    returned: int = Field(ge=0, le=50)
    checked_at: str = Field(max_length=100)


class Discovery(Frozen):
    schema_version: Literal[1] = 1
    course_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    documents: dict[str, str] = Field(default_factory=dict, max_length=10000)
    searches: tuple[SearchObservation, ...] = Field(default=(), max_length=10000)
    checked_at: str = Field(max_length=100)
    coverage: Literal["partial"] = "partial"

    @model_validator(mode="after")
    def canonical_documents(self) -> "Discovery":
        if any(
            not re.fullmatch(r"[1-9][0-9]{0,19}", document_id)
            or url != f"https://www.studocu.com/de/document/{document_id}"
            for document_id, url in self.documents.items()
        ):
            raise ValueError("Discovery document identities are invalid.")
        return self


def load_discovery(root: Path) -> Discovery | None:
    path = private_path(root, "studocu/discovery.json")
    if not path.exists():
        return None
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError
        return Discovery.model_validate_json(path.read_bytes())
    except (OSError, ValueError, ValidationError):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Discovery evidence needs review.") from None


def record_discovery(
    root: Path,
    course_id: str,
    documents: list[dict],
    *,
    searches: tuple[SearchObservation, ...] = (),
) -> None:
    """Persist sanitized search evidence, without making any selection decisions."""
    root = root.expanduser().resolve()
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        queue = load_queue(root)
        require_course_match(state, queue)
        if queue.course_id != course_id:
            raise CampusError(Code.SCOPE_DENIED, "The selected course changed during search.")
        path = private_path(root, "studocu/discovery.json")
        before = read_bytes(path)
        try:
            old = Discovery.model_validate_json(before) if before else None
        except ValidationError:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Discovery evidence needs review.") from None
        if old is not None and old.course_id != course_id:
            raise CampusError(Code.SCOPE_DENIED, "Discovery evidence belongs to another course.")
        candidates = dict(old.documents) if old else {}
        for item in documents:
            doc_id = str(item.get("id", ""))
            if item.get("course_id") != int(course_id) or not re.fullmatch(
                r"[1-9][0-9]{0,19}", doc_id
            ):
                continue
            candidates[doc_id] = f"https://www.studocu.com/de/document/{doc_id}"
        receipt = Discovery(
            course_id=course_id,
            documents=candidates,
            searches=(*(old.searches if old else ()), *searches),
            checked_at=datetime.now(UTC).isoformat(),
        )
        apply(
            root,
            (
                Write(
                    private_name(root, "studocu/discovery.json"),
                    before,
                    receipt.model_dump_json(indent=2).encode(),
                ),
            ),
        )


def load_queue(root: Path) -> Selection:
    path = queue_path(root)
    try:
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError
        return Selection.model_validate_json(path.read_bytes())
    except (ValueError, OSError, ValidationError):
        raise CampusError(
            Code.ACTION_REQUIRED, "Create a valid Studocu selection with studocu plan."
        ) from None


def require_course_match(state: StudyState, queue: Selection) -> None:
    """Reject unconfirmed legacy queues before searching or importing materials."""
    from tum_mcp.studocu.courses import matches_course

    bindings = [item for item in state.course.bindings if item.provider == "studocu"]
    if len(bindings) != 1 or bindings[0].course_id != queue.course_id:
        raise CampusError(
            Code.SCOPE_DENIED, "The selected Studocu course is not bound to this project."
        )
    if not queue.confirmed_course and not matches_course(queue.course_id, state.course.title):
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Confirm the Studocu course matches this project and update the plan.",
        )


def request_browser_download(root: Path, document_id: str) -> Document:
    """Record a browser action without starting a quota-consuming request."""
    root = root.expanduser().resolve()
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        queue = load_queue(root)
        require_course_match(state, queue)
        found = next((item for item in queue.documents if item.document_id == document_id), None)
        if found is None:
            raise CampusError(Code.SCOPE_DENIED, "Select the document in studocu plan first.")
        if found.decision != "include":
            raise CampusError(Code.SCOPE_DENIED, "This document was not selected for collection.")
        if found.state in {"imported", "duplicate"}:
            return found
        if found.state == "downloaded":
            return found
        if found.state in {"acquiring", "unavailable", "outcome_unknown"}:
            raise CampusError(
                Code.ACTION_REQUIRED, "Review the previous browser outcome before retrying."
            )
        updated = found.model_copy(update={"state": "action_required"})
        selection = queue.model_copy(
            update={
                "documents": tuple(
                    updated if item.document_id == document_id else item for item in queue.documents
                )
            }
        )
        path = queue_path(root)
        apply(
            root,
            (
                Write(
                    private_name(root, "studocu/queue.json"),
                    read_bytes(path),
                    selection.model_dump_json(indent=2).encode(),
                ),
            ),
        )
        return updated


def mark_outcome(
    root: Path,
    document_id: str,
    outcome: Literal["pending", "acquiring", "unavailable", "outcome_unknown", "failed"],
) -> Document:
    """Record a user-observed browser outcome without contacting Studocu."""
    root = root.expanduser().resolve()
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        queue = load_queue(root)
        require_course_match(state, queue)
        found = next((item for item in queue.documents if item.document_id == document_id), None)
        if found is None or found.decision != "include":
            raise CampusError(Code.SCOPE_DENIED, "Select the document in studocu plan first.")
        if found.state in {"imported", "duplicate"}:
            raise CampusError(
                Code.SCOPE_DENIED, "Use an explicit refresh for an imported document."
            )
        if outcome == "acquiring" and found.state not in {"pending", "action_required"}:
            raise CampusError(
                Code.ACTION_REQUIRED, "Review the previous browser outcome before a new attempt."
            )
        if outcome == "pending" and found.state == "acquiring":
            raise CampusError(Code.ACTION_REQUIRED, "Record the uncertain outcome before retrying.")
        attempt = (
            uuid.uuid4().hex
            if outcome == "acquiring"
            else None
            if outcome == "pending"
            else found.attempt_id
        )
        updated = found.model_copy(
            update={
                "state": outcome,
                "staged_name": None,
                "validation": None,
                "attempt_id": attempt,
            }
        )
        updated_queue = queue.model_copy(
            update={
                "documents": tuple(
                    updated if item.document_id == document_id else item for item in queue.documents
                )
            }
        )
        path = queue_path(root)
        apply(
            root,
            (
                Write(
                    private_name(root, "studocu/queue.json"),
                    read_bytes(path),
                    updated_queue.model_dump_json(indent=2).encode(),
                ),
            ),
        )
        return updated


def _reclassified(
    root: Path,
    previous: ResourceState,
    document: Document,
    resources: dict[str, ResourceState],
    *,
    preserve_alias: bool = False,
) -> tuple[ResourceState, tuple[Write, ...], tuple[Write, ...]]:
    """Prepare a conflict-safe move while preserving source identity and bytes."""
    source = previous.resource.studocu
    if source is None or previous.status != "current":
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Imported material needs review before reclassification."
        )
    relative = previous.path or resources[previous.alias_of].path
    if relative is None:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The alias original needs review.")
    old_path = confined(root, relative)
    if not old_path.is_file() or old_path.stat().st_size > 50 * 1024 * 1024:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF is missing or too large.")
    with old_path.open("rb") as stream:
        data = stream.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024 or digest(data) != previous.sha256:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF was edited; review it first.")
    provenance = StudocuProvenance.model_validate(
        source.model_dump()
        | {
            "storage_group": document.group,
            "document_type": document.document_type,
            "raw_category": document.raw_category,
            "year": document.year,
            "lecturer": document.lecturer,
            "language": document.language,
        }
    )
    resource = Resource.model_validate(previous.resource.model_dump() | {"studocu": provenance})
    if (previous.alias_of and preserve_alias) or (
        source.storage_group,
        source.document_type,
        source.year,
    ) == (
        provenance.storage_group,
        provenance.document_type,
        provenance.year,
    ):
        updated = ResourceState(
            resource=resource,
            path=previous.path,
            alias_of=previous.alias_of,
            sha256=previous.sha256,
            status="current",
        )
        return updated, (Write(relative, data, data),), ()
    destination = material_path(resource, ".pdf")
    updated = ResourceState(
        resource=resource, path=destination, sha256=previous.sha256, status="current"
    )
    if destination == previous.path:
        return updated, (), ()
    if read_bytes(confined(root, destination)) is not None:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "The destination already exists; it was preserved."
        )
    deletions = (Write(previous.path, data, None),) if previous.path else ()
    return updated, (Write(destination, None, data),), deletions


def plan(root: Path, file: Path) -> Selection:
    root = root.expanduser().resolve()
    if not file.is_file() or file.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.INVALID_RESPONSE, "Selection file is missing or exceeds 8 MiB.")
    try:
        proposed = Selection.model_validate_json(file.read_bytes())
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid Studocu selection; check its schema."
        ) from None
    if any(
        item.state != "pending"
        or item.duplicate_of is not None
        or item.staged_name is not None
        or item.validation is not None
        or item.attempt_id is not None
        for item in proposed.documents
    ):
        raise CampusError(Code.INVALID_RESPONSE, "New selections must contain pending documents.")
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        bindings = [b for b in state.course.bindings if b.provider == "studocu"]
        if len(bindings) > 1 or (bindings and bindings[0].course_id != proposed.course_id):
            raise CampusError(
                Code.SCOPE_DENIED, "Studocu course differs from this project's binding."
            )
        from tum_mcp.studocu.courses import known_course, matches_course

        path = queue_path(root)
        before = read_bytes(path)
        old = load_queue(root) if before is not None else None
        if old is not None and old.course_id != proposed.course_id:
            raise CampusError(Code.SCOPE_DENIED, "Existing selection belongs to another course.")
        confirmed = proposed.confirmed_course or bool(old and old.confirmed_course)
        if (old is None or not confirmed) and not known_course(proposed.course_id):
            raise CampusError(
                Code.ACTION_REQUIRED, "Search and verify the Studocu course at TUM before planning."
            )
        if not confirmed and not matches_course(proposed.course_id, state.course.title):
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Confirm the Studocu course matches this project before binding it.",
            )
        if confirmed:
            proposed = proposed.model_copy(update={"confirmed_course": True})
        if not bindings:
            if state.course.synthetic or any(
                item.key == "studocu" for item in state.course.bindings
            ):
                raise CampusError(
                    Code.SCOPE_DENIED, "This project cannot add a Studocu course binding."
                )
        if proposed.documents:
            evidence = load_discovery(root)
            if evidence is None:
                raise CampusError(
                    Code.ACTION_REQUIRED, "Search this course before selecting its documents."
                )
            if evidence.course_id != proposed.course_id or any(
                evidence.documents.get(item.document_id) != item.url for item in proposed.documents
            ):
                raise CampusError(
                    Code.SCOPE_DENIED, "Selection contains unverified course documents."
                )
        resources = {entry.resource.key: entry for entry in state.resources}
        creates: list[Write] = []
        removes: list[Write] = []
        promotion_cleanup: list[Write] = []
        recovered_promotions = cleanup_completed_promotions(root, resources)
        changed_classifications: set[str] = set()
        consolidated = False
        if before is None and any(item.refresh for item in proposed.documents):
            raise CampusError(Code.SCOPE_DENIED, "Only an imported document can be refreshed.")
        if old is not None:
            old_by_id = {item.document_id: item for item in old.documents}
            desired = old_by_id | {item.document_id: item for item in proposed.documents}
            preserve_family: set[str] = set()
            families: dict[str, list[ResourceState]] = {}
            for resource in resources.values():
                if resource.alias_of:
                    families.setdefault(resource.alias_of, []).append(resource)
            for target_key, aliases in families.items():
                canonical = resources[target_key]
                original = canonical.resource.studocu
                target_id = original.document_id
                if target_id not in old_by_id or canonical.status != "current":
                    continue
                selected_target = desired[target_id]
                classification = (
                    selected_target.group,
                    selected_target.document_type,
                    selected_target.year,
                )
                if classification[2] is None or classification == (
                    original.storage_group,
                    original.document_type,
                    original.year,
                ):
                    continue
                for alias in aliases:
                    doc_id = alias.resource.studocu.document_id
                    if doc_id not in old_by_id or alias.status != "current":
                        continue
                    item = desired[doc_id]
                    if (item.group, item.document_type, item.year) == classification:
                        preserve_family.add(alias.resource.key)
            merged = []
            order = {item.document_id: index for index, item in enumerate(proposed.documents)}
            # Detach aliases before moving their canonical original in the same plan.
            selected = sorted(
                proposed.documents,
                key=lambda item: (
                    0
                    if resources.get(f"studocu-{item.document_id}")
                    and resources[f"studocu-{item.document_id}"].alias_of
                    else 1,
                    order[item.document_id],
                ),
            )
            for item in selected:
                previous = old_by_id.pop(item.document_id, None)
                if previous is not None:
                    classification = {
                        "group": item.group,
                        "document_type": item.document_type,
                        "raw_category": item.raw_category,
                        "year": item.year,
                        "lecturer": item.lecturer,
                        "language": item.language,
                    }
                    reclassified = any(
                        getattr(previous, field) != value for field, value in classification.items()
                    )
                    comparable = previous.model_copy(
                        update={
                            "state": "pending",
                            "duplicate_of": None,
                            "staged_name": None,
                            "validation": None,
                            "attempt_id": None,
                            "decision": item.decision,
                            "reason": item.reason,
                            "refresh": item.refresh,
                            **classification,
                        }
                    )
                    if comparable != item:
                        raise CampusError(
                            Code.WORKSPACE_CONFLICT,
                            "Existing document identity changed; review it.",
                        )
                    key = f"studocu-{item.document_id}"
                    if reclassified and (
                        previous.state in {"imported", "duplicate"} or key in resources
                    ):
                        if key not in resources:
                            raise CampusError(
                                Code.WORKSPACE_CONFLICT,
                                "Imported material is missing from the inventory.",
                            )
                        if any(
                            getattr(previous, name) != classification[name]
                            for name in ("group", "document_type", "year")
                        ):
                            promotion = promote_alias(
                                root, resources, key, retain=frozenset(preserve_family)
                            )
                            creates.extend(promotion.writes)
                            promotion_cleanup.extend(promotion.cleanup)
                        updated_resource, additions, deletions = _reclassified(
                            root,
                            resources[key],
                            item,
                            resources,
                            preserve_alias=key in preserve_family,
                        )
                        resources[key] = updated_resource
                        creates.extend(additions)
                        removes.extend(deletions)
                        changed_classifications.add(item.document_id)
                    if item.refresh and (
                        previous.state not in {"imported", "duplicate"}
                        or item.decision != "include"
                    ):
                        raise CampusError(
                            Code.SCOPE_DENIED,
                            "Only an imported selected document can be refreshed.",
                        )
                    status = previous.state if not item.refresh else "pending"
                    merged.append(
                        previous.model_copy(
                            update={
                                "decision": item.decision,
                                "reason": item.reason,
                                "state": status,
                                "refresh": False,
                                "duplicate_of": None if item.refresh else previous.duplicate_of,
                                "staged_name": None if item.refresh else previous.staged_name,
                                "validation": None if item.refresh else previous.validation,
                                "attempt_id": None if item.refresh else previous.attempt_id,
                                **classification,
                            }
                        )
                    )
                else:
                    if item.refresh:
                        raise CampusError(
                            Code.SCOPE_DENIED, "Only an imported document can be refreshed."
                        )
                    merged.append(item)
            merged.sort(key=lambda item: order[item.document_id])
            proposed = proposed.model_copy(
                update={"documents": tuple(merged) + tuple(old_by_id.values())}
            )
            if changed_classifications:
                changed_keys = {f"studocu-{doc_id}" for doc_id in changed_classifications}
                consolidate_moving(root, resources, creates, removes, changed_keys)
                moving = {
                    write.relative for write in (*creates, *removes) if write.before != write.after
                }
                removal = consolidate_reclassified(root, resources, changed_keys, moving)
                consolidated |= bool(removal)
                removes.extend(removal)
            if not changed_classifications:
                for document in proposed.documents:
                    if document.state == "duplicate" and document.duplicate_of:
                        removal = consolidate_alias(
                            root,
                            resources,
                            f"studocu-{document.document_id}",
                            f"studocu-{document.duplicate_of}",
                        )
                        consolidated |= bool(removal)
                        removes.extend(removal)
                moving = {write.relative for write in removes if write.before != write.after}
                removal = consolidate_reclassified(root, resources, set(resources), moving)
                consolidated |= bool(removal)
                removes.extend(removal)
                for document in proposed.documents:
                    source = resources.get(f"studocu-{document.document_id}")
                    if (
                        document.state in {"imported", "duplicate"}
                        and document.staged_name
                        and source
                        and source.sha256
                        and source.resource.studocu
                    ):
                        retained = (
                            resources[source.alias_of].path if source.alias_of else source.path
                        )
                        if retained:
                            removes.extend(
                                cleanup_staging(root, document.staged_name, source, retained)
                            )
            if changed_classifications or consolidated:
                proposed = proposed.model_copy(
                    update={
                        "documents": tuple(
                            document.model_copy(
                                update={
                                    "state": "duplicate"
                                    if resources[f"studocu-{document.document_id}"].alias_of
                                    else "imported",
                                    "duplicate_of": resources[
                                        f"studocu-{document.document_id}"
                                    ].alias_of.removeprefix("studocu-")
                                    if resources[f"studocu-{document.document_id}"].alias_of
                                    else None,
                                }
                            )
                            if document.state in {"imported", "duplicate"}
                            and f"studocu-{document.document_id}" in resources
                            else document
                            for document in proposed.documents
                        )
                    }
                )
        writes = list(creates)
        if changed_classifications or consolidated:
            ordered = tuple(sorted(resources.values(), key=lambda entry: entry.resource.key))
            updated_state = type(state).model_validate(
                state.model_dump()
                | {
                    "resources": ordered,
                    "generation": generation_for(state.course, ordered, state.coverage),
                }
            )
            state_path = private_path(root, "state.json")
            writes.append(
                Write(
                    private_name(root, "state.json"),
                    read_bytes(state_path),
                    updated_state.model_dump_json(indent=2).encode(),
                )
            )
        writes.append(
            Write(
                private_name(root, "studocu/queue.json"),
                before,
                proposed.model_dump_json(indent=2).encode(),
            )
        )
        writes.extend(removes)
        writes.extend(promotion_cleanup)
        writes.extend(recovered_promotions)
        if not bindings:
            from tum_mcp.study_sync import _reconcile

            binding = Binding(key="studocu", provider="studocu", course_id=proposed.course_id)
            course = Course.model_validate(
                state.course.model_dump() | {"bindings": (*state.course.bindings, binding)}
            )
            snapshot = Snapshot(
                schema_version=state.schema_version,
                course=course,
                coverage=(
                    Coverage(
                        binding=binding.key,
                        status="partial",
                        checked_at=datetime.now(UTC).isoformat(),
                    ),
                ),
                resources=(),
                retained_bindings=tuple(item.key for item in state.course.bindings),
            )
            _reconcile(
                root, path, snapshot, state, extra_writes=tuple(writes), require_no_conflicts=True
            )
        else:
            apply(root, tuple(writes))
    return proposed
