"""Artemis lecture reading, always using the student attachment variant."""

import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from tum_mcp.artemis.client import Artemis
from tum_mcp.artemis.lecture_models import (
    AttachmentView,
    Lecture,
    LectureDirectory,
    LectureList,
    LectureUnit,
    LectureView,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.errors import MoodleError
from tum_mcp.moodle.extract_worker import run_extraction
from tum_mcp.parsing import decode
from tum_mcp.settings import data_dir


def released(date: datetime | None) -> bool:
    return date is None or date <= datetime.now(UTC)


def readable(unit: LectureUnit) -> bool:
    if not unit.visible or not released(unit.release_date):
        return False
    if unit.attachment and not released(unit.attachment.release_date):
        return False
    if unit.exercise:
        exercise = unit.exercise
        return (
            exercise.type in {"programming", "text", "modeling", "file-upload"}
            and exercise.exercise_group is None
            and released(exercise.release_date)
        )
    return True


class Lectures:
    def __init__(self, artemis: Artemis) -> None:
        self.artemis = artemis
        self.api = artemis.api

    def directory(self, course_id: int) -> LectureDirectory:
        self.artemis.identity()
        lectures = decode(
            LectureList, self.api.get(f"/api/lecture/courses/{course_id}/lectures-for-overview")
        ).root
        return LectureDirectory(
            account_id=self.api.account.id,
            course_id=course_id,
            lectures=lectures,
            fetched_at=time.time(),
            source_link=f"{self.api.account.origin}/courses/{course_id}/lectures",
        )

    def lecture(self, course_id: int, lecture_id: int) -> LectureView:
        if not any(item.id == lecture_id for item in self.directory(course_id).lectures):
            raise CampusError(Code.SCOPE_DENIED, "Lecture does not belong to the selected course.")
        lecture = decode(Lecture, self.api.get(f"/api/lecture/lectures/{lecture_id}/details"))
        if lecture.id != lecture_id or lecture.course.id != course_id:
            raise CampusError(Code.SCOPE_DENIED, "Lecture identity or course changed.")
        supported = {"text", "online", "attachment", "video", "exercise"}
        units = tuple(
            unit.model_copy(
                update={
                    "exercise": unit.exercise.model_copy(update={"student_participations": None})
                    if unit.exercise
                    else None,
                }
            )
            for unit in lecture.units
            if unit.type in supported and readable(unit)
        )
        return LectureView(
            account_id=self.api.account.id,
            course_id=course_id,
            lecture=lecture.model_copy(
                update={
                    "units": units,
                    "attachments": tuple(
                        a for a in lecture.attachments if released(a.release_date)
                    ),
                }
            ),
            unsupported_units=tuple(
                sorted({u.type for u in lecture.units if u.type not in supported})
            ),
            fetched_at=time.time(),
            source_link=f"{self.api.account.origin}/courses/{course_id}/lectures/{lecture_id}",
        )

    def attachment(
        self,
        course_id: int,
        lecture_id: int,
        attachment_id: int,
        *,
        page_start: int = 1,
        page_limit: int = 8,
        save_original: bool = False,
    ) -> AttachmentView:
        if page_start < 1 or not 1 <= page_limit <= 12:
            raise CampusError(Code.ACTION_REQUIRED, "Use a positive page and a limit from 1 to 12.")
        view = self.lecture(course_id, lecture_id)
        matches = [
            u for u in view.lecture.units if u.attachment and u.attachment.id == attachment_id
        ]
        if len(matches) != 1:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "No unique readable attachment unit found."
            )
        unit = matches[0]
        attachment = unit.attachment
        if attachment is None:
            raise CampusError(Code.INVALID_RESPONSE, "Attachment metadata changed.")
        # Never fetch the staff/original link: the student endpoint removes hidden slides.
        supplied = urlsplit(attachment.student_version or attachment.link)
        if supplied.netloc and f"{supplied.scheme}://{supplied.netloc}" != self.api.account.origin:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED,
                "External attachment: use its cited website separately.",
            )
        filename = unquote(PurePosixPath(supplied.path).name)
        if not re.fullmatch(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,180}\.pdf", filename):
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Only supported student PDF attachments can be read."
            )
        path = f"/api/core/files/attachments/attachment-video-units/{unit.id}/student/{filename}"
        body = self.api.get_lecture_file(path)
        if not body.startswith(b"%PDF-"):
            raise CampusError(Code.INVALID_RESPONSE, "The student attachment is not a PDF.")
        digest = hashlib.sha256(body).hexdigest()
        try:
            extracted = run_extraction(body, "application/pdf")
        except MoodleError as error:
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, error.message) from None
        pages = []
        remaining = 40000
        for page in extracted.pages[page_start - 1 : page_start - 1 + page_limit]:
            text = page.text[:remaining]
            pages.append(page.model_copy(update={"text": text}))
            remaining -= len(text)
            if not remaining:
                break
        saved = None
        if save_original:
            from tum_mcp.study_store import confined, read_bytes

            relative = (
                f"downloads/artemis/{self.api.account.id}/course-{course_id}/"
                f"{attachment_id}-{digest}.pdf"
            )
            target = confined(data_dir(), relative)
            before = read_bytes(target)
            if before is not None and before != body:
                raise CampusError(Code.WORKSPACE_CONFLICT, "The edited student copy was preserved.")
            if before is None:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                private_write(target, body)
            saved = str(target)
        return AttachmentView(
            account_id=self.api.account.id,
            course_id=course_id,
            lecture_id=lecture_id,
            attachment_id=attachment_id,
            title=attachment.name,
            sha256=digest,
            total_pages=len(extracted.pages),
            pages=tuple(pages),
            truncated=page_start > 1
            or page_start - 1 + len(pages) < len(extracted.pages)
            or not remaining,
            saved_path=saved,
            warnings=tuple(extracted.warnings),
            fetched_at=time.time(),
            source_link=view.source_link + f"#attachment-{attachment_id}",
        )
