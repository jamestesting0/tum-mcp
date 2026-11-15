"""Released course exercises and revision-matched, visible student feedback."""

import hashlib
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
    StatementImage,
    Task,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.parsing import decode
from tum_mcp.transport import API

IMAGE_MAGIC = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "gif": b"GIF8",
    "webp": b"RIFF",
}
# At most this many statement images are fetched for one exercise.
MAX_IMAGES = 20


def tasks(statement: str) -> tuple[Task, ...]:
    """The `[task][name](tests)` lines of a programming statement; test markup is metadata."""
    found = []
    for name, tests in re.findall(r"\[task\]\[([^\]\n]{1,300})\]\(([^)\n]{0,2000})\)", statement):
        ids = [re.sub(r"</?testid>", "", test).strip() for test in tests.split(",") if test.strip()]
        found.append(Task(name=name.strip(), tests=tuple(ids)))
    return tuple(found)


def images(statement: str) -> list[tuple[str, str]]:
    """Same-origin images the statement embeds, in order and without repeats."""
    pattern = (
        r"!\[([^\]\n]{0,300})\]\("
        r"(/api/core/files/markdown/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}\.(?:png|jpe?g|gif|webp))"
        r"(?:\s+\"[^\"]*\")?\)"
    )
    seen: dict[str, str] = {}
    for alt, path in re.findall(pattern, statement):
        seen.setdefault(path, alt)
    return [(alt, path) for path, alt in list(seen.items())[:MAX_IMAGES]]


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
        statement = exercise.problem_statement or ""
        return ExerciseView(
            account_id=self.api.account.id,
            instance_id=self.api.account.origin,
            course_id=course_id,
            exercise=exercise,
            fetched_at=time.time(),
            source_link=f"{self.api.account.origin}/courses/{course_id}/exercises/{exercise_id}",
            tasks=tasks(statement),
            images=tuple(StatementImage(path=path, alt=alt) for alt, path in images(statement)),
        )

    def save_images(self, view: ExerciseView) -> ExerciseView:
        """Fetch each image the statement embeds and keep a local copy; a failed image is
        reported, never silently dropped."""
        from tum_mcp.course.project.store import confined, read_bytes
        from tum_mcp.moodle.config import private_write
        from tum_mcp.settings import data_dir

        saved = []
        for image in view.images:
            try:
                body = self.api.get_markdown_image(image.path)
            except CampusError as error:
                saved.append(image.model_copy(update={"problem": error.message}))
                continue
            extension = image.path.rsplit(".", 1)[1].lower().replace("jpeg", "jpg")
            if not body.startswith(IMAGE_MAGIC[extension]) or (
                extension == "webp" and body[8:12] != b"WEBP"
            ):
                saved.append(image.model_copy(update={"problem": "Not the image it names."}))
                continue
            digest = hashlib.sha256(body).hexdigest()
            relative = (
                f"downloads/artemis/{self.api.account.id}/course-{view.course_id}/"
                f"exercise-{view.exercise.id}/{digest}.{extension}"
            )
            target = confined(data_dir(), relative)
            if read_bytes(target) is None:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                private_write(target, body)
            saved.append(image.model_copy(update={"sha256": digest, "saved_path": str(target)}))
        return view.model_copy(update={"images": tuple(saved)})

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
