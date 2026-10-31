import os
import subprocess
import sys
import time
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field, JsonValue, TypeAdapter

from tum_mcp.moodle.auth import SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.moodle.downloads import list_downloads
from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.http_client import MoodleHTTP
from tum_mcp.moodle.material_search import moodle_search_materials
from tum_mcp.moodle.models import Post, TextPage
from tum_mcp.moodle.pagination import excerpt, offset_of
from tum_mcp.moodle.personal_records import PersonalRecords
from tum_mcp.moodle.protocol import StrictMCPServer
from tum_mcp.moodle.service import Service

server = StrictMCPServer("TUM Moodle")
READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
CourseId = Annotated[int, Field(gt=0)]
Limit = Annotated[int, Field(ge=1, le=50)]
MaxChars = Annotated[int, Field(ge=500, le=30000)]


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def moodle_auth_status() -> dict[str, str | float | None]:
    """Check whether a local Moodle session exists. Does not open a browser."""
    store = SessionStore(Paths.default())
    status = store.status()
    if status["state"] != "SAVED_SESSION":
        return status
    try:
        MoodleHTTP(store).get("/my/courses.php")
    except MoodleError as error:
        return {"state": error.code.value, "message": error.message}
    return {"state": "CONNECTED", "verified_at": time.time()}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
def moodle_login() -> dict[str, str]:
    """Start local Moodle sign-in; never accept passwords or codes through chat."""
    if os.environ.get("TUM_MOODLE_SESSION_STORAGE") == "file":
        return {
            "state": "ACTION_REQUIRED",
            "command": "tum-mcp login",
            "message": "Run tum-mcp login in your terminal and select Moodle. "
            "Moodle, Artemis and Zulip use the same browser sign-in flow.",
        }
    store = SessionStore(Paths.default())
    status = store.status()
    if status["state"] == "AUTHENTICATING":
        return {"state": "AUTHENTICATING", "message": "Complete sign-in in the open window."}
    subprocess.Popen(
        [sys.executable, "-m", "tum_mcp.moodle", "login"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env=os.environ.copy(),
    )
    return {"state": "STARTING", "message": "Complete sign-in in the browser, then check status."}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
def moodle_logout() -> dict[str, str]:
    """Remove the saved local Moodle session; does not revoke TUM's server-side sessions."""
    SessionStore(Paths.default()).logout()
    return {"state": "DISCONNECTED", "message": "Local Moodle credentials removed."}


@server.tool(
    annotations=READ,
    description="List enrolled courses from every semester, current semester first.",
)
def moodle_list_courses(cursor: str | None = None, limit: Limit = 20) -> dict[str, JsonValue]:
    result = Service().courses()
    courses = result["courses"]
    start = offset_of(cursor)
    if isinstance(courses, list):
        result["courses"] = courses[start : start + limit]
        result["next_cursor"] = str(start + limit) if start + limit < len(courses) else None
    return result


@server.tool(
    annotations=READ,
    description="Discover sections, files, links and activities in any accessible Moodle course.",
)
def moodle_list_materials(
    course_id: CourseId, cursor: str | None = None, limit: Limit = 50
) -> dict[str, JsonValue]:
    service = Service()
    materials = service.materials(course_id)
    start = offset_of(cursor)
    return {
        "materials": [item.model_dump(mode="json") for item in materials[start : start + limit]],
        "next_cursor": str(start + limit) if start + limit < len(materials) else None,
        "coverage": service.library.coverage(course_id),
    }


@server.tool(
    annotations=READ,
    description=(
        "Read bounded text with PDF page/slide numbers and source links. Page text drops "
        "figures and scrambles tables and formulas: look at a page before relying on it "
        "(the course project's copy, or the file from moodle_download_material)."
    ),
)
def moodle_read_material(
    material_id: str,
    start_page: Annotated[int | None, Field(ge=1)] = None,
    end_page: Annotated[int | None, Field(ge=1)] = None,
    cursor: str | None = None,
    max_chars: MaxChars = 12000,
) -> dict[str, JsonValue]:
    service = Service()
    material, content, fetched = service.read(material_id)
    return {
        "material": material.model_dump(mode="json"),
        "fetched_at": fetched,
        "freshness": "Use moodle_refresh for an explicit re-download.",
        "related_materials": [
            item.model_dump(mode="json")
            for item in service.library.materials(material.course_id)
            if item.parent_id == material.id
        ][:50],
        **excerpt(content, cursor, max_chars, start_page, end_page),
    }


@server.tool(
    annotations=READ,
    description="Save a Moodle file in Downloads/TUM Moodle and return its persistent local path.",
)
def moodle_download_material(material_id: str) -> dict[str, JsonValue]:
    return Service().download(material_id)


@server.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    description="List Moodle files already downloaded to this Mac, without requiring login.",
)
def moodle_list_downloads(cursor: str | None = None, limit: Limit = 20) -> dict[str, JsonValue]:
    files = list_downloads()
    offset = offset_of(cursor)
    return {
        "files": files[offset : offset + limit],
        "next_cursor": str(offset + limit) if offset + limit < len(files) else None,
    }


