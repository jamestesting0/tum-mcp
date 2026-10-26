"""Source-bound lecture projection and explicit preparation freshness checks."""

from pathlib import Path

from pydantic import JsonValue, ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_content import LectureContent
from tum_mcp.lecture_figures import verify_figures
from tum_mcp.lecture_processing.receipts import (
    InvalidReceipt,
    read_receipt,
    source_text,
    usable_receipt,
)
from tum_mcp.lecture_processing.timeline import watch_link
from tum_mcp.study_content import render_blocks
from tum_mcp.study_models import StudyState
from tum_mcp.study_store import confined, digest


def read_lectures(root: Path) -> LectureContent | None:
    path = app_path(root, "lectures.json")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 8 * 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Lecture notes must be a file below 8 MiB.")
    try:
        return LectureContent.model_validate_json(path.read_bytes())
    except ValidationError as error:
        locations = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)]
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Invalid lecture notes at: "
            + ", ".join(locations[:5])
            + ". See study schema lectures.",
        ) from None


def stale_lectures(root: Path, state: StudyState, content: LectureContent) -> tuple[str, ...]:
    if state.course.key != content.course_key:
        raise CampusError(Code.SCOPE_DENIED, "Lecture notes belong to a different course.")
    resources = {item.resource.key: item for item in state.resources}
    bindings = {item.key: item for item in state.course.bindings}
    evidence = {item.key: item for item in content.evidence}
    stale: set[str] = set()
    for lecture in content.lectures:
        if lecture.recording.synthetic != state.course.synthetic:
            raise CampusError(
                Code.SCOPE_DENIED,
                "Synthetic lecture evidence cannot be mixed with real course notes.",
            )
        for source in lecture.sources:
            stored = resources.get(source.key)
            if (
                stored is None
                or stored.status != "current"
                or stored.sha256 != source.sha256
                or not stored.path
            ):
                stale.add(lecture.key)
                continue
            path = confined(root, stored.path)
            if not path.is_file() or digest(path.read_bytes()) != source.sha256:
                stale.add(lecture.key)
        primary = {
            evidence[key].source_key
            for section in lecture.sections
            for key in section.evidence
            if evidence[key].kind != "document"
        }
        for key in primary:
            stored = resources.get(key)
            if stored is None:
                stale.add(lecture.key)
                continue
            binding = bindings[stored.resource.binding]
            if not lecture.recording.synthetic and (
                binding.provider != "tum_live"
                or binding.course_id != str(lecture.recording.course_id)
                or binding.course_slug != lecture.recording.course_slug
                or stored.resource.url != watch_link(lecture.recording, 0).removesuffix("?t=0")
            ):
                raise CampusError(
                    Code.SCOPE_DENIED,
                    "Timed lecture evidence belongs to another bound course or recording.",
                )
        if not lecture.recording.synthetic:
            try:
                receipt = usable_receipt(root, lecture.recording.key)
            except CampusError as error:
                if error.code == Code.SCOPE_DENIED:
                    raise
                stale.add(lecture.key)
                continue
            expected = digest(source_text(receipt).encode())
            if (
                receipt.recording != lecture.recording
                or any(resources[key].sha256 != expected for key in primary if key in resources)
                or receipt.validity.eligible != lecture.coverage.eligible
                or receipt.validity.excluded != lecture.coverage.excluded
                or receipt.processed != lecture.coverage.processed
                or receipt.missing != lecture.coverage.missing
                or (lecture.coverage.status == "complete" and receipt.status != "prepared")
            ):
                stale.add(lecture.key)
            verify_figures(root, lecture)
    return tuple(sorted(stale))


def render_lectures(root: Path, content: LectureContent) -> dict[str, JsonValue]:
    value = content.model_dump(mode="json")
    evidence = {item.key: item for item in content.evidence}
    for lecture, rendered in zip(content.lectures, value["lectures"], strict=True):
        rendered["revision"] = lecture.semantic_revision
        rendered["evidence_as_of"] = (
            lecture.checked_at
            if lecture.recording.synthetic
            else usable_receipt(root, lecture.recording.key).checked_at
        )
        rendered["source_link"] = watch_link(lecture.recording, 0).removesuffix("?t=0")
        for section, body in zip(lecture.sections, rendered["sections"], strict=True):
            body["blocks"] = render_blocks(section.blocks)
            body["citations"] = [
                {
                    "key": key,
                    "source": evidence[key].source_key,
                    "start_s": evidence[key].interval.start_s,
                    "end_s": evidence[key].interval.end_s,
                    "url": watch_link(lecture.recording, evidence[key].interval.start_s),
                }
                for key in section.evidence
                if evidence[key].interval is not None
            ]
            for figure, picture in zip(section.figures, body["figures"], strict=True):
                picture["url"] = watch_link(lecture.recording, figure.captured_at_s)
    return value


def lecture_health(root: Path, content: LectureContent) -> tuple[dict[str, JsonValue], ...]:
    result: list[dict[str, JsonValue]] = []
    for lecture in content.lectures:
        if lecture.recording.synthetic:
            result.append(
                {"key": lecture.key, "preparation": "synthetic", "as_of": lecture.checked_at}
            )
            continue
        try:
            receipt = read_receipt(root, lecture.recording.key)
            result.append(
                {
                    "key": lecture.key,
                    "preparation": receipt.status,
                    "as_of": receipt.checked_at,
                    "reason": receipt.reason if isinstance(receipt, InvalidReceipt) else "",
                }
            )
        except CampusError as error:
            result.append(
                {"key": lecture.key, "preparation": "unavailable", "reason": error.code.value}
            )
    return tuple(result)
