"""Synthetic Moodle transport with paginated enrollment and independent course access."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx2
import pytest
from keyring.backend import KeyringBackend

from tum_mcp.moodle import http_client
from tum_mcp.moodle.auth import Cookie, Session, SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.moodle.course_scope import current_term
from tum_mcp.moodle.models import Course


@dataclass(slots=True)
class MoodleSite:
    """Mutable server state lets tests revoke access without changing the local cache."""

    denied: set[int] = field(default_factory=set)

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "www.moodle.tum.de"
        path = request.url.path
        if path == "/my/courses.php":
            return httpx2.Response(
                200,
                text='<script>var config = {"sesskey": "synthetic-key"}</script>',
                headers={"Content-Type": "text/html"},
            )
        if path == "/lib/ajax/service.php":
            payload = json.loads(request.content)[0]
            assert payload["methodname"] == (
                "core_course_get_enrolled_courses_by_timeline_classification"
            )
            first = [
                Course(id=1, fullname="Past winter", shortname="W00/01", enddate=0),
                Course(id=2, fullname="Current", shortname=current_term()),
            ]
            second = [
                Course(id=3, fullname="Past summer", shortname="S01"),
                Course(id=4, fullname="Advising"),
                first[1],
            ]
            if payload["args"]["classification"] == "allincludinghidden":
                second.append(Course(id=6, fullname="Hidden past course", shortname="W00/01"))
            courses = first if payload["args"]["offset"] == 0 else second
            return httpx2.Response(
                200,
                json=[
                    {
                        "data": {
                            "courses": [course.model_dump() for course in courses],
                            "nextoffset": 2 if courses is first else 0,
                        }
                    }
                ],
            )
        if path == "/course/view.php":
            identity = int(request.url.params["id"])
            if identity in self.denied or identity == 90:
                return httpx2.Response(403)
            if identity == 91:
                html = '<body class="course-91"><div class="errorbox">Denied</div></body>'
            elif identity == 92:
                return httpx2.Response(302, headers={"Location": "/enrol/index.php?id=92"})
            else:
                displayed = 2 if identity == 93 else identity
                html = (
                    f'<body id="page-course-view-topics" class="course-{displayed}">'
                    '<div class="course-content"><li class="section">'
                    '<h3 class="sectionname">Lectures</h3><li class="activity">'
                    f'<a href="/mod/resource/view.php?id={displayed * 100}">'
                    '<span class="instancename">Past lecture</span></a></li>'
                    '<li class="activity" id="note"><div class="contentwithoutlink">'
                    "Inline past note</div></li></li></div></body>"
                )
            return httpx2.Response(200, text=html, headers={"Content-Type": "text/html"})
        if path == "/enrol/index.php":
            return httpx2.Response(
                200,
                text='<body class="course-92"><h1>Enrolment options</h1></body>',
                headers={"Content-Type": "text/html"},
            )
        if path == "/mod/resource/view.php":
            return httpx2.Response(
                200,
                content=b"Past semester lecture on scheduling.",
                headers={"Content-Type": "text/plain"},
            )
        raise AssertionError(f"Unexpected synthetic endpoint: {path}")


@pytest.fixture
def moodle_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_keyring: KeyringBackend
) -> MoodleSite:
    monkeypatch.setenv("TUM_MOODLE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TUM_MOODLE_SESSION_STORAGE", raising=False)
    store = SessionStore(Paths(tmp_path))
    store.save(
        Session(
            generation=store.begin_login(),
            verified_at=0,
            cookies=[Cookie(name="MoodleSession", value="synthetic", domain="www.moodle.tum.de")],
        )
    )
    site = MoodleSite()
    client_class = httpx2.Client
    monkeypatch.setattr(http_client, "public_address", lambda: None)
    monkeypatch.setattr(http_client.MoodleHTTP, "_rate_limit", lambda self: None)
    monkeypatch.setattr(
        httpx2,
        "Client",
        lambda **kwargs: client_class(transport=httpx2.MockTransport(site.respond), **kwargs),
    )
    return site
