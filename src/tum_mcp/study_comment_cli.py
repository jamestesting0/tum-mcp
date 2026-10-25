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
    view: Annotated[Literal["content", "flashcards", "practice"] | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    offset: Annotated[int, typer.Option(min=0)] = 0,
) -> None:
    """Read feedback as literal data, with the optimistic revision needed for resolution."""
    from tum_mcp.study_build import read_content, unit_revision
    from tum_mcp.study_comments import read_comments

    result = read_comments(project)
    units = {item.key: item for item in read_content(project.expanduser().resolve()).units}
    chosen = []
    for item in result["comments"]:
        if status != "all" and item["status"] != status:
            continue
        anchor = item["anchor"]
        if unit is not None and anchor["unit_key"] != unit:
            continue
        if view is not None and anchor["view"] != view:
            continue
        current = units.get(anchor["unit_key"])
        context = (
            "missing_unit"
            if current is None
            else (
                "current"
                if unit_revision(current) == anchor["unit_revision"]
                else "content_changed"
            )
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
