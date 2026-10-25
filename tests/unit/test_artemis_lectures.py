from pathlib import Path

import httpx2
import pytest

from tum_mcp.artemis import Artemis
from tum_mcp.credentials import Credential
from tum_mcp.errors import CampusError
from tum_mcp.lectures import Lectures
from tum_mcp.settings import Account, Provider
from tum_mcp.transport import API
from tum_moodle.models import Extracted, TextPage


@pytest.fixture
def lecture_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path))
    account = Account(
        provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7", courses=(9,)
    )
    attachment = {
        "id": 14,
        "name": "Student slides",
        "link": "/api/core/files/staff-original.pdf",
        "studentVersion": (
            "/api/core/files/attachments/attachment-video-units/12/student/student-slides.pdf"
        ),
    }
    lecture = {
        "id": 11,
        "title": "Lecture",
        "course": {"id": 9},
        "lectureUnits": [
            {
                "id": 12,
                "type": "attachment",
                "name": "Slides",
                "attachment": attachment,
                "completed": True,
            },
            {"id": 13, "type": "text", "name": "Definition", "content": "A precise definition."},
            {"id": 15, "type": "online", "source": "https://example.invalid/reading"},
            {
                "id": 16,
                "type": "text",
                "content": "hidden-future",
                "releaseDate": "2999-01-01T00:00:00Z",
            },
            {"id": 17, "type": "text", "content": "hidden-unit", "visibleToStudents": False},
            {"id": 18, "type": "exercise", "exercise": {"id": 21, "type": "quiz", "title": "Quiz"}},
            {"id": 19, "type": "new-type", "staffSecret": "staff-only"},
        ],
    }
    calls = []

    def request(req):
        calls.append((req.method, req.url.path))
        if "/student/" in req.url.path:
            assert (
                req.url.path == "/api/core/files/attachments/attachment-video-units/12/student/"
                "student-slides.pdf"
            )
            return httpx2.Response(200, content=b"%PDF-synthetic")
        routes = {
            "/api/core/public/account": {"id": 7, "login": "synthetic"},
            "/api/lecture/courses/9/lectures-for-overview": [
                {"id": 11, "title": "Lecture", "isTutorialLecture": True}
            ],
            "/api/lecture/lectures/11/details": lecture,
        }
        return httpx2.Response(200, json=routes[req.url.path])

    api = API(account, Credential(account_id=account.id), httpx2.MockTransport(request))
    monkeypatch.setattr(
        "tum_mcp.lectures.run_extraction",
        lambda body, mime: Extracted(
            pages=[TextPage(number=i, text=f"Page {i}") for i in range(1, 21)]
        ),
    )
    return Lectures(Artemis(api)), lecture, calls


def test_teaching_content_is_preserved_without_completion_or_hidden_units(lecture_api):
    provider, _, calls = lecture_api
    assert provider.directory(9).lectures[0].tutorial
    result = provider.lecture(9, 11)
    assert {u.id for u in result.lecture.units} == {12, 13, 15}
    assert result.lecture.units[1].content == "A precise definition."
    assert result.unsupported_units == ("new-type",)
    encoded = result.model_dump_json()
    assert all(
        word not in encoded
        for word in ("completed", "hidden-future", "hidden-unit", "staff-only", "staff-original")
    )
    assert all(method == "GET" for method, _ in calls)


def test_course_scope_is_checked_before_any_http(lecture_api):
    provider, _, calls = lecture_api
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        provider.lecture(99, 11)
    assert calls == []


def test_lecture_must_belong_to_selected_course_before_details_request(lecture_api):
    provider, _, calls = lecture_api
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        provider.lecture(9, 999)
    assert not any(path.endswith("/999/details") for _, path in calls)


def test_changed_course_in_details_is_rejected(lecture_api):
    provider, lecture, _ = lecture_api
    lecture["course"] = {"id": 99}
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        provider.lecture(9, 11)


def test_student_pdf_is_paged_and_saved_only_when_requested(lecture_api, tmp_path):
    provider, _, calls = lecture_api
    page = provider.attachment(9, 11, 14, page_start=3, page_limit=2)
    assert [p.number for p in page.pages] == [3, 4]
    assert page.total_pages == 20 and page.truncated and page.saved_path is None
    assert not (tmp_path / "downloads").exists()
    saved = provider.attachment(9, 11, 14, save_original=True)
    assert Path(saved.saved_path).read_bytes() == b"%PDF-synthetic"
    assert all(method == "GET" for method, _ in calls)
    assert not any("staff-original" in path for _, path in calls)


def test_external_attachment_never_receives_campus_cookies(lecture_api):
    provider, lecture, calls = lecture_api
    lecture["lectureUnits"][0]["attachment"]["studentVersion"] = "https://other.invalid/private.pdf"
    with pytest.raises(CampusError, match="CAPABILITY_UNSUPPORTED"):
        provider.attachment(9, 11, 14)
    assert not any("/student/" in path for _, path in calls)


def test_future_attachment_is_not_downloadable(lecture_api):
    provider, lecture, calls = lecture_api
    lecture["lectureUnits"][0]["attachment"]["releaseDate"] = "2999-01-01T00:00:00Z"
    with pytest.raises(CampusError):
        provider.attachment(9, 11, 14)
    assert not any("/student/" in path for _, path in calls)


def test_file_transport_rejects_original_and_cross_origin_paths_before_credentials():
    account = Account(provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7")
    for path in (
        "https://other.invalid/private.pdf",
        "/api/core/files/attachments/attachment-video-units/12/original.pdf",
        "/api/core/files/attachments/lectures/11/original.pdf",
    ):
        with pytest.raises(CampusError, match="SCOPE_DENIED"):
            API(account).get_lecture_file(path)
