from pathlib import Path

import httpx2
import pytest

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.identity import account_for_subject
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.tumonline.study_service import StudyService


def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    account = account_for_subject("synthetic-student")
    policies = PolicyStore()
    policies.create(account.id)
    vault = Vault()
    vault.save(
        account,
        Credential(
            account_id=account.id,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic-cookie", domain="campus.tum.de"),),
        ),
    )
    return account, policies, vault


def test_study_service_projects_allowed_data_and_uses_verified_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    account, policies, vault = setup(tmp_path, monkeypatch)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.url.path)
        if request.method == "POST":
            return httpx2.Response(201, json={"accessToken": "synthetic-token"})
        if request.url.path.endswith("/desktop/profile"):
            return httpx2.Response(
                200,
                json={
                    "resource": [
                        {"content": {"desktopProfileLibDto": {"obfuscatedId": "synthetic-student"}}}
                    ]
                },
            )
        return httpx2.Response(
            200,
            json={
                "resource": [
                    {
                        "content": {
                            "CmStudyInfoDto": {
                                "studyId": 11,
                                "name": {"value": "Synthetic degree"},
                                "intendedDegree": {"value": "Bachelor"},
                                "myStudyLink": {
                                    "href": (
                                        "/tumonline/ee/rest/slc.cm.cs/student/"
                                        "myStudies/11/myCurriculumElements/22"
                                    )
                                },
                                "grade": "synthetic-secret-grade",
                            }
                        }
                    }
                ]
            },
        )

    service = StudyService(httpx2.MockTransport(handler))
    result = service.list(account.id)
    assert len(calls) == 3
    assert result[0].name == "Synthetic degree"
    assert "synthetic-secret-grade" not in result[0].model_dump_json()
    assert "synthetic-token" not in result[0].model_dump_json()


def test_denied_study_scope_prevents_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    account, policies, vault = setup(tmp_path, monkeypatch)
    policies.set_scope(account.id, Scope.STUDIES_COURSES, False)
    service = StudyService(httpx2.MockTransport(lambda _: pytest.fail("network called")))
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        service.list(account.id)
