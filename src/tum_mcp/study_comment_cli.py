"""Small agent handoff: read passage feedback and resolve only a reviewed revision."""

import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import typer

from tum_mcp.errors import CampusError, Code

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.command(name="list")
def list_comments(
    project: Path,
    status: Annotated[Literal["open", "resolved", "all"], typer.Option()] = "open",
    unit: Annotated[str | None, typer.Option()] = None,
    view: Annotated[
        Literal["content", "flashcards", "practice", "explore", "exercises", "lectures", "exam"]
        | None,
        typer.Option(),
    ] = None,
    exercise: Annotated[str | None, typer.Option()] = None,
    lecture: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    offset: Annotated[int, typer.Option(min=0)] = 0,
) -> None:
    """Read feedback as literal data, with the optimistic revision needed for resolution."""
    from tum_mcp.course_app_paths import app_path
    from tum_mcp.exercise_content import exercise_revision
    from tum_mcp.exercise_data import read_exercises
    from tum_mcp.lecture_data import read_lectures
    from tum_mcp.study_build import explore_revision, read_content, unit_revision
    from tum_mcp.study_comments import read_comments

    result = read_comments(project)
    root = project.expanduser().resolve()
    units = (
        {item.key: item for item in read_content(root).units}
        if app_path(root, "content.json").exists()
        else {}
    )
    content = read_exercises(root)
    exercises = (
        {item.key: item for group in content.sets for item in group.exercises} if content else {}
    )
    notes = read_lectures(root)
    from tum_mcp.exam_data import exam_revisions, read_exam

    exam = read_exam(root)
    exam_items = exam_revisions(exam) if exam else {}
    lectures = {item.key: item for item in notes.lectures} if notes else {}
    chosen = []
    for item in result["comments"]:
        if status != "all" and item["status"] != status:
            continue
        anchor = item["anchor"]
        if unit is not None and anchor.get("unit_key") != unit:
            continue
        if exercise is not None and anchor.get("exercise_key") != exercise:
            continue
        if lecture is not None and anchor.get("lecture_key") != lecture:
            continue
        if view is not None and anchor["view"] != view:
            continue
        if anchor["view"] == "lectures":
            current = lectures.get(anchor["lecture_key"])
            revision = current.semantic_revision if current else None
            previous = anchor["semantic_revision"]
            exists = current and any(s.key == anchor["section_key"] for s in current.sections)
        elif anchor["view"] == "explore":
            owner = units.get(anchor["unit_key"])
            material = (
                next((part for part in owner.explore if part.key == anchor["item_key"]), None)
                if owner
                else None
            )
            revision = explore_revision(material) if material else None
            previous = anchor["semantic_revision"]
            exists = material and any(b.key == anchor["block_key"] for b in material.blocks)
        elif anchor["view"] == "exam":
            revision = exam_items.get(anchor["item_key"])
            previous = anchor["item_revision"]
            exists = revision is not None
        elif anchor["view"] == "exercises":
            current = exercises.get(anchor["exercise_key"])
            revision = exercise_revision(current) if current else None
            previous = anchor["exercise_revision"]
            exists = current is not None
        else:
            current = units.get(anchor["unit_key"])
            revision = unit_revision(current) if current else None
            previous = anchor["unit_revision"]
            exists = current is not None
        context = (
            "missing_unit"
            if not exists
            else "current"
            if revision == previous
            else "content_changed"
        )
        chosen.append(item | {"content_state": context})
    result["comments"] = chosen[offset : offset + limit]
    result["total"] = len(chosen)
    result["next_offset"] = offset + limit if offset + limit < len(chosen) else None
    typer.echo(json.dumps(result, indent=2))


@app.command()
def resolve(
    project: Path,
    comment_id: UUID,
    expected_revision: Annotated[str, typer.Option()],
    resolution_file: Annotated[Path, typer.Option()],
) -> None:
    """Mark one verified note resolved, preserving any concurrently edited feedback."""
    from pydantic import ValidationError

    from tum_mcp.study_comment_models import SetStatus
    from tum_mcp.study_comments import change_comment, read_comments

    if not resolution_file.is_file() or resolution_file.stat().st_size > 8000:
        raise CampusError(Code.ACTION_REQUIRED, "Supply a short UTF-8 resolution file.")
    try:
        resolution = resolution_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise CampusError(Code.INVALID_RESPONSE, "The resolution file could not be read.") from None
    if not resolution or len(resolution) > 2000:
        raise CampusError(
            Code.ACTION_REQUIRED, "Explain the verified correction in 1–2000 characters."
        )
    document = read_comments(project)
    try:
        operation = SetStatus(
            op="status",
            id=comment_id,
            expected_revision=expected_revision,
            course_identity=document["course_identity"],
            status="resolved",
            resolution=resolution,
        )
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Use the revision returned by comments list."
        ) from None
    result = change_comment(project, operation)
    typer.echo(
        json.dumps({"id": str(comment_id), "status": "resolved", "revision": result["revision"]})
    )
