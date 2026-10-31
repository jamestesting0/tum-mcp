from typing import Literal, assert_never

import anyio
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from moodle_semester_fixture import MoodleSite, moodle_site

from tum_mcp.moodle.errors import MoodleError
from tum_mcp.moodle.server import (
    moodle_list_courses,
    moodle_list_materials,
    moodle_read_material,
    moodle_search_materials,
    server,
)
from tum_mcp.moodle.service import Service

__all__ = ["moodle_site"]


def test_discovery_keeps_every_semester_and_prefers_current_across_pages(
    moodle_site: MoodleSite,
) -> None:
    first = moodle_list_courses(limit=1)
    assert [course["id"] for course in first["courses"]] == [2]
    rest = moodle_list_courses(cursor=first["next_cursor"])
    assert [course["id"] for course in rest["courses"]] == [1, 3, 4, 6]
    assert [course["id"] for course in rest["unclassified"]] == [4]
    assert rest["next_cursor"] is None


@pytest.mark.parametrize("course_id", [1, 3, 4, 5, 6])
def test_material_reads_allow_old_unclassified_and_unlisted_accessible_courses(
    moodle_site: MoodleSite,
    course_id: int,
) -> None:
    materials = moodle_list_materials(course_id)["materials"]
    resource = next(item for item in materials if item["kind"] == "resource")
    reading = moodle_read_material(resource["id"])
    assert reading["material"]["course_id"] == course_id
    assert "Past semester lecture on scheduling" in reading["pages"][0]["text"]
    for mode in ("text", "titles"):
        found = moodle_search_materials("Past", course_id=course_id, mode=mode)
        identity = "material_id" if mode == "text" else "id"
        assert resource["id"] in [hit[identity] for hit in found["hits"]]
        assert str(course_id) in found["coverage"]


@pytest.mark.parametrize("course_id", [90, 91, 92, 93])
def test_server_denials_enrollment_pages_and_wrong_courses_are_rejected(
    moodle_site: MoodleSite,
    course_id: int,
) -> None:
    with pytest.raises(MoodleError, match="ACCESS_DENIED"):
        moodle_list_materials(course_id)


@pytest.mark.parametrize("operation", ["read", "inline", "download", "search", "search_all"])
def test_revoked_course_cannot_read_cached_materials_or_search(
    moodle_site: MoodleSite,
    operation: Literal["read", "inline", "download", "search", "search_all"],
) -> None:
    service = Service()
    materials = service.materials(1)
    resource = next(item for item in materials if item.kind == "resource")
    inline = next(item for item in materials if item.kind == "label")
    service.read(resource.id)
    moodle_site.denied.add(1)
    with pytest.raises(MoodleError, match="ACCESS_DENIED"):
        match operation:
            case "read":
                service.read(resource.id)
            case "inline":
                service.read(inline.id)
            case "download":
                service.download(resource.id)
            case "search":
                moodle_search_materials("Past", course_id=1)
            case "search_all":
                moodle_search_materials("Past")
            case unreachable:
                assert_never(unreachable)


def test_unscoped_search_keeps_past_hits_after_current_hits(moodle_site: MoodleSite) -> None:
    service = Service()
    for course_id in (1, 2):
        resource = next(item for item in service.materials(course_id) if item.kind == "resource")
        service.read(resource.id)
    found = moodle_search_materials("scheduling")
    assert [hit["material_id"] for hit in found["hits"]] == ["module:200", "module:100"]


def test_mcp_tool_calls_discover_read_and_reject_denied_past_courses(
    moodle_site: MoodleSite,
) -> None:
    async def check() -> None:
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as group:
                group.start_soon(
                    server._lowlevel_server.run,
                    *server_streams,
                    server._lowlevel_server.create_initialization_options(),
                )
                async with ClientSession(*client_streams) as client:
                    await client.initialize()
                    listed = await client.call_tool("moodle_list_courses", {})
                    assert [c["id"] for c in listed.structured_content["courses"]] == [
                        2,
                        1,
                        3,
                        4,
                        6,
                    ]
                    materials = await client.call_tool("moodle_list_materials", {"course_id": 1})
                    resource = materials.structured_content["materials"][0]
                    read = await client.call_tool(
                        "moodle_read_material", {"material_id": resource["id"]}
                    )
                    assert "scheduling" in read.structured_content["pages"][0]["text"]
                    moodle_site.denied.add(1)
                    denied = await client.call_tool("moodle_list_materials", {"course_id": 1})
                    assert denied.is_error and "ACCESS_DENIED" in denied.content[0].text
                group.cancel_scope.cancel()

    anyio.run(check)
