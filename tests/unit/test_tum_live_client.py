import copy
import json

import httpx2
import pytest

from tum_mcp.credentials import Credential
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import Cookie
from tum_mcp.settings import TUM_LIVE, Account, Provider
from tum_mcp.transport import API
from tum_mcp.tum_live import TumLive
from tum_mcp.tum_live.wire import Watch

ACCOUNT = Account(provider=Provider.TUM_LIVE, origin=TUM_LIVE, principal="7")
STREAM = {
    "id": 11,
    "courseId": 2464,
    "start": "2026-10-14T10:00:00Z",
    "recording": True,
    "duration": 600,
    "name": "Lecture",
}
COURSE = {"id": 2464, "slug": "950943622", "name": "Selected course", "streams": [STREAM]}
WATCH = {
    "course": COURSE,
    "stream": STREAM,
    "views": [
        {
            "kind": "WATCH_VIEW_KIND_PRESENTATION",
            "playlistUrl": "https://media.example.invalid/vod.m3u8?jwt=synthetic-capability-value",
        }
    ],
    "silences": [{"start": 500, "end": 600}],
}


def client(routes: dict, visited: list[str]) -> TumLive:
    def respond(request: httpx2.Request) -> httpx2.Response:
        visited.append(request.url.path)
        assert "session=synthetic-session" in request.headers["cookie"]
        value = routes[request.url.path]
        return value if isinstance(value, httpx2.Response) else httpx2.Response(200, json=value)

    credential = Credential(
        account_id=ACCOUNT.id,
        authentication="browser_session",
        cookies=(Cookie(name="session", value="synthetic-session", domain="live.rbg.tum.de"),),
    )
    return TumLive(API(ACCOUNT, credential, httpx2.MockTransport(respond)))


def routes() -> dict:
    return {
        "/api/v2/users/me": {"user": {"id": 7, "email": "not-in-projection@example.invalid"}},
        "/api/v2/courses/950943622": {"course": COURSE},
        "/api/v2/streams/950943622/11/watch": WATCH,
        "/api/v2/courses/enrolled": {
            "courses": [
                {"id": 1, "slug": "a", "name": "One"},
                {"id": 2, "slug": "b", "name": "Two"},
            ]
        },
    }


def test_authenticated_recording_metadata_drops_capabilities_and_staff_fields() -> None:
    visited = []
    value = client(routes(), visited).recording("950943622", 11)
    assert value.course.id == 2464 and value.course.slug == "950943622"
    assert value.source_link == "https://live.rbg.tum.de/w/950943622/11"
    assert "jwt" not in value.model_dump_json()
    assert "synthetic-capability-value" not in value.model_dump_json()
    assert visited == [
        "/api/v2/users/me",
        "/api/v2/courses/950943622",
        "/api/v2/streams/950943622/11/watch",
    ]
    wire = Watch.model_validate(WATCH)
    assert "synthetic-capability-value" not in repr(wire)
    assert "synthetic-capability-value" not in wire.model_dump_json()


def test_course_page_is_bounded_and_rejects_changed_directory_cursor() -> None:
    mapping = routes()
    provider = client(mapping, [])
    first = provider.courses(limit=1)
    second = provider.courses(cursor=first.next_cursor, limit=1)
    assert [entry.id for entry in first.courses] == [1]
    assert [entry.id for entry in second.courses] == [2]
    assert second.next_cursor is None
    mapping["/api/v2/courses/enrolled"]["courses"][0]["name"] = "Changed"
    with pytest.raises(CampusError) as error:
        provider.courses(first.next_cursor, 1)
    assert error.value.code == Code.STALE_RESULT


def test_other_course_recording_is_rejected_before_watch_request() -> None:
    visited = []
    with pytest.raises(CampusError) as error:
        client(routes(), visited).recording("950943622", 99)
    assert error.value.code == Code.SCOPE_DENIED
    assert not any(path.endswith("/watch") for path in visited)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_redirect_or_denied_provider_never_exposes_response_capability(status: int) -> None:
    mapping = routes()
    mapping["/api/v2/users/me"] = httpx2.Response(
        status,
        headers={"Location": "https://other.invalid/?jwt=synthetic-capability-value"},
        content=b"synthetic-capability-value",
    )
    with pytest.raises(CampusError) as error:
        client(mapping, []).identity()
    assert "synthetic-capability-value" not in str(error.value)


def test_identity_switch_or_bad_payload_cannot_reuse_saved_session() -> None:
    mapping = routes()
    mapping["/api/v2/users/me"] = {"user": {"id": 99}}
    with pytest.raises(CampusError) as error:
        client(mapping, []).recording("950943622", 11)
    assert error.value.code == Code.SCOPE_DENIED
    mapping["/api/v2/users/me"] = {"user": {"id": "synthetic-capability-value"}}
    with pytest.raises(CampusError) as invalid:
        client(mapping, []).identity()
    assert "synthetic-capability-value" not in str(invalid.value)


@pytest.mark.parametrize(
    "slug", ["../users/me", "950943622?jwt=synthetic", "https://other.invalid/"]
)
def test_malformed_slug_cannot_expand_the_get_allowlist(slug: str) -> None:
    visited = []
    with pytest.raises(CampusError):
        client(routes(), visited).course(slug)
    assert visited == []


def test_wire_names_match_deployed_json_and_not_a_scheduled_duration() -> None:
    encoded = json.dumps(WATCH).encode()
    wire = Watch.model_validate_json(encoded)
    assert wire.stream.duration == 600
    assert wire.silences[0].start == 500


def test_whole_silence_returns_only_minimal_invalid_metadata_without_content_reads() -> None:
    mapping = routes()
    watch = copy.deepcopy(WATCH)
    watch["silences"] = [{"start": 0, "end": 600}]
    mapping["/api/v2/streams/950943622/11/watch"] = watch
    visited = []
    value = client(mapping, visited).recording("950943622", 11)
    assert value.validity == "invalid" and value.reason == "whole_recording_silence"
    assert (
        not {"views", "available_views", "subtitle_languages", "attachments"}
        & value.model_dump().keys()
    )
    assert visited == [
        "/api/v2/users/me",
        "/api/v2/courses/950943622",
        "/api/v2/streams/950943622/11/watch",
    ]


def test_offered_binary_file_has_its_own_budget_without_widening_json_reads() -> None:
    mapping = routes()
    watch = copy.deepcopy(WATCH)
    watch["views"][0]["sprite"] = {"fileId": 22, "intervalSeconds": 30}
    wire = Watch.model_validate(watch)
    body = b"x" * (5 * 1024 * 1024)
    mapping["/api/v2/streams/11/files/22"] = httpx2.Response(200, content=body)
    visited = []
    provider = client(mapping, visited)
    assert len(provider.file(wire, 22)) == len(body)
    assert visited == ["/api/v2/streams/11/files/22"]
    with pytest.raises(CampusError):
        provider.file(wire, 99)
    assert len(visited) == 1


def test_unknown_duration_file_guard_is_resolved_from_playlist_metadata_only() -> None:
    watch = copy.deepcopy(WATCH)
    watch["stream"] = STREAM | {"duration": None}
    watch["silences"] = [{"start": 0, "end": 600}]
    watch["views"][0]["sprite"] = {"fileId": 22, "intervalSeconds": 30}
    wire = Watch.model_validate(watch)
    visited = []
    provider = client(routes(), visited)
    with pytest.raises(CampusError, match="duration"):
        provider.file(wire, 22)
    with pytest.raises(CampusError, match="whole_recording_silence"):
        provider.file(wire, 22, duration_s=599.95)
    assert visited == []