server.tool(
    annotations=READ,
    description="Search indexed course text or titles; always returns coverage.",
)(moodle_search_materials)


@server.tool(
    annotations=READ, description="Refresh metadata or index up to five materials per batch."
)
def moodle_refresh(
    course_id: CourseId,
    scope: Literal["metadata", "content"] = "metadata",
    cursor: str | None = None,
    limit: Annotated[int, Field(ge=1, le=5)] = 5,
) -> dict[str, JsonValue]:
    return Service().refresh(course_id, scope, offset_of(cursor), limit)


@server.tool(annotations=READ, description="List readable forums and course announcement boards.")
def moodle_list_forums(course_id: CourseId) -> dict[str, JsonValue]:
    return {
        "forums": [
            item.model_dump(mode="json")
            for item in Service().materials(course_id)
            if item.kind == "forum"
        ]
    }


@server.tool(
    annotations=READ, description="List visible threads in a discovered forum, with pagination."
)
def moodle_list_discussions(forum_id: str, cursor: str | None = None) -> dict[str, JsonValue]:
    service = Service()
    forum = service.require_material(forum_id)
    if forum.kind != "forum":
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Choose a forum from moodle_list_forums.")
    page = offset_of(cursor)
    discussions, more = service.expand(forum, page)
    return {
        "discussions": [item.model_dump(mode="json") for item in discussions],
        "next_cursor": str(page + 1) if more else None,
    }


@server.tool(
    annotations=READ,
    description="Read visible forum posts with authors, dates and post permalinks.",
)
def moodle_read_discussion(
    discussion_id: str, cursor: str | None = None, max_chars: MaxChars = 12000
) -> dict[str, JsonValue]:
    service = Service()
    result = service.discussion(discussion_id)
    cached = service.library.content(discussion_id)
    if cached is None:
        return result
    selected = excerpt(cached[0], cursor, max_chars, None, None)
    original = TypeAdapter(list[Post]).validate_python(result.pop("posts"))
    pieces = TypeAdapter(list[TextPage]).validate_python(selected.pop("pages"))
    result["posts"] = [
        original[piece.number - 1].model_copy(update={"text": piece.text}).model_dump(mode="json")
        for piece in pieces
    ]
    result.update(selected)
    return result


@server.tool(
    annotations=READ,
    description="List your own grades, feedback, submissions or matching message conversations.",
)
def moodle_list_personal_records(
    kind: Literal["grades", "feedback", "submissions", "messages"],
    course_id: CourseId | None = None,
    query: str | None = None,
    cursor: str | None = None,
    limit: Limit = 20,
) -> dict[str, JsonValue]:
    return PersonalRecords(Service()).list(kind, course_id, query, offset_of(cursor), limit)


@server.tool(
    annotations=READ,
    description="Read a previously listed own record; never changes or sends anything.",
)
def moodle_read_personal_record(
    record_id: str, cursor: str | None = None, max_chars: MaxChars = 12000
) -> dict[str, JsonValue]:
    return PersonalRecords(Service()).read(record_id, cursor, max_chars)


@server.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    description="Delete this integration's managed document cache and search index.",
)
def moodle_clear_cache() -> dict[str, str]:
    from tum_mcp.moodle.library import Library

    store = SessionStore(Paths.default())
    Library(store.paths, store.generation()).clear()
    return {"state": "CLEARED", "message": "Managed documents and search index removed."}
