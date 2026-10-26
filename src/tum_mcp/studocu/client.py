"""Anonymous, allowlisted reads of the public Studocu MCP."""

import json
from typing import Any, Final

import httpx2

from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import studocu_enabled

ENDPOINT: Final = "https://mcp.studocu.com/mcp"
PUBLIC_TOOLS: Final = {"search-courses", "search-documents", "search-institutions"}
MAX_RESPONSE: Final = 4 * 1024 * 1024


def search(
    name: str, arguments: dict[str, Any], *, transport: httpx2.BaseTransport | None = None
) -> dict:
    if name not in PUBLIC_TOOLS:
        raise CampusError(Code.SCOPE_DENIED, "Only public search operations are supported.")
    if not studocu_enabled():
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "The Studocu extension is disabled.")
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    try:
        with httpx2.Client(
            transport=transport, timeout=20, follow_redirects=False, trust_env=False
        ) as client:
            with client.stream(
                "POST",
                ENDPOINT,
                headers={"Accept": "application/json, text/event-stream"},
                json=body,
            ) as response:
                if response.status_code == 429:
                    raise CampusError(
                        Code.RATE_LIMITED, "Studocu rate-limited search; retry later."
                    )
                if response.status_code in {401, 403}:
                    raise CampusError(Code.AUTH_REQUIRED, "Studocu refused this search request.")
                if response.status_code != 200:
                    raise CampusError(Code.OFFLINE, "Studocu search is unavailable.")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE:
                        raise CampusError(Code.INVALID_RESPONSE, "Studocu response is too large.")
        if data.startswith(b"event:") or data.startswith(b"data:"):
            messages = [line[5:].strip() for line in data.splitlines() if line.startswith(b"data:")]
            data = bytearray(messages[-1] if messages else b"")
        result = json.loads(data)
        if (
            not isinstance(result, dict)
            or result.get("error")
            or not isinstance(result.get("result"), dict)
        ):
            raise ValueError
        result = result["result"]
        if result.get("isError"):
            raise CampusError(Code.INVALID_RESPONSE, "Studocu search returned an error.")
        content = result.get("structuredContent", {})
        if not isinstance(content, dict):
            raise ValueError
        if name == "search-courses":
            courses = content.get("courses", [])
            if not isinstance(courses, list):
                raise ValueError
            content = {
                "courses": [
                    {
                        key: item[key]
                        for key in (
                            "course_id",
                            "name",
                            "code",
                            "institution_id",
                            "institution_name",
                        )
                        if key in item
                    }
                    for item in courses
                    if isinstance(item, dict)
                    and isinstance(item.get("course_id"), int)
                    and item["course_id"] > 0
                    and item.get("institution_id") == arguments.get("institution_id")
                ]
            }
        if name == "search-documents":
            documents = content.get("documents", [])
            if not isinstance(documents, list):
                raise ValueError
            safe = []
            for item in documents:
                if not isinstance(item, dict):
                    raise ValueError
                document_id = str(item.get("id", ""))
                if not document_id.isascii() or not document_id.isdigit() or int(document_id) <= 0:
                    continue
                if item.get("course_id") != arguments.get("course_id"):
                    continue
                keep = {
                    key: item[key]
                    for key in (
                        "id",
                        "title",
                        "course",
                        "course_id",
                        "institution",
                        "institution_id",
                        "ratingPositive",
                        "ratingNegative",
                        "publishedAt",
                        "academicYears",
                        "description",
                        "numberOfPages",
                        "language",
                    )
                    if key in item
                }
                keep["url"] = f"https://www.studocu.com/de/document/{document_id}"
                from tum_mcp.studocu.discovery import classify

                group, kind = classify(str(item.get("title", "")), str(item.get("description", "")))
                keep["suggested_group"] = group
                keep["suggested_type"] = kind
                keep["classification"] = "heuristic_review_required"
                safe.append(keep)
            content = {"documents": safe}
        return {"data": content, "coverage": "partial", "untrusted": True}
    except httpx2.HTTPError:
        raise CampusError(Code.OFFLINE, "Studocu search could not be reached.") from None
    except (ValueError, UnicodeDecodeError):
        raise CampusError(
            Code.INVALID_RESPONSE, "Studocu returned an invalid search response."
        ) from None
