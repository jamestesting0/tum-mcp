from pathlib import Path

import httpx2
import pytest

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.curriculum import PublicCurriculum
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope

ACCOUNT = "a" * 64


def wire_position(name: str) -> dict:
    return {
        "content": {
            "coCurriculumPositionDto": {
                "studyNameInfoDto": {
                    "name": {"value": "Program"},
                    "curriculumVersionIdentification": "2024",
                },
                "curriculumPositionPathDto": {"path": [{"name": {"value": name}}]},
                "grade": "synthetic-private-grade",
                "completed": True,
            }
        }
    }


@pytest.fixture
def policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PolicyStore:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    Vault().save(
        AccountRef(account_id=ACCOUNT),
        Credential(
            account_id=ACCOUNT,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic-secret", domain="campus.tum.de"),),
        ),
    )
    return policies


def test_public_curriculum_projects_only_structure_without_sending_credentials(
    policy: PolicyStore,
) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(
            200, json={"resource": [wire_position("Module A"), wire_position("Module B")]}
        )

    reader = PublicCurriculum(policy, httpx2.MockTransport(handler))
    first = reader.list(ACCOUNT, 42, offset=0, limit=1)
    assert len(calls) == 1 and calls[0].method == "GET"
    assert calls[0].url.host == "campus.tum.de"
    assert calls[0].url.path.endswith("/positions/42/course/allCurriculumPositions")
    assert "cookie" not in calls[0].headers and "authorization" not in calls[0].headers
    assert first.positions[0].path == ("Module A",)
    assert first.next_offset == 1 and first.coverage_status == "partial"
    assert "synthetic-private-grade" not in first.model_dump_json()
    assert "completed" not in first.model_dump_json()
    second = reader.list(ACCOUNT, 42, offset=1, limit=1)
    assert second.positions[0].path == ("Module B",) and second.next_offset is None


def test_denied_scope_prevents_curriculum_request(policy: PolicyStore) -> None:
    policy.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
    reader = PublicCurriculum(policy, httpx2.MockTransport(lambda _: pytest.fail("network called")))
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        reader.list(ACCOUNT, 42, offset=0, limit=20)


def test_revocation_during_request_discards_curriculum_result(policy: PolicyStore) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        policy.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
        return httpx2.Response(200, json={"resource": [wire_position("Module A")]})

    reader = PublicCurriculum(policy, httpx2.MockTransport(handler))
    with pytest.raises(CampusError, match="STALE_RESULT"):
        reader.list(ACCOUNT, 42, offset=0, limit=20)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_curriculum_rejects_failed_responses_and_redirects(
    policy: PolicyStore, status: int
) -> None:
    reader = PublicCurriculum(
        policy,
        httpx2.MockTransport(
            lambda _: httpx2.Response(
                status, text="private", headers={"Location": "https://example.invalid"}
            )
        ),
    )
    with pytest.raises(CampusError) as error:
        reader.list(ACCOUNT, 42, offset=0, limit=20)
    assert "private" not in str(error.value)


def test_response_byte_limit_preserves_a_continuation(policy: PolicyStore) -> None:
    long_name = "x" * 4000
    payload = {"resource": [wire_position(long_name) for _ in range(10)]}
    reader = PublicCurriculum(
        policy, httpx2.MockTransport(lambda _: httpx2.Response(200, json=payload))
    )
    first = reader.list(ACCOUNT, 42, offset=0, limit=10)
    assert 0 < len(first.positions) < 10
    assert first.next_offset == len(first.positions)
    assert len(first.model_dump_json().encode()) < 31_000


def test_schema_change_does_not_leak_raw_response(policy: PolicyStore) -> None:
    reader = PublicCurriculum(
        policy,
        httpx2.MockTransport(
            lambda _: httpx2.Response(200, json={"resource": [{"grade": "private"}]})
        ),
    )
    with pytest.raises(CampusError) as error:
        reader.list(ACCOUNT, 42, offset=0, limit=20)
    assert "private" not in str(error.value)
