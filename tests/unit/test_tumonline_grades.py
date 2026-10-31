import json
from pathlib import Path

import httpx2
import pytest

from tum_mcp.credentials import Credential, Vault
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.grades import project_achievements, read_progress
from tum_mcp.tumonline.identity import account_for_subject
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.tumonline.study_service import read_personal

PROFILE = {
    "resource": [{"content": {"desktopProfileLibDto": {"obfuscatedId": "synthetic-student"}}}]
}


def test_achievement_projection_keeps_grades_and_drops_identifiers() -> None:
    final = {
        "id": 901,
        "achievementType": "EXAM",
        "achievementStatusType": "FINAL",
        "cpCourseLibDto": {
            "id": 77,
            "courseTitle": {"value": "Synthetic Analysis"},
            "courseNumber": {"courseNumber": "IN0001"},
        },
        "semesterLibDto": {"shortName": {"value": "2025 W"}},
        "achievementDate": {"value": "2026-02-14T00:00:00"},
        "gradeDto": {"nameShort": "1,3", "name": {"value": "sehr gut"}, "isPositive": True},
        "credits": 6,
        "studyBasicInfoLibDto": {
            "studyIdentifier": "synthetic-private-matriculation",
            "studyName": {"value": "Synthetic Informatics"},
        },
        "gradeComment": "synthetic-private-comment",
        "information": "synthetic-private-information",
    }
    in_progress = {
        "achievementType": "FINAL_THESIS",
        "achievementStatusType": "IN_PROGRESS",
        "cpCourseLibDto": {"courseTitle": {"value": "Synthetic thesis"}},
        "gradeDto": {"nameShort": "-"},
    }
    body = json.dumps(
        {
            "resource": [
                {
                    "link": [{"href": "https://example.invalid/private"}],
                    "content": {"achievementDto": item},
                }
                for item in (final, in_progress)
            ]
        }
    ).encode()
    first, second = project_achievements(body)
    assert (first.title, first.course_number, first.semester, first.date) == (
        "Synthetic Analysis",
        "IN0001",
        "2025 W",
        "2026-02-14",
    )
    assert (first.grade, first.passed, first.credits, first.study) == (
        "1,3",
        True,
        6,
        "Synthetic Informatics",
    )
    assert (second.status, second.semester, second.date, second.credits) == (
        "IN_PROGRESS",
        None,
        None,
        None,
    )
    encoded = first.model_dump_json() + second.model_dump_json()
    assert "synthetic-private" not in encoded and "example.invalid" not in encoded


def test_progress_reads_both_bars_for_every_study_with_the_verified_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    account = account_for_subject("synthetic-student")
    PolicyStore().create(account.id)
    PolicyStore().set_scope(account.id, Scope.ACADEMIC_PROGRESS, True)
    Vault().save(
        account,
        Credential(
            account_id=account.id,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic-cookie", domain="campus.tum.de"),),
        ),
    )
    requests = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx2.Response(201, json={"accessToken": "synthetic-token"})
        if request.url.path.endswith("/desktop/profile"):
            return httpx2.Response(200, json=PROFILE)
        if request.url.path.endswith("/chooser"):
            study = {"name": {"value": "Synthetic degree"}, "intendedDegree": {"value": "MSc"}}
            return httpx2.Response(
                200,
                json={"resource": [{"content": {"CmStudyInfoDto": {"studyId": 11, **study}}}]},
            )
        share = 0.5 if request.url.path.endswith("/modules") else 0.25
        return httpx2.Response(
            200,
            json={"barElements": [{"progress": share, "tooltip": {"value": "In progress"}}]},
        )

    (progress,) = read_personal(
        account.id, Scope.ACADEMIC_PROGRESS, read_progress, httpx2.MockTransport(handler)
    )
    assert (progress.study, progress.degree) == ("Synthetic degree", "MSc")
    assert [(part.state, part.share) for part in progress.modules] == [("In progress", 0.5)]
    assert [part.share for part in progress.exams] == [0.25]
    bars = [request for request in requests if "/progressBar/" in request.url.path]
    assert [request.url.path.rsplit("/", 3)[1:] for request in bars] == [
        ["11", "progressBar", "modules"],
        ["11", "progressBar", "exams"],
    ]
    assert all(request.headers["authorization"] == "Bearer synthetic-token" for request in bars)
