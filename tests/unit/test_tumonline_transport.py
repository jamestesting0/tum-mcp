from pathlib import Path

import httpx2
import pytest

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.tumonline.transport import PublicCourses

ACCOUNT = "a" * 64


@pytest.fixture(autouse=True)
def synthetic_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    account = AccountRef(account_id=ACCOUNT)
    Vault().save(
        account,
        Credential(
            account_id=ACCOUNT,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic", domain="campus.tum.de"),),
        ),
    )


def payload() -> dict:
    return {
        "totalCount": 1,
        "courses": [
            {
                "id": 123,
                "courseNumber": {"databaseValue": "IN1"},
                "courseTitle": {"value": "Synthetic course"},
                "semesterDto": {"semesterDesignation": {"value": "2026 W"}},
                "courseTypeDto": {"courseTypeShortName": {"value": "VO"}},
                "grade": "private-grade",
            }
        ],
    }


def test_public_course_read_checks_scope_and_projects_response(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    requests = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=payload())

    client = PublicCourses(policies, httpx2.MockTransport(handler))
    result = client.list(ACCOUNT, offset=0, limit=20)
    assert len(requests) == 1
    assert requests[0].url.host == "campus.tum.de"
    assert requests[0].method == "GET"
    assert requests[0].url.params["$top"] == "20"
    assert result.courses[0].title == "Synthetic course"
    assert "private-grade" not in result.model_dump_json()
    assert result.coverage_status == "complete"


def test_denied_scope_makes_no_request(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
    client = PublicCourses(
        policies, httpx2.MockTransport(lambda _: pytest.fail("network must not be contacted"))
    )
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        client.list(ACCOUNT, offset=0, limit=20)


def test_revocation_during_request_rejects_response(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)

    def handler(request: httpx2.Request) -> httpx2.Response:
        policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
        return httpx2.Response(200, json=payload())

    client = PublicCourses(policies, httpx2.MockTransport(handler))
    with pytest.raises(CampusError, match="STALE_RESULT"):
        client.list(ACCOUNT, offset=0, limit=20)


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_failed_responses_never_return_body(tmp_path: Path, status: int) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    client = PublicCourses(
        policies,
        httpx2.MockTransport(
            lambda _: httpx2.Response(
                status, headers={"Location": "https://example.invalid"}, content=b"private-body"
            )
        ),
    )
    with pytest.raises(CampusError) as raised:
        client.list(ACCOUNT, offset=0, limit=20)
    assert "private-body" not in str(raised.value)


def test_invalid_response_is_rejected_without_echoing_data(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    client = PublicCourses(
        policies, httpx2.MockTransport(lambda _: httpx2.Response(200, content=b"private-body"))
    )
    with pytest.raises(CampusError) as raised:
        client.list(ACCOUNT, offset=0, limit=20)
    assert "private-body" not in str(raised.value)


def test_oversized_response_and_invalid_bounds_fail_safely(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))

    client = PublicCourses(policies, httpx2.MockTransport(handler))
    with pytest.raises(CampusError):
        client.list(ACCOUNT, offset=-1, limit=20)
    assert calls == []
    with pytest.raises(CampusError, match="too large"):
        client.list(ACCOUNT, offset=0, limit=20)
    assert "authorization" not in calls[0].headers
    assert "cookie" not in calls[0].headers


def test_disconnected_account_is_denied_before_network(tmp_path: Path) -> None:
    policies = PolicyStore(tmp_path / "policies")
    policies.create(ACCOUNT)
    vault = Vault(tmp_path / "vault")
    transport = httpx2.MockTransport(lambda _: pytest.fail("network must not be contacted"))
    client = PublicCourses(policies, transport, vault=vault)
    with pytest.raises(CampusError, match="AUTH_REQUIRED"):
        client.list(ACCOUNT, offset=0, limit=20)


@pytest.mark.parametrize("query", ["Mathematik", "C++", "A/B"])
def test_search_is_sent_to_upstream_filter_without_credentials(tmp_path: Path, query: str) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=payload())

    result = PublicCourses(policies, httpx2.MockTransport(handler)).list(
        ACCOUNT, offset=0, limit=20, query=query
    )
    assert result.courses[0].title == "Synthetic course"
    assert seen[0].url.params["$filter"] == "filterTerm-like=" + query
    assert "authorization" not in seen[0].headers and "cookie" not in seen[0].headers


@pytest.mark.parametrize("query", ["x", "a;termId-eq=999", "a=b", " ", "x" * 81])
def test_invalid_search_fails_before_network(tmp_path: Path, query: str) -> None:
    policies = PolicyStore(tmp_path)
    policies.create(ACCOUNT)
    reader = PublicCourses(
        policies, httpx2.MockTransport(lambda _: pytest.fail("network must not be contacted"))
    )
    with pytest.raises(CampusError):
        reader.list(ACCOUNT, offset=0, limit=20, query=query)
