import json
from pathlib import Path

import httpx2
import pytest

from tum_mcp.artemis import Artemis
from tum_mcp.course.sources.repository import listing, read_snapshot, select, write_snapshot
from tum_mcp.credentials import Credential
from tum_mcp.errors import CampusError
from tum_mcp.settings import Account, Provider
from tum_mcp.transport import API

TEMPLATE, WORK = "a" * 40, "b" * 40
FILES = {
    TEMPLATE: {
        "src/Idle.java": "class Idle {\n    // TODO\n}\n",
        "src/State.java": "abstract class State {}\n",
        "build.gradle": "repositories { maven { url 'https://user:secret@example.org' } }",
        "gradle/wrapper/gradle-wrapper.properties": "distributionUrl=x",
        ".vscode/settings.json": "{}",
        ".gitignore": "build/",
    },
    WORK: {"src/Idle.java": "class Idle { solved(); }\n"},
}


def provider(participations: list[dict]) -> tuple[Artemis, list[str]]:
    seen: list[str] = []
    exercise = {
        "id": 11,
        "title": "State",
        "type": "programming",
        "course": {"id": 77},
        "releaseDate": "2020-01-01T00:00:00Z",
        "studentParticipations": participations,
    }
    routes = {
        "/api/core/public/account": {"id": 7, "login": "student"},
        "/api/course/courses/77/exercises-for-overview": {"exercises": [exercise]},
        "/api/exercise/exercises/11/details": {"exercise": exercise},
        "/api/programming/programming-exercise-participations/9/commit-history": [
            {"hash": WORK, "timestamp": "2026-11-02T10:00:00Z", "author": "me"},
            {"hash": TEMPLATE, "timestamp": "2026-10-01T10:00:00Z", "author": "staff"},
        ],
    }
    for item in participations:
        routes[
            f"/api/programming/programming-exercise-participations/{item['id']}/"
            "student-participation-with-all-results"
        ] = item | {"initializationDate": "2026-11-01T09:00:00Z"}

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        seen.append(str(request.url))
        if request.url.path.endswith("/files-content-commit-details"):
            return httpx2.Response(200, json=FILES[request.url.params["commitId"]])
        return httpx2.Response(200, json=routes[request.url.path])

    account = Account(provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7")
    api = API(account, Credential(account_id=account.id), httpx2.MockTransport(handler))
    return Artemis(api), seen


def test_the_template_is_the_commit_artemis_copied_not_the_students_work() -> None:
    artemis, seen = provider([{"id": 9, "testRun": False}])
    commit, files = artemis.template_files(artemis.exercise(77, 11).exercise)
    assert commit == TEMPLATE
    assert files["src/Idle.java"].endswith("// TODO\n}\n")
    assert all("participationId=9" in url for url in seen if "files-content" in url)


def test_an_unstarted_exercise_is_never_started() -> None:
    artemis, seen = provider([])
    with pytest.raises(CampusError, match="not_started"):
        artemis.template_files(artemis.exercise(77, 11).exercise)
    assert not any("programming" in url for url in seen)


def test_the_snapshot_keeps_sources_and_never_lists_their_text(tmp_path: Path) -> None:
    kept, dropped = select(FILES[TEMPLATE])
    assert sorted(kept) == ["src/Idle.java", "src/State.java"]
    assert {item.path for item in dropped} == set(FILES[TEMPLATE]) - set(kept)
    manifest = write_snapshot(tmp_path / "snap", "artemis-11", TEMPLATE, FILES[TEMPLATE])
    assert not (tmp_path / "snap/files/build.gradle").exists()
    shown = json.dumps(listing(*read_snapshot(tmp_path / "snap")))
    assert "secret" not in shown and "TODO" not in shown.replace('"todo"', "")
    assert manifest.files["src/Idle.java"] in shown
    (tmp_path / "snap/files/src/Idle.java").write_text("changed")
    with pytest.raises(CampusError, match="changed"):
        read_snapshot(tmp_path / "snap")


def test_a_repository_beyond_the_editor_is_narrowed_with_include() -> None:
    big = {f"src/F{n}.java": "class F {}\n" for n in range(70)}
    with pytest.raises(CampusError, match="--include"):
        select(big)
    kept, _ = select(big, ("src/F1*.java",))
    assert len(kept) == 11
