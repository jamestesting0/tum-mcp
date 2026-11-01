"""Historical discovery feeds the same persistent preparation contract as current courses."""

from pathlib import Path
from typing import Literal

import pytest
from artemis_semester_fixture import ArtemisSemesterSite, artemis_site
from moodle_semester_fixture import MoodleSite, moodle_site

from tum_mcp import server
from tum_mcp.errors import CampusError
from tum_mcp.moodle.course_scope import term_of
from tum_mcp.moodle.models import Course as MoodleCourse
from tum_mcp.moodle.service import Service
from tum_mcp.study_models import Binding, Course, Coverage, Resource, Snapshot
from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync

__all__ = ["artemis_site", "moodle_site"]


def _prepare_ws23(
    root: Path, provider: Literal["moodle", "artemis"], course_id: int, url: str, text: str
) -> None:
    snapshot = Snapshot(
        course=Course(
            key="algorithms-ws23",
            title="Algorithms",
            semester="WS23/24",
            bindings=(Binding(key=provider, provider=provider, course_id=str(course_id)),),
        ),
        coverage=(Coverage(binding=provider, status="partial", checked_at="2026-10-31"),),
        resources=(
            Resource(
                key="past-source",
                binding=provider,
                kind="content",
                title="Past source",
                url=url,
                text=text,
            ),
        ),
    )
    path = root.parent / "snapshot.json"
    path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    sync(root, path, course_input="Algorithms")
    sync(root, path)
    state = load_state(root)
    assert state.course.semester == "WS23/24"
    assert state.course.bindings[0].course_id == str(course_id)
    assert text in (root / state.resources[0].path).read_text(encoding="utf-8")
    assert "WS23/24" in (root / ".tum-mcp/course.md").read_text(encoding="utf-8")
    before = (root / ".tum-mcp/state.json").read_bytes()
    for replacement in (
        snapshot.course.model_copy(update={"semester": "WS26/27"}),
        snapshot.course.model_copy(
            update={
                "bindings": (
                    Binding(
                        key=provider,
                        provider=provider,
                        course_id="2" if provider == "moodle" else "20",
                    ),
                )
            }
        ),
    ):
        changed = snapshot.model_copy(update={"course": replacement})
        path.write_text(changed.model_dump_json(), encoding="utf-8")
        with pytest.raises(CampusError, match="SCOPE_DENIED"):
            sync(root, path)
        assert (root / ".tum-mcp/state.json").read_bytes() == before


def test_moodle_ws23_preparation_selects_older_offering_and_keeps_binding(
    moodle_site: MoodleSite,
    tmp_path: Path,
) -> None:
    service = Service()
    _, courses, _ = service.moodle.courses(include_past=True)
    matches: list[MoodleCourse] = [
        course
        for course in courses
        if course.fullname == "Algorithms" and term_of(course) == "W23/24"
    ]
    assert [course.id for course in matches] == [1]
    assert any(course.id == 2 and course.fullname == "Algorithms" for course in courses)
    resource = next(item for item in service.materials(matches[0].id) if item.kind == "resource")
    _, content, _ = service.read(resource.id)
    text = content.pages[0].text
    _prepare_ws23(
        tmp_path / "course",
        "moodle",
        matches[0].id,
        resource.url,
        text,
    )


def test_artemis_ws23_preparation_selects_older_offering_and_keeps_binding(
    artemis_site: ArtemisSemesterSite,
    tmp_path: Path,
) -> None:
    courses = server.artemis_list_courses(artemis_site.account.id, include_past=True).courses
    matches = [c for c in courses if c.title == "Algorithms" and c.semester == "WS2023/24"]
    assert [course.id for course in matches] == [9]
    assert any(course.id == 20 and course.title == "Algorithms" for course in courses)
    exercise = server.artemis_get_exercise(artemis_site.account.id, matches[0].id, 94)
    assert exercise.exercise.problem_statement is not None
    _prepare_ws23(
        tmp_path / "course",
        "artemis",
        matches[0].id,
        exercise.source_link,
        exercise.exercise.problem_statement,
    )
