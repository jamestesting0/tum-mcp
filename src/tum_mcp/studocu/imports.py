"""Stage a user-selected original PDF and atomically reconcile its receipt."""

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.extract_worker import ExtractionLimit, validate_pdf
from tum_mcp.studocu.aliases import cleanup_completed_promotions, promote_alias
from tum_mcp.studocu.state import Document, load_queue, queue_path, require_course_match
from tum_mcp.study_models import (
    Binding,
    Course,
    Coverage,
    Resource,
    Snapshot,
    StudocuProvenance,
    resolved_material_path,
)
from tum_mcp.study_store import (
    Write,
    apply,
    confined,
    digest,
    load_state,
    private_name,
    private_path,
    read_bytes,
)
from tum_mcp.study_sync import _reconcile

STAGED = re.compile(r"^[a-f0-9]{32}\.pdf$")
MAX_PDF = 50 * 1024 * 1024


def _bounded(path: Path, limit: int) -> bytes:
    if not path.is_file():
        raise CampusError(Code.INVALID_RESPONSE, "The selected file is missing.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise CampusError(Code.INVALID_RESPONSE, "The selected file exceeds its size limit.")
    return data


def _selected(root: Path, document_id: str) -> Document:
    queue = load_queue(root)
    require_course_match(load_state(root), queue)
    matches = [item for item in queue.documents if item.document_id == document_id]
    if len(matches) != 1:
        raise CampusError(Code.SCOPE_DENIED, "Choose this document in studocu plan first.")
    if matches[0].decision != "include":
        raise CampusError(Code.SCOPE_DENIED, "This document was not selected for collection.")
    return matches[0]


def staged_validation(root: Path, name: str) -> str:
    if not STAGED.fullmatch(name):
        raise CampusError(Code.SCOPE_DENIED, "Use a staged PDF name from studocu stage.")
    receipt = private_path(root.expanduser().resolve(), f"studocu/incoming/{name}.json")
    try:
        info = json.loads(_bounded(receipt, 4096))
        value = info.get("validation", "validated")
        if value not in {"pending", "validated"}:
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise CampusError(Code.INVALID_RESPONSE, "Staged PDF receipt needs review.") from None


def stage(root: Path, document_id: str, file: Path) -> str:
    root = root.expanduser().resolve()
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_PDF:
        raise CampusError(Code.INVALID_RESPONSE, "Select an original PDF file under 50 MiB.")
    data = _bounded(file, MAX_PDF)
    try:
        pages = validate_pdf(data)
    except ExtractionLimit:
        pages = None
    name = f"{uuid.uuid4().hex}.pdf"
    receipt = {
        "document_id": document_id,
        "sha256": digest(data),
        "page_count": pages,
        "validation": "validated" if pages is not None else "pending",
        "identity_basis": "user_selected_file",
        "acquired_at": datetime.now(UTC).isoformat(),
    }
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        selected = _selected(root, document_id)
        if selected.state == "downloaded":
            if selected.staged_name is None:
                raise CampusError(Code.WORKSPACE_CONFLICT, "The staged download needs review.")
            previous_path = private_path(root, f"studocu/incoming/{selected.staged_name}")
            previous_receipt = private_path(root, f"studocu/incoming/{selected.staged_name}.json")
            try:
                previous_data = _bounded(previous_path, MAX_PDF)
                previous_receipt_data = _bounded(previous_receipt, 4096)
                previous_info = json.loads(previous_receipt_data)
                if (
                    previous_data != data
                    or previous_info.get("document_id") != document_id
                    or previous_info.get("sha256") != digest(data)
                    or previous_info.get("validation", "validated") not in {"validated", "pending"}
                    or (
                        previous_info.get("validation", "validated") == "validated"
                        and pages is not None
                        and previous_info.get("page_count") != pages
                    )
                ):
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "A different staged file exists; review it before replacing the selection.",
                ) from None
            if previous_info.get("validation") == "pending" and pages is not None:
                previous_info.update({"validation": "validated", "page_count": pages})
                queue = load_queue(root)
                updated = queue.model_copy(
                    update={
                        "documents": tuple(
                            item.model_copy(update={"validation": "validated"})
                            if item.document_id == document_id
                            else item
                            for item in queue.documents
                        )
                    }
                )
                apply(
                    root,
                    (
                        Write(
                            private_name(root, f"studocu/incoming/{selected.staged_name}.json"),
                            previous_receipt_data,
                            json.dumps(previous_info).encode(),
                        ),
                        Write(
                            private_name(root, "studocu/queue.json"),
                            read_bytes(queue_path(root)),
                            updated.model_dump_json(indent=2).encode(),
                        ),
                    ),
                )
            return selected.staged_name
        if selected.state in {"imported", "duplicate"}:
            existing = next(
                (item for item in state.resources if item.resource.key == f"studocu-{document_id}"),
                None,
            )
            if existing is None or existing.sha256 != digest(data):
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Explicitly select refresh before staging a different imported PDF.",
                )
            if existing.status != "current" or existing.resource.studocu is None:
                raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF needs review.")
            relative = resolved_material_path(state, existing)
            if relative is None or _bounded(confined(root, relative), MAX_PDF) != data:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "The imported PDF was edited or removed."
                )
            if selected.staged_name is not None:
                old_receipt = private_path(root, f"studocu/incoming/{selected.staged_name}.json")
                old_file = private_path(root, f"studocu/incoming/{selected.staged_name}")
                try:
                    info = json.loads(_bounded(old_receipt, 4096))
                    reusable = (
                        info["document_id"] == document_id
                        and info["sha256"] == existing.sha256
                        and info["identity_basis"] == "user_selected_file"
                        and info.get("validation", "validated") == "validated"
                        and info["page_count"] == existing.resource.studocu.page_count
                        and (not old_file.exists() or _bounded(old_file, MAX_PDF) == data)
                    )
                except (CampusError, ValueError, KeyError, TypeError, AttributeError, OSError):
                    reusable = False
                if reusable:
                    return selected.staged_name
            receipt.update(
                {"validation": "validated", "page_count": existing.resource.studocu.page_count}
            )
            queue = load_queue(root)
            updated = queue.model_copy(
                update={
                    "documents": tuple(
                        item.model_copy(update={"staged_name": name, "validation": "validated"})
                        if item.document_id == document_id
                        else item
                        for item in queue.documents
                    )
                }
            )
            apply(
                root,
                (
                    Write(
                        private_name(root, f"studocu/incoming/{name}.json"),
                        None,
                        json.dumps(receipt).encode(),
                    ),
                    Write(
                        private_name(root, "studocu/queue.json"),
                        read_bytes(queue_path(root)),
                        updated.model_dump_json(indent=2).encode(),
                    ),
                ),
            )
            return name
        queue = load_queue(root)
        updated_queue = queue.model_copy(
            update={
                "documents": tuple(
                    item.model_copy(
                        update={
                            "state": "downloaded",
                            "staged_name": name,
                            "validation": receipt["validation"],
                        }
                    )
                    if item.document_id == document_id
                    and selected.state not in {"imported", "duplicate"}
                    else item
                    for item in queue.documents
                )
            }
        )
        queue_before = read_bytes(queue_path(root))
        apply(
            root,
            (
                Write(private_name(root, f"studocu/incoming/{name}"), None, data),
                Write(
                    private_name(root, f"studocu/incoming/{name}.json"),
                    None,
                    json.dumps(receipt).encode(),
                ),
                Write(
                    private_name(root, "studocu/queue.json"),
                    queue_before,
                    updated_queue.model_dump_json(indent=2).encode(),
                ),
            ),
        )
    return name


