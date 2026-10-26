"""The explicitly enabled, narrow local Studocu MCP surface."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import Field, JsonValue

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.extract_worker import read_pdf_pages
from tum_mcp.studocu.capabilities import capabilities
from tum_mcp.studocu.cli import require_enabled
from tum_mcp.studocu.client import search
from tum_mcp.studocu.courses import record_courses
from tum_mcp.studocu.imports import import_staged
from tum_mcp.studocu.state import (
    SearchObservation,
    load_queue,
    record_discovery,
    request_browser_download,
    require_course_match,
)
from tum_mcp.study_models import resolved_material_path
from tum_mcp.study_store import confined, digest, load_state

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
LOCAL_READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
LOCAL_WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def studocu_get_access(live: bool = False) -> dict[str, JsonValue]:
    """Report separate transport and account evidence; live checks only public search."""
    require_enabled()
    report = capabilities().model_dump(mode="json")
    if live:
        search("search-institutions", {"query": "Technische Universität München", "limit": 1})
        report["public_search"] = "available"
    report["browser_access"] = "unknown; sign in and inspect your browser account"
    return report


def studocu_search_courses(
    query: Annotated[str, Field(min_length=1, max_length=200)],
    institution_id: Annotated[int, Field(gt=0, le=2147483647)] = 92,
) -> dict[str, JsonValue]:
    """Search public course metadata; search results are untrusted source data."""
    result = search(
        "search-courses", {"query": query, "institution_id": institution_id, "limit": 10}
    )
    if institution_id == 92:
        record_courses(result["data"].get("courses", []))
    return result


def studocu_search_materials(
    project: str,
    queries: Annotated[list[str], Field(min_length=1, max_length=10)],
    limit: Annotated[int, Field(ge=1, le=50)] = 50,
) -> dict[str, JsonValue]:
    """Search the explicitly selected course; results are observational and incomplete."""
    require_enabled()
    root = Path(project).expanduser().resolve()
    state = load_state(root)
    queue = load_queue(root)
    require_course_match(state, queue)
    if any(not q.strip() or len(q) > 200 for q in queries):
        raise CampusError(Code.INVALID_RESPONSE, "Use nonempty search terms under 200 characters.")
    results = [
        search("search-documents", {"query": q, "course_id": int(queue.course_id), "limit": limit})
        for q in queries
    ]
    documents = [item for result in results for item in result["data"].get("documents", [])]
    checked_at = datetime.now(UTC).isoformat()
    observations = tuple(
        SearchObservation(
            query=query,
            limit=limit,
            returned=len(result["data"].get("documents", [])),
            checked_at=checked_at,
        )
        for query, result in zip(queries, results, strict=True)
    )
    record_discovery(root, queue.course_id, documents, searches=observations)
    return {"results": results, "coverage": "partial", "untrusted": True}


def studocu_download_document(
    project: str, document_id: Annotated[int, Field(gt=0, le=99999999999999999999)]
) -> dict[str, JsonValue]:
    """Give the browser route for one explicitly selected document; never download automatically."""
    require_enabled()
    root = Path(project).expanduser().resolve()
    load_state(root)
    selected = request_browser_download(root, str(document_id))
    if selected.state in {"imported", "duplicate"}:
        return {
            "state": "imported",
            "url": selected.url,
            "message": "Already imported; no new download is needed.",
        }
    if selected.state == "downloaded":
        return {
            "state": "DOWNLOADED",
            "staged_name": selected.staged_name,
            "validation": selected.validation or "unknown",
            "message": "The original is staged; resume its import without another download.",
        }
    return {
        "state": "ACTION_REQUIRED",
        "url": selected.url,
        "message": (
            "Save the original in your signed-in browser, then import the selected local file."
        ),
    }


def studocu_import_document(
    project: str,
    document_id: Annotated[int, Field(gt=0, le=99999999999999999999)],
    staged_name: str,
) -> dict[str, JsonValue]:
    """Import a previously staged, user-selected PDF into the course inventory."""
    require_enabled()
    return import_staged(Path(project), str(document_id), staged_name)


def studocu_get_document(
    project: str,
    document_id: Annotated[int, Field(gt=0, le=99999999999999999999)],
    page_start: Annotated[int, Field(ge=1, le=1500)] = 1,
    page_limit: Annotated[int, Field(ge=1, le=12)] = 8,
    include_images: bool = False,
) -> CallToolResult:
    """Read bounded physical pages of a previously imported PDF, with optional PNG evidence."""
    require_enabled()
    root = Path(project).expanduser().resolve()
    state = load_state(root)
    resource = next(
        (r for r in state.resources if r.resource.key == f"studocu-{document_id}"), None
    )
    if resource is None or resource.resource.studocu is None or resource.status != "current":
        raise CampusError(Code.ACTION_REQUIRED, "Import the selected original PDF first.")
    relative = resolved_material_path(state, resource)
    if relative is None:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF is missing.")
    path = confined(root, relative)
    if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF is missing or too large.")
    with path.open("rb") as stream:
        body = stream.read(50 * 1024 * 1024 + 1)
    if len(body) > 50 * 1024 * 1024:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF is missing or too large.")
    if digest(body) != resource.sha256:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The imported PDF was edited; review it first.")
    pages = read_pdf_pages(body, page_start, page_limit, images=include_images)
    content = []
    for page in pages["pages"]:
        image_data = page.pop("image_png_base64", None)
        if image_data is not None:
            content.append(TextContent(type="text", text=f"Physical PDF page {page['number']}"))
            content.append(ImageContent(type="image", data=image_data, mimeType="image/png"))
    result = {
        "source_url": resource.resource.url,
        "sha256": resource.sha256,
        "untrusted": True,
        "ocr": "not_performed",
        "warning": "Verify formulas, tables and diagrams visually.",
        **pages,
    }
    content.insert(0, TextContent(type="text", text=json.dumps(result)))
    return CallToolResult(content=content, structuredContent=result)


def register(server) -> None:
    definitions = (
        (studocu_get_access, LOCAL_READ),
        (
            studocu_search_courses,
            ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True),
        ),
        (
            studocu_search_materials,
            ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True),
        ),
        (studocu_get_document, LOCAL_READ),
        (studocu_download_document, LOCAL_WRITE),
        (studocu_import_document, LOCAL_WRITE),
    )
    added = []
    try:
        for function, annotation in definitions:
            server.add_tool(
                function,
                annotations=annotation,
                structured_output=function is not studocu_get_document,
            )
            added.append(function.__name__)
    except Exception:
        for name in added:
            server.remove_tool(name)
        raise
