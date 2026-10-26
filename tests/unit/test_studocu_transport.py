import httpx2
import pytest

from tum_mcp.errors import CampusError
from tum_mcp.studocu.client import search


def test_anonymous_search_filters_course_and_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tum_mcp.studocu.client.studocu_enabled", lambda: True)

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://mcp.studocu.com/mcp"
        assert "authorization" not in request.headers
        return httpx2.Response(
            200,
            json={
                "result": {
                    "structuredContent": {
                        "documents": [
                            {
                                "id": "42",
                                "course_id": 123,
                                "title": "Mock",
                                "url": "https://studocu.com/?token=canary",
                            },
                            {"id": "43", "course_id": 999, "title": "Wrong course"},
                        ]
                    }
                }
            },
        )

    result = search(
        "search-documents",
        {"query": "exam", "course_id": 123},
        transport=httpx2.MockTransport(handle),
    )
    assert result["coverage"] == "partial"
    assert result["data"]["documents"] == [
        {
            "id": "42",
            "course_id": 123,
            "title": "Mock",
            "url": "https://www.studocu.com/de/document/42",
            "suggested_group": "exams",
            "suggested_type": "mock",
            "classification": "heuristic_review_required",
        }
    ]
    assert "canary" not in str(result)


def test_redirect_and_upstream_write_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tum_mcp.studocu.client.studocu_enabled", lambda: True)
    calls = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        calls.append(str(request.url))
        return httpx2.Response(302, headers={"Location": "https://evil.example/?token=canary"})

    with pytest.raises(CampusError) as error:
        search("search-courses", {"query": "test"}, transport=httpx2.MockTransport(handle))
    assert "canary" not in str(error.value)
    with pytest.raises(CampusError):
        search("write-artifact", {}, transport=httpx2.MockTransport(handle))
    assert calls == ["https://mcp.studocu.com/mcp"]
