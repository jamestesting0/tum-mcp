import json
from typing import Literal, assert_never

import anyio
import pytest
from artemis_semester_fixture import ArtemisSemesterSite, artemis_site
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from typer.testing import CliRunner

from tum_mcp import server
from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.transport import API

__all__ = ["artemis_site"]


@pytest.mark.parametrize(
    "active,past,expected",
    [
        (True, True, [20, 9, 10]),
        (False, True, [9, 10, 20]),
        (True, False, [20]),
        (False, False, []),
    ],
)
def test_discovery_includes_past_semesters_after_active_courses_without_duplicates(
    artemis_site: ArtemisSemesterSite,
    active: bool,
    past: bool,
    expected: list[int],
) -> None:
    artemis_site.active, artemis_site.past = active, past
    result = server.artemis_list_courses(artemis_site.account.id, include_past=True)
    assert [item.id for item in result.courses] == expected
    assert all(item.active == (active and item.id == 20) for item in result.courses)
    if past:
        assert next(item for item in result.courses if item.id == 9).semester == "WS2023/24"
    if active:
        assert result.courses[0].title == "Algorithms"
    assert "staffOnly" not in result.model_dump_json()


@pytest.mark.parametrize("course_id", [9, 10, 77])
def test_past_and_unlisted_exercises_remain_released_student_statement_reads(
    artemis_site: ArtemisSemesterSite,
    course_id: int,
) -> None:
    account = artemis_site.account.id
    listed = server.artemis_list_exercises(account, course_id)
    assert [item.id for item in listed.exercises] == [course_id * 10 + 4]
    assert listed.exercises[0].problem_statement is None
    assert listed.exercises[0].student_participations is None
    read = server.artemis_get_exercise(account, course_id, course_id * 10 + 4)
    assert read.exercise.problem_statement == "Past semester statement."
    assert read.exercise.student_participations is None


@pytest.mark.parametrize("course_id", [9, 77])
def test_past_and_unlisted_lectures_and_student_pdfs_are_readable(
    artemis_site: ArtemisSemesterSite,
    course_id: int,
) -> None:
    account = artemis_site.account.id
    lecture_id = server.artemis_list_lectures(account, course_id).lectures[0].id
    read = server.artemis_get_lecture(account, course_id, lecture_id)
    assert [unit.type for unit in read.lecture.units] == ["text", "attachment"]
    assert read.lecture.units[0].content == "Past semester teaching."
    slides = server.artemis_get_attachment(account, course_id, lecture_id, course_id * 100 + 3)
    assert "Past semester student slides" in slides.pages[0].text
    assert slides.saved_path is None
    assert not any("staff-original" in path for path in artemis_site.calls)


@pytest.mark.parametrize("status,code", [(403, "AUTH_REQUIRED"), (404, "CAPABILITY_UNSUPPORTED")])
def test_archive_denial_or_unavailability_is_not_reported_as_empty_history(
    artemis_site: ArtemisSemesterSite,
    status: int,
    code: str,
) -> None:
    artemis_site.archive_status = status
    with pytest.raises(CampusError, match=code):
        server.artemis_list_courses(artemis_site.account.id, include_past=True)


@pytest.mark.parametrize("kind", ["exercises", "exercise", "lecture", "slides"])
def test_denied_past_course_remains_denied_for_every_read(
    artemis_site: ArtemisSemesterSite,
    kind: Literal["exercises", "exercise", "lecture", "slides"],
) -> None:
    artemis_site.denied.add(9)
    account = artemis_site.account.id
    with pytest.raises(CampusError, match="AUTH_REQUIRED"):
        match kind:
            case "exercises":
                server.artemis_list_exercises(account, 9)
            case "exercise":
                server.artemis_get_exercise(account, 9, 94)
            case "lecture":
                server.artemis_get_lecture(account, 9, 91)
            case "slides":
                server.artemis_get_attachment(account, 9, 91, 903)
            case unreachable:
                assert_never(unreachable)


@pytest.mark.parametrize(
    "path",
    [
        "/api/course/courses/9/archive",
        "/api/course/courses/9/download-archive",
        "/api/course/courses/9/enroll",
        "/api/course/courses/9/cleanup",
    ],
)
def test_archive_discovery_does_not_enable_archive_exports_or_enrollment(
    artemis_site: ArtemisSemesterSite,
    path: str,
) -> None:
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        API(artemis_site.account).get(path)


def test_real_mcp_client_discovers_and_reads_past_content_then_preserves_denial(
    artemis_site: ArtemisSemesterSite,
) -> None:
    async def check() -> None:
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                group.start_soon(
                    server.server._lowlevel_server.run,
                    *server_streams,
                    server.server._lowlevel_server.create_initialization_options(),
                )
                async with ClientSession(*client_streams) as client:
                    await client.initialize()
                    account = {"account_id": artemis_site.account.id}
                    current = await client.call_tool("artemis_list_courses", account)
                    assert [c["id"] for c in current.structured_content["courses"]] == [20]
                    assert not any("for-archive" in path for path in artemis_site.calls)
                    courses = await client.call_tool(
                        "artemis_list_courses", {**account, "include_past": True}
                    )
                    assert not courses.is_error, courses.content
                    assert [item["id"] for item in courses.structured_content["courses"]] == [
                        20,
                        9,
                        10,
                    ]
                    read = await client.call_tool(
                        "artemis_get_exercise",
                        {
                            **account,
                            "course_id": 9,
                            "exercise_id": 94,
                        },
                    )
                    assert not read.is_error, read.content
                    assert (
                        read.structured_content["exercise"]["problemStatement"]
                        == "Past semester statement."
                    )
                    artemis_site.denied.add(9)
                    denied = await client.call_tool(
                        "artemis_get_lecture",
                        {
                            **account,
                            "course_id": 9,
                            "lecture_id": 91,
                        },
                    )
                    assert denied.is_error and "AUTH_REQUIRED" in denied.content[0].text
                group.cancel_scope.cancel()

    anyio.run(check)


@pytest.mark.parametrize("active", [True, False])
def test_default_discovery_skips_archive_even_if_history_is_denied(
    artemis_site: ArtemisSemesterSite,
    active: bool,
) -> None:
    artemis_site.active = active
    artemis_site.archive_status = 403
    result = server.artemis_list_courses(artemis_site.account.id)
    assert [course.id for course in result.courses] == ([20] if active else [])
    assert artemis_site.calls == [
        "/api/core/public/account",
        "/api/course/courses/for-dropdown",
    ]


@pytest.mark.parametrize("include_past", [False, True])
def test_cli_history_flag_controls_archive_requests(
    artemis_site: ArtemisSemesterSite,
    include_past: bool,
) -> None:
    args = ["discover", "artemis", artemis_site.account.id]
    if include_past:
        args.append("--include-past")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert [c["id"] for c in json.loads(result.output)] == ([20, 9, 10] if include_past else [20])
    assert len(artemis_site.calls) == (3 if include_past else 2)


def test_cli_rejects_history_flag_for_other_providers_before_access() -> None:
    result = CliRunner().invoke(app, ["discover", "zulip", "missing", "--include-past"])
    assert result.exit_code == 2
    assert "applies to Artemis" in result.output
