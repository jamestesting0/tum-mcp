"""Bounded Moodle material search tool."""

from typing import Annotated, Literal, assert_never

from pydantic import Field, JsonValue

from tum_mcp.moodle.pagination import offset_of
from tum_mcp.moodle.service import Service

CourseId = Annotated[int, Field(gt=0)]
Limit = Annotated[int, Field(ge=1, le=50)]


def moodle_search_materials(
    query: Annotated[str, Field(min_length=1, max_length=500)],
    course_id: CourseId | None = None,
    mode: Literal["text", "titles"] = "text",
    limit: Limit = 20,
    cursor: str | None = None,
) -> dict[str, JsonValue]:
    service = Service()
    start = offset_of(cursor)
    count = min(start + limit + 1, 1000)
    if course_id is None:
        _, courses, _ = service.moodle.courses()
        ids = [course.id for course in courses]
    else:
        ids = [course_id]
    hits: list[JsonValue] = []
    coverage: dict[str, JsonValue] = {}
    for identity in ids:
        service.moodle.require_course(identity)
        coverage[str(identity)] = service.library.coverage(identity)
        match mode:
            case "titles":
                hits.extend(
                    item.model_dump(mode="json")
                    for item in service.library.materials(identity)
                    if not item.kind.startswith("private_")
                    and query.casefold() in item.title.casefold()
                )
            case "text":
                hits.extend(
                    item.model_dump(mode="json")
                    for item in service.library.search(query, identity, count)
                )
            case unreachable:
                assert_never(unreachable)
    return {
        "hits": hits[start : start + limit],
        "next_cursor": str(start + limit) if start + limit < len(hits) else None,
        "coverage": coverage,
        "note": "Only indexed content was searched. Refresh to index missing materials.",
    }
