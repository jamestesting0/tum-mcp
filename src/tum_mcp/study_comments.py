"""Course-local comments with confined private writes and compare-and-swap updates."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never

from filelock import FileLock
from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_comment_models import (
    Comment,
    Comments,
    Create,
    Delete,
    Edit,
    ExploreAnchor,
    LectureAnchor,
    Operation,
    SetStatus,
)
from tum_mcp.study_store import (
    Write,
    apply,
    digest,
    load_state,
    private_name,
    private_path,
    read_bytes,
)

LIMIT = 2 * 1024 * 1024


def _read(root: Path) -> tuple[Comments, bytes | None]:
    state = load_state(root)
    identity = digest(json.dumps([state.course.key, state.course.semester]).encode())
    path = private_path(root, "comments.json")
    if path.exists() and path.stat().st_size > LIMIT:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Comments exceed the local storage limit.")
    before = read_bytes(path)
    try:
        document = (
            Comments.model_validate_json(before)
            if before is not None
            else Comments(course_identity=identity)
        )
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid comment file preserved; review it locally."
        ) from None
    if document.course_identity != identity:
        raise CampusError(Code.SCOPE_DENIED, "Comments belong to another course project.")
    return document, before


def _revision(document: Comments, before: bytes | None) -> str:
    return digest(before if before is not None else document.model_dump_json(indent=2).encode())


def read_comments(root: Path) -> dict:
    root = root.expanduser().resolve()
    load_state(root)
    with FileLock(str(private_path(root, "comments.lock"))):
        document, before = _read(root)
        return document.model_dump(mode="json") | {"revision": _revision(document, before)}


def change_comment(root: Path, operation: Operation) -> dict:
    root = root.expanduser().resolve()
    load_state(root)
    with FileLock(str(private_path(root, "comments.lock"))):
        document, before = _read(root)
        if operation.course_identity != document.course_identity:
            raise CampusError(Code.SCOPE_DENIED, "Comment request belongs to another course.")
        if operation.expected_revision != _revision(document, before):
            raise CampusError(Code.STALE_RESULT, "Comments changed. Review before retrying.")
        now = datetime.now(UTC)
        items = list(document.comments)
        index = next((i for i, item in enumerate(items) if item.id == operation.id), None)
        match operation:
            case Create():
                if index is not None:
                    raise CampusError(Code.WORKSPACE_CONFLICT, "This comment is already saved.")
                if len(items) >= 500:
                    raise CampusError(Code.ACTION_REQUIRED, "The project has reached 500 comments.")
                if isinstance(operation.anchor, ExploreAnchor):
                    from tum_mcp.study_build import explore_revision, read_content

                    anchor = operation.anchor
                    content = read_content(root)
                    material = next(
                        (
                            item
                            for unit in content.units
                            if unit.key == anchor.unit_key
                            for item in unit.explore
                            if item.key == anchor.item_key
                        ),
                        None,
                    )
                    if material is None or not any(
                        block.key == anchor.block_key for block in material.blocks
                    ):
                        raise CampusError(
                            Code.SCOPE_DENIED, "This Explore passage no longer exists."
                        )
                    if explore_revision(material) != anchor.semantic_revision:
                        raise CampusError(
                            Code.STALE_RESULT, "Explore material changed. Reload before commenting."
                        )
                elif isinstance(operation.anchor, LectureAnchor):
                    from tum_mcp.lecture_data import read_lectures

                    content = read_lectures(root)
                    lecture = (
                        next(
                            (
                                item
                                for item in content.lectures
                                if item.key == operation.anchor.lecture_key
                            ),
                            None,
                        )
                        if content
                        else None
                    )
                    if lecture is None or not any(
                        item.key == operation.anchor.section_key for item in lecture.sections
                    ):
                        raise CampusError(
                            Code.SCOPE_DENIED, "This lecture passage no longer exists."
                        )
                    if lecture.semantic_revision != operation.anchor.semantic_revision:
                        raise CampusError(
                            Code.STALE_RESULT, "Lecture notes changed. Reload before commenting."
                        )
                items.append(
                    Comment(
                        id=operation.id,
                        anchor=operation.anchor,
                        text=operation.text,
                        created_at=now,
                        updated_at=now,
                    )
                )
            case Edit() | SetStatus() | Delete():
                if index is None:
                    raise CampusError(Code.STALE_RESULT, "This comment was removed.")
                original = items[index]
                match operation:
                    case Edit():
                        items[index] = original.model_copy(
                            update={
                                "text": operation.text,
                                "status": "open",
                                "resolution": "",
                                "updated_at": now,
                            }
                        )
                    case SetStatus():
                        items[index] = original.model_copy(
                            update={
                                "status": operation.status,
                                "resolution": operation.resolution
                                if operation.status == "resolved"
                                else "",
                                "updated_at": now,
                            }
                        )
                    case Delete():
                        items.pop(index)
                    case unreachable:
                        assert_never(unreachable)
            case unreachable:
                assert_never(unreachable)
        version = max(
            document.schema_version,
            4
            if any(isinstance(item.anchor, ExploreAnchor) for item in items)
            else 3
            if any(isinstance(item.anchor, LectureAnchor) for item in items)
            else 2,
        )
        updated = document.model_copy(update={"schema_version": version, "comments": tuple(items)})
        after = updated.model_dump_json(indent=2).encode()
        if len(after) > LIMIT:
            raise CampusError(Code.ACTION_REQUIRED, "Comments exceed the local storage limit.")
        apply(root, (Write(private_name(root, "comments.json"), before, after),))
        return updated.model_dump(mode="json") | {"revision": digest(after)}
