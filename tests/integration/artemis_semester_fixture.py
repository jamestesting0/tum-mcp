"""Synthetic active/archive courses served through the real read-only transport."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx2
import pytest
from material_fixture import pdf_bytes

from tum_mcp.credentials import Credential, Vault
from tum_mcp.moodle.auth import Cookie
from tum_mcp.settings import Account, Provider, save_account


@dataclass(slots=True)
class ArtemisSemesterSite:
    """Mutable server state exercises course availability and permission revocation."""

    account: Account
    active: bool = True
    past: bool = True
    archive_status: int = 200
    denied: set[int] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET" and request.url.host == "artemis.tum.de"
        path = request.url.path
        self.calls.append(path)
        if path == "/api/core/public/account":
            return httpx2.Response(200, json={"id": 7, "login": "synthetic"})
        if path == "/api/course/courses/for-dropdown":
            return httpx2.Response(
                200, json=[{"id": 20, "title": "Algorithms"}] if self.active else []
            )
        if path == "/api/course/courses/for-archive":
            courses = [
                {"id": 9, "title": "Algorithms", "semester": "WS2023/24", "staffOnly": "omit"},
                {"id": 10, "title": "Past summer", "semester": "SS2020"},
                {"id": 20, "title": "Stale duplicate", "semester": "WS2019/20"},
            ]
            return httpx2.Response(self.archive_status, json=courses if self.past else [])
        overview = re.fullmatch(r"/api/course/courses/(\d+)/exercises-for-overview", path)
        lectures = re.fullmatch(r"/api/lecture/courses/(\d+)/lectures-for-overview", path)
        exercise = re.fullmatch(r"/api/exercise/exercises/(\d+)/details", path)
        lecture = re.fullmatch(r"/api/lecture/lectures/(\d+)/details", path)
        student = re.fullmatch(
            r"/api/core/files/attachments/attachment-video-units/(\d+)/student/past.pdf", path
        )
        if overview or lectures:
            course_id = int((overview or lectures)[1])
        elif exercise or lecture:
            course_id = int((exercise or lecture)[1]) // 10
        elif student:
            course_id = int(student[1]) // 100
        else:
            raise AssertionError(f"Unexpected synthetic endpoint: {path}")
        if course_id in self.denied:
            return httpx2.Response(403)
        statement = {
            "id": course_id * 10 + 4,
            "type": "programming",
            "title": "Past exercise",
            "course": {"id": course_id, "endDate": "2021-01-01T00:00:00Z"},
            "releaseDate": "2020-01-01T00:00:00Z",
            "problemStatement": "Past semester statement.",
            "studentParticipations": [
                {"id": 1, "repositoryUri": "https://example.invalid/private"}
            ],
        }
        if overview:
            return httpx2.Response(
                200,
                json={
                    "exercises": [
                        statement,
                        {"id": 800, "type": "quiz", "title": "Quiz"},
                        {"id": 801, "type": "text", "title": "Exam", "exerciseGroup": {"id": 1}},
                        {
                            "id": 802,
                            "type": "text",
                            "title": "Future",
                            "releaseDate": "2999-01-01T00:00:00Z",
                        },
                    ]
                },
            )
        if exercise:
            return httpx2.Response(200, json={"exercise": statement})
        summary = {
            "id": course_id * 10 + 1,
            "title": "Past lecture",
            "startDate": "2020-01-01T00:00:00Z",
            "endDate": "2020-02-01T00:00:00Z",
        }
        if lectures:
            return httpx2.Response(200, json=[summary])
        if lecture:
            return httpx2.Response(
                200,
                json={
                    **summary,
                    "course": {"id": course_id},
                    "lectureUnits": [
                        {"id": 1, "type": "text", "content": "Past semester teaching."},
                        {
                            "id": course_id * 100 + 2,
                            "type": "attachment",
                            "attachment": {
                                "id": course_id * 100 + 3,
                                "name": "Past slides",
                                "link": "/api/core/files/staff-original.pdf",
                                "studentVersion": (
                                    "/api/core/files/attachments/attachment-video-units/"
                                    f"{course_id * 100 + 2}/student/past.pdf"
                                ),
                            },
                        },
                        {"id": 4, "type": "text", "content": "hidden", "visibleToStudents": False},
                        {
                            "id": 5,
                            "type": "text",
                            "content": "future",
                            "releaseDate": "2999-01-01T00:00:00Z",
                        },
                    ],
                },
            )
        return httpx2.Response(
            200,
            content=pdf_bytes(["Past semester student slides."]),
            headers={"Content-Type": "application/pdf"},
        )


@pytest.fixture
def artemis_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ArtemisSemesterSite:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    account = Account(
        provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7", courses=(20,)
    )
    save_account(account)
    Vault().save(
        account,
        Credential(
            account_id=account.id,
            cookies=(Cookie(name="session", value="synthetic", domain="artemis.tum.de"),),
        ),
    )
    site = ArtemisSemesterSite(account)
    monkeypatch.setattr(
        httpx2, "HTTPTransport", lambda **kwargs: httpx2.MockTransport(site.respond)
    )
    return site
