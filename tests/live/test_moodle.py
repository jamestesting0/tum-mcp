import os
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tum_mcp.moodle.service import Service

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("TUM_MOODLE_LIVE") != "1",
        reason="Set TUM_MOODLE_LIVE=1 after personal sign-in.",
    ),
]


def test_real_time_systems_pdf_and_search() -> None:
    service = Service()
    _, courses, _ = service.moodle.courses()
    course = next(course for course in courses if "Echtzeit" in course.fullname)
    materials = service.materials(course.id)
    lecture = next(item for item in materials if item.kind == "resource")
    item, extracted, _ = service.read(lecture.id)
    assert item.course_id == course.id
    assert len(extracted.pages) >= 1
    assert sum(len(page.text) for page in extracted.pages) > 500
    assert service.library.search("real", course.id, 5)


def test_installed_mcp_reads_and_downloads_the_lecture(tmp_path: Path) -> None:
    launcher = os.environ.get("TUM_MOODLE_PACKAGED")
    if launcher is None:
        pytest.skip("Set TUM_MOODLE_PACKAGED to test the installed runtime.")

    async def check() -> None:
        params = StdioServerParameters(
            command="/usr/bin/python3", args=[launcher], cwd=str(tmp_path)
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=60) as client:
                await client.initialize()
                courses = await client.call_tool("moodle_list_courses")
                assert not courses.is_error
                course = next(
                    item
                    for item in courses.structured_content["courses"]
                    if "Echtzeit" in item["fullname"]
                )
                materials = await client.call_tool(
                    "moodle_list_materials", {"course_id": course["id"]}
                )
                assert not materials.is_error
                lecture = next(
                    item
                    for item in materials.structured_content["materials"]
                    if item["kind"] == "resource"
                )
                reading = await client.call_tool(
                    "moodle_read_material",
                    {
                        "material_id": lecture["id"],
                        "start_page": 1,
                        "end_page": 1,
                    },
                )
                assert not reading.is_error
                assert reading.structured_content["pages"][0]["number"] == 1
                downloaded = await client.call_tool(
                    "moodle_download_material",
                    {
                        "material_id": lecture["id"],
                    },
                )
                assert not downloaded.is_error
                path = Path(downloaded.structured_content["path"])
                body = await anyio.to_thread.run_sync(path.read_bytes)
                assert body.startswith(b"%PDF-")
                assert path.parent.parent.name == "TUM Moodle"

    anyio.run(check)
