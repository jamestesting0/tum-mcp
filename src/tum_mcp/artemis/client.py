"""Released course exercises and revision-matched, visible student feedback."""

import re
import time
from datetime import UTC, datetime
from typing import Literal

from tum_mcp.artemis.models import (
    Courses,
    Details,
    Exercise,
    ExerciseView,
    Feedbacks,
    FeedbackView,
    Identity,
    Overview,
    Participation,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.parsing import decode
from tum_mcp.transport import API


class Artemis:
    def __init__(self, api: API) -> None:
        self.api = api

    def identity(self) -> Identity:
        identity = decode(Identity, self.api.get("/api/core/public/account"))
        if str(identity.id) != self.api.account.principal:
            raise CampusError(Code.SCOPE_DENIED, "Artemis identity changed; reconnect.")
        return identity

    def courses(self, include_past: bool = False) -> Courses:
        self.identity()
        active = decode(Courses, self.api.get("/api/course/courses/for-dropdown"))
        courses = {item.id: item.model_copy(update={"active": True}) for item in active.root}
        if include_past:
            past = decode(Courses, self.api.get("/api/course/courses/for-archive"))
            for item in past.root:
                if item.id not in courses:
                    courses[item.id] = item.model_copy(update={"active": False})
        return Courses(tuple(courses.values()))

    def exercises(self, course_id: int) -> Overview:
        self.identity()
        overview = decode(
            Overview, self.api.get(f"/api/course/courses/{course_id}/exercises-for-overview")
        )
        return overview.model_copy(
            update={
                "exercises": tuple(
                    item.model_copy(
                        update={"student_participations": None, "problem_statement": None}
                    )
                    for item in overview.exercises
                    if item.type in {"programming", "text", "modeling", "file-upload"}
                    and item.exercise_group is None
                    and (item.release_date is None or item.release_date <= datetime.now(UTC))
                )
            }
        )

    def exercise(self, course_id: int, exercise_id: int) -> ExerciseView:
        if not any(item.id == exercise_id for item in self.exercises(course_id).exercises):
            raise CampusError(
                Code.SCOPE_DENIED, "Exercise is not a readable released exercise in this course."
            )
        exercise = decode(
            Details, self.api.get(f"/api/exercise/exercises/{exercise_id}/details")
        ).exercise
        if (
            exercise.id != exercise_id
            or exercise.type not in {"programming", "text", "modeling", "file-upload"}
            or exercise.course is None
            or exercise.course.id != course_id
            or exercise.exercise_group is not None
            or (exercise.release_date is not None and exercise.release_date > datetime.now(UTC))
        ):
            raise CampusError(Code.SCOPE_DENIED, "Exercise identity, course, or release changed.")
        return ExerciseView(
            account_id=self.api.account.id,
            instance_id=self.api.account.origin,
            course_id=course_id,
            exercise=exercise,
            fetched_at=time.time(),
            source_link=f"{self.api.account.origin}/courses/{course_id}/exercises/{exercise_id}",
        )

    def participation(
        self, exercise: Exercise, mode: Literal["graded", "practice"]
    ) -> Participation:
        matches = [
            item
            for item in exercise.student_participations or ()
            if item.test_run == (mode == "practice")
        ]
        if not matches:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Feedback is unavailable without an existing matching participation.",
            )
        if len(matches) != 1:
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Participation identity is ambiguous.")
        return matches[0]

    def feedback(
        self, exercise: Exercise, mode: Literal["graded", "practice"], commit: str
    ) -> FeedbackView:
        if exercise.type != "programming":
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED,
                "Commit-linked feedback applies to programming exercises only.",
            )
        if not re.fullmatch(r"[a-fA-F0-9]{40}", commit):
            raise CampusError(Code.STALE_RESULT, "A full built commit hash is required.")
        participation = self.participation(exercise, mode)
        current = decode(
            Participation,
            self.api.get(
                f"/api/programming/programming-exercise-participations/{participation.id}/"
                "student-participation-with-all-results"
            ),
        )
        if (
            current.id != participation.id
            or current.test_run != participation.test_run
            or current.exercise is None
            or current.exercise.id != exercise.id
        ):
            raise CampusError(
                Code.STALE_RESULT, "Result participation does not match this exercise/mode."
            )
        submissions = [item for item in current.submissions or () if item.commit_hash == commit]
        if not submissions:
            raise CampusError(
                Code.STALE_RESULT, "No visible submission matches this exact revision."
            )
        if len(submissions) != 1:
            raise CampusError(Code.STALE_RESULT, "Revision-to-submission linkage is ambiguous.")
        submission = submissions[0]
        results = submission.results or ()
        details = []
        withheld = False
        for result in results:
            if result.feedbacks is None:
                try:
                    feedbacks = decode(
                        Feedbacks,
                        self.api.get(
                            f"/api/assessment/participations/{current.id}/results/{result.id}/details"
                        ),
                    ).root
                    result = result.model_copy(update={"feedbacks": feedbacks})
                except CampusError as error:
                    if error.code not in {Code.AUTH_REQUIRED, Code.CAPABILITY_UNSUPPORTED}:
                        raise
                    withheld = True
            details.append(result)
        results = tuple(details)
        state = (
            "completed"
            if results and all(item.completion_date for item in results)
            else "pending_or_withheld"
        )
        if submission.build_failed:
            state = "compilation_error"
        return FeedbackView(
            account_id=self.api.account.id,
            participation_id=current.id,
            commit_hash=commit,
            submission_id=submission.id,
            state=state,
            results=results,
            fetched_at=time.time(),
            limitations=("Only student-visible results; hidden tests remain unknown.",)
            + (("Detailed feedback is withheld or unsupported.",) if withheld else ()),
        )