def import_staged(root: Path, document_id: str, staged_name: str) -> dict:
    root = root.expanduser().resolve()
    if not STAGED.fullmatch(staged_name):
        raise CampusError(Code.SCOPE_DENIED, "Use a staged PDF name from studocu stage.")
    with FileLock(str(private_path(root, "update.lock"))):
        previous = load_state(root)
        recovered = cleanup_completed_promotions(
            root, {item.resource.key: item for item in previous.resources}
        )
        queue = load_queue(root)
        document = _selected(root, document_id)
        if document.state == "downloaded" and document.staged_name != staged_name:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "This staged file was superseded; review it."
            )
        if document.state not in {"downloaded", "imported", "duplicate"}:
            raise CampusError(Code.ACTION_REQUIRED, "Stage the selected PDF before importing it.")
        path = private_path(root, f"studocu/incoming/{staged_name}")
        receipt_path = private_path(root, f"studocu/incoming/{staged_name}.json")
        receipt_body = _bounded(receipt_path, 4096)
        if not path.exists() and document.state in {"imported", "duplicate"}:
            existing = next(
                (
                    item
                    for item in previous.resources
                    if item.resource.key == f"studocu-{document_id}"
                ),
                None,
            )
            try:
                info = json.loads(receipt_body)
                relative = resolved_material_path(previous, existing) if existing else None
                if (
                    document.staged_name != staged_name
                    or existing is None
                    or existing.status != "current"
                    or existing.resource.studocu is None
                    or relative is None
                    or info["document_id"] != document_id
                    or info["sha256"] != existing.sha256
                    or info["identity_basis"] != "user_selected_file"
                    or info.get("validation", "validated") != "validated"
                    or not isinstance(info["page_count"], int)
                    or info["page_count"] != existing.resource.studocu.page_count
                    or digest(_bounded(confined(root, relative), MAX_PDF)) != existing.sha256
                ):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "The imported PDF needs review."
                ) from None
            apply(root, recovered)
            return {
                "state": "already_imported",
                "document_id": document_id,
                "pages": info["page_count"],
                "sha256": existing.sha256,
                "identity_basis": "user_selected_file",
                "generation": previous.generation,
            }
        body = _bounded(path, MAX_PDF)
        try:
            receipt = json.loads(receipt_body or b"")
            if (
                receipt["document_id"] != document_id
                or receipt["sha256"] != digest(body)
                or receipt["identity_basis"] != "user_selected_file"
            ):
                raise ValueError
            pages = validate_pdf(body)
            validation = receipt.get("validation", "validated")
            if validation not in {"pending", "validated"} or (
                validation == "validated" and receipt["page_count"] != pages
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise CampusError(
                Code.INVALID_RESPONSE, "Staged PDF or receipt needs review."
            ) from None
        matches = [b for b in previous.course.bindings if b.provider == "studocu"]
        if len(matches) > 1 or (matches and matches[0].course_id != queue.course_id):
            raise CampusError(
                Code.SCOPE_DENIED, "Studocu selection does not match the course binding."
            )
        if matches:
            binding = matches[0]
        else:
            if any(b.key == "studocu" for b in previous.course.bindings):
                raise CampusError(Code.WORKSPACE_CONFLICT, "The Studocu binding key is occupied.")
            binding = Binding(key="studocu", provider="studocu", course_id=queue.course_id)
        existing = next(
            (r for r in previous.resources if r.resource.key == f"studocu-{document_id}"), None
        )
        if (
            existing
            and existing.resource.studocu
            and existing.resource.studocu.storage_group != document.group
        ):
            raise CampusError(Code.WORKSPACE_CONFLICT, "Reclassification needs local review.")
        if (
            existing
            and existing.status == "current"
            and resolved_material_path(previous, existing)
            and existing.sha256 == digest(body)
            and document.state in {"imported", "duplicate"}
            and read_bytes(confined(root, resolved_material_path(previous, existing))) == body
        ):
            if document.staged_name == staged_name:
                relative = resolved_material_path(previous, existing)
                apply(
                    root,
                    (
                        Write(relative, body, body),
                        Write(
                            private_name(root, f"studocu/incoming/{staged_name}.json"),
                            receipt_body,
                            receipt_body,
                        ),
                        Write(private_name(root, f"studocu/incoming/{staged_name}"), body, None),
                        *recovered,
                    ),
                )
            else:
                apply(root, recovered)
            return {
                "state": "already_imported",
                "document_id": document_id,
                "pages": pages,
                "sha256": existing.sha256,
                "identity_basis": "user_selected_file",
                "generation": previous.generation,
            }
        history_writes: tuple[Write, ...] = ()
        existing_path = resolved_material_path(previous, existing) if existing else None
        if existing and existing_path and existing.sha256 != digest(body):
            if document.state in {"imported", "duplicate"}:
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Explicitly select refresh before replacing an imported PDF.",
                )
            old_body = read_bytes(confined(root, existing_path))
            if old_body is None or existing.sha256 is None or digest(old_body) != existing.sha256:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "The existing PDF was edited; review it first."
                )
            history_name = private_name(
                root, f"studocu/history/{document_id}/{existing.sha256}.pdf"
            )
            history_before = read_bytes(confined(root, history_name))
            if history_before is not None and history_before != old_body:
                raise CampusError(Code.WORKSPACE_CONFLICT, "A previous PDF version needs review.")
            history_writes = (Write(history_name, history_before, old_body),)
        duplicate_of = next(
            (
                item.resource.studocu.document_id
                for item in previous.resources
                if item.resource.studocu is not None
                and item.resource.studocu.document_id != document_id
                and document.year is not None
                and item.resource.studocu.year == document.year
                and item.resource.studocu.storage_group == document.group
                and item.resource.studocu.document_type == document.document_type
                and item.resource.studocu.page_count == pages
                and item.status == "current"
                and item.alias_of is None
                and item.sha256 == digest(body)
                and item.path is not None
                and read_bytes(confined(root, item.path)) == body
            ),
            None,
        )
        resources = {item.resource.key: item for item in previous.resources}
        from tum_mcp.studocu.aliases import Promotion

        promotion = Promotion()
        if existing and existing.path and (existing.sha256 != digest(body) or duplicate_of):
            promotion = promote_alias(root, resources, existing.resource.key)
            if promotion.writes:
                previous = type(previous).model_validate(
                    previous.model_dump() | {"resources": tuple(resources.values())}
                )
        alias_guard: tuple[Write, ...] = ()
        if duplicate_of:
            target = resources[f"studocu-{duplicate_of}"]
            if target.path is None:
                raise CampusError(Code.WORKSPACE_CONFLICT, "The alias original needs review.")
            alias_guard = (Write(target.path, body, body),)
        course = Course.model_validate(
            previous.course.model_dump()
            | {
                "bindings": (*previous.course.bindings, binding)
                if not matches
                else previous.course.bindings
            }
        )
        source = StudocuProvenance(
            document_id=document_id,
            course_id=queue.course_id,
            storage_group=document.group,
            raw_category=document.raw_category,
            document_type=document.document_type,
            year=document.year,
            lecturer=document.lecturer,
            language=document.language,
            acquired_at=receipt["acquired_at"],
            file_sha256=receipt["sha256"],
            page_count=pages,
        )
        resource = Resource(
            key=f"studocu-{document_id}",
            binding=binding.key,
            kind="exam"
            if document.group == "exams"
            else "content"
            if document.group == "summaries"
            else "other",
            title=document.title,
            url=document.url,
            studocu=source,
            source_file=staged_name,
        )
        retained = tuple(b.key for b in previous.course.bindings if b.key != binding.key)
        snapshot = Snapshot(
            schema_version=previous.schema_version,
            course=course,
            coverage=(
                Coverage(
                    binding=binding.key, status="partial", checked_at=datetime.now(UTC).isoformat()
                ),
            ),
            resources=(resource,),
            retained_bindings=retained,
        )
        updated = queue.model_copy(
            update={
                "documents": tuple(
                    item.model_copy(
                        update={
                            "state": "duplicate" if duplicate_of else "imported",
                            "duplicate_of": duplicate_of,
                            "validation": "validated",
                        }
                    )
                    if item.document_id == document_id
                    else item.model_copy(
                        update={
                            "state": "duplicate"
                            if resources[f"studocu-{item.document_id}"].alias_of
                            else "imported",
                            "duplicate_of": resources[
                                f"studocu-{item.document_id}"
                            ].alias_of.removeprefix("studocu-")
                            if resources[f"studocu-{item.document_id}"].alias_of
                            else None,
                        }
                    )
                    if promotion.writes
                    and item.state in {"imported", "duplicate"}
                    and f"studocu-{item.document_id}" in resources
                    else item
                    for item in queue.documents
                )
            }
        )
        before = read_bytes(queue_path(root))
        receipt_writes: tuple[Write, ...] = ()
        if validation == "pending":
            receipt.update({"validation": "validated", "page_count": pages})
            receipt_writes = (
                Write(
                    private_name(root, f"studocu/incoming/{staged_name}.json"),
                    receipt_body,
                    json.dumps(receipt).encode(),
                ),
            )
        report = _reconcile(
            root,
            path.parent / "snapshot.json",
            snapshot,
            previous,
            before_writes=(*promotion.writes, *history_writes),
            extra_writes=(
                *receipt_writes,
                Write(
                    private_name(root, "studocu/queue.json"),
                    before,
                    updated.model_dump_json(indent=2).encode(),
                ),
                *alias_guard,
                Write(private_name(root, f"studocu/incoming/{staged_name}"), body, None),
                *promotion.cleanup,
                *recovered,
            ),
            require_no_conflicts=True,
            alias_of=f"studocu-{duplicate_of}" if duplicate_of else None,
        )
        return {
            "state": "duplicate" if duplicate_of else "imported",
            "duplicate_of": duplicate_of,
            "document_id": document_id,
            "pages": pages,
            "sha256": digest(body),
            "identity_basis": "user_selected_file",
            "generation": report.generation,
        }
