import json

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
                "jsonrpc": "2.0",
                "id": 1,
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
                },
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


def test_streamed_search_stops_at_its_complete_multiline_reply(monkeypatch) -> None:
    monkeypatch.setattr("tum_mcp.studocu.client.studocu_enabled", lambda: True)

    class Events(httpx2.SyncByteStream):
        def __iter__(self):
            yield b": keepalive\r\n"
            yield b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\r\n\r\n'
            yield b'event: message\r\ndata: {"jsonrpc":"2.0","id":1,\r\n'
            yield b'data: "result":{"structuredContent":{"courses":[]}}}\r\n\r\n'
            raise AssertionError("A completed reply must not wait for the stream to close")

    result = search(
        "search-courses",
        {"query": "graph", "institution_id": 92},
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Events()
            )
        ),
    )
    assert result["data"] == {"courses": []}


def test_provider_result_count_and_boolean_ids_cannot_override_search_bounds(monkeypatch) -> None:
    monkeypatch.setattr("tum_mcp.studocu.client.studocu_enabled", lambda: True)
    courses = [{"course_id": True, "institution_id": 92}]
    courses += [{"course_id": n, "institution_id": 92} for n in range(1, 6)]
    response = {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"courses": courses}}}
    result = search(
        "search-courses",
        {"query": "graph", "institution_id": 92, "limit": 2},
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=response)),
    )
    assert result["data"]["courses"] == [
        {"course_id": 1, "institution_id": 92},
        {"course_id": 2, "institution_id": 92},
    ]


@pytest.mark.parametrize("response_id", [0, True, "1"])
def test_search_refuses_a_response_for_another_rpc_request(monkeypatch, response_id) -> None:
    monkeypatch.setattr("tum_mcp.studocu.client.studocu_enabled", lambda: True)
    response = {
        "jsonrpc": "2.0",
        "id": response_id,
        "result": {"structuredContent": {"courses": []}},
    }
    with pytest.raises(CampusError):
        search(
            "search-courses",
            {"query": "graph", "institution_id": 92},
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(200, content=json.dumps(response))
            ),
        )
