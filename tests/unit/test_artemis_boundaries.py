from pathlib import Path

import httpx2
import pytest

from tum_mcp import workspace
from tum_mcp.artemis import Artemis
from tum_mcp.credentials import Credential
from tum_mcp.errors import CampusError
from tum_mcp.settings import Account, Preferences, Provider
from tum_mcp.transport import API

COMMIT = "a" * 40


def provider(
    *, sensitive: bool = True, wrong_course: bool = False, workspace_enabled: bool = True
) -> Artemis:
    account = Account(
        provider=Provider.ARTEMIS,
        origin="https://artemis.tum.de",
        principal="7",
        courses=(77,),
        sensitive_reads=sensitive,
        workspace_writes=workspace_enabled,
    )
    participation = {
        "id": 9,
        "testRun": False,
        "repositoryUri": "https://student:never-show-this@artemis.tum.de/git/course/student.git",
        "branch": "main",
        "exercise": {"id": 11},
        "submissions": [
            {
                "id": 8,
                "commitHash": COMMIT,
                "results": [
                    {
                        "id": 6,
                        "completionDate": "2020-01-01T00:00:00Z",
                        "successful": False,
                        "score": 50,
                    }
                ],
            }
        ],
    }
    exercise = {
        "id": 11,
        "title": "Assignment",
        "type": "programming",
        "course": {"id": 88 if wrong_course else 77},
        "releaseDate": "2020-01-01T00:00:00Z",
        "allowOfflineIde": True,
        "problemStatement": "Do the exercise.",
        "studentParticipations": [participation],
    }

    routes = {
        "/api/core/public/account": {"id": 7, "login": "student"},
        "/api/course/courses/77/exercises-for-overview": {
            "exercises": [exercise, {"id": 12, "title": "Exam", "type": "quiz"}],
        },
        "/api/exercise/exercises/11/details": {"exercise": exercise},
        "/api/assessment/participations/9/results/6/details": [
            {
                "id": 51,
                "text": "test_core",
                "detailText": "Expected 2, received 1",
                "positive": False,
            },
        ],
        "/api/programming/programming-exercise-participations/9/"
        "student-participation-with-all-results": participation,
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert request.url.path in routes
        return httpx2.Response(200, json=routes[request.url.path])

    return Artemis(API(account, Credential(account_id=account.id), httpx2.MockTransport(handler)))


def test_feedback_matches_exact_revision_and_mode() -> None:
    # Given a visible completed result for one precise participation/revision.
    artemis = provider()
    exercise = artemis.exercise(77, 11).exercise
    # When that revision is requested.
    result = artemis.feedback(exercise, "graded", COMMIT)
    # Then the visible failing result is returned, without exposing repository credentials.
    assert result.participation_id == 9
    assert result.submission_id == 8
    assert result.results[0].score == 50
    assert result.results[0].successful is False
    assert result.results[0].feedbacks[0].positive is False
    assert result.state == "completed"
    assert "never-show-this" not in exercise.model_dump_json()


def test_feedback_rejects_a_different_commit() -> None:
    # Given server feedback for a previous revision.
    artemis = provider()
    exercise = artemis.exercise(77, 11).exercise
    # When a new commit is requested, then it cannot inherit an old result.
    with pytest.raises(CampusError, match="STALE_RESULT"):
        artemis.feedback(exercise, "graded", "b" * 40)


def test_practice_does_not_reuse_graded_participation() -> None:
    # Given an existing graded participation but no practice participation.
    artemis = provider()
    exercise = artemis.exercise(77, 11).exercise
    # When practice is requested, then no hidden start or mode switch occurs.
    with pytest.raises(CampusError, match="ACTION_REQUIRED"):
        artemis.feedback(exercise, "practice", COMMIT)


def test_course_listing_omits_sensitive_records_and_assessments() -> None:
    # Given a course response containing participation data and a quiz.
    artemis = provider(sensitive=False)
    # When released programming exercises are listed.
    result = artemis.exercises(77)
    # Then the public projection excludes both private records and assessments.
    assert [item.id for item in result.exercises] == [11]
    assert result.exercises[0].student_participations is None
    assert result.exercises[0].problem_statement is None
    assert artemis.exercise(77, 11).exercise.student_participations is None


def test_cross_course_exercise_response_is_rejected() -> None:
    # Given a provider response that changes the exercise's course identity.
    artemis = provider(wrong_course=True)
    # When details are retrieved, then no cross-course content is returned.
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        artemis.exercise(77, 11)


def test_existing_unrelated_workspace_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given unrelated work already occupying the requested preparation path.
    artemis = provider()
    monkeypatch.setattr(workspace, "preferences", lambda: Preferences(workspace_root=tmp_path))
    existing = tmp_path / "course-77/exercise-11-graded"
    existing.mkdir(parents=True)
    note = existing / "notes.txt"
    note.write_text("Keep my work")
    # When preparation is requested, then it stops before credentials/network cloning.
    with pytest.raises(CampusError, match="WORKSPACE_CONFLICT"):
        workspace.prepare(artemis, artemis.exercise(77, 11), "graded")
    assert note.read_text() == "Keep my work"


def test_unselected_course_is_denied_before_credentials() -> None:
    # Given no configured read grant for a course.
    account = Account(provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7")
    # When a direct provider call bypasses skill instructions, then it still fails closed.
    with pytest.raises(CampusError, match="SCOPE_DENIED"):
        Artemis(API(account)).exercises(77)


def test_read_grants_do_not_authorize_workspace_creation() -> None:
    # Given a read-enabled account without the separate workspace capability.
    artemis = provider(workspace_enabled=False)
    # When direct tool-style preparation bypasses a skill, then no local write occurs.
    with pytest.raises(CampusError, match="ACTION_REQUIRED"):
        workspace.prepare(artemis, artemis.exercise(77, 11), "graded")
