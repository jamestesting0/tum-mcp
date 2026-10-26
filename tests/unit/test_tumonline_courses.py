import json

import pytest
from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.courses import CoursePage


def listing() -> bytes:
    return json.dumps(
        {
            "totalCount": 25,
            "courses": [
                {
                    "id": 12345,
                    "courseNumber": {"databaseValue": "IN0001"},
                    "courseTitle": {"value": "Synthetic course"},
                    "semesterDto": {"semesterDesignation": {"value": "2026 W"}},
                    "courseTypeDto": {"courseTypeShortName": {"value": "VO"}},
                    "grade": "synthetic-hidden-grade",
                    "registrationInfo": "synthetic-hidden-personal",
                    "links": [{"href": "https://example.invalid/secret"}],
                }
            ],
        }
    ).encode()


def test_projection_drops_unrequested_fields_and_builds_fixed_origin_links() -> None:
    page = CoursePage.from_wire(listing(), offset=0, limit=1)
    course = page.courses[0]
    assert (course.id, course.number, course.title, course.term) == (
        12345,
        "IN0001",
        "Synthetic course",
        "2026 W",
    )
    assert course.source_link == "https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/"
    assert page.coverage_status == "partial"
    encoded = page.model_dump_json()
    assert "synthetic-hidden" not in encoded
    assert "example.invalid" not in encoded


@pytest.mark.parametrize("offset", [0, 10])
def test_empty_incomplete_page_is_retryable_failure(offset: int) -> None:
    with pytest.raises(CampusError) as raised:
        CoursePage.from_wire(b'{"totalCount":25,"courses":[]}', offset=offset, limit=20)
    assert raised.value.code == Code.OFFLINE


def test_empty_completed_page_is_valid() -> None:
    page = CoursePage.from_wire(b'{"totalCount":25,"courses":[]}', offset=25, limit=20)
    assert page.coverage_status == "complete"
    assert page.next_offset is None


def test_invalid_missing_and_wrongly_typed_fields_fail_closed() -> None:
    for body in (b"{}", b'{"totalCount":1,"courses":[{"id":-1}]}'):
        with pytest.raises(ValidationError):
            CoursePage.from_wire(body, offset=0, limit=20)


def test_invalid_page_bounds_and_inconsistent_counts_are_rejected() -> None:
    from tum_mcp.errors import CampusError

    for offset, limit in ((-1, 20), (0, 0), (0, 101)):
        with pytest.raises(CampusError):
            CoursePage.from_wire(listing(), offset=offset, limit=limit)
    with pytest.raises(CampusError):
        CoursePage.from_wire(listing(), offset=25, limit=1)


def test_large_course_page_is_bounded_and_cursor_tracks_only_returned_courses() -> None:
    item = json.loads(listing())["courses"][0]
    item["courseTitle"]["value"] = "講" * 4000
    rows = [dict(item, id=number) for number in range(1, 11)]
    body = json.dumps({"totalCount": 10, "courses": rows}).encode()
    page = CoursePage.from_wire(body, offset=0, limit=10)
    assert len(page.model_dump_json().encode()) <= 30_000
    assert page.courses and len(page.courses) < len(rows)
    assert page.next_offset == len(page.courses)
    assert page.coverage_status == "partial"
    tail = CoursePage.from_wire(
        json.dumps({"totalCount": 10, "courses": rows[page.next_offset :]}).encode(),
        offset=page.next_offset,
        limit=10,
    )
    assert tail.courses[0].id == page.courses[-1].id + 1
