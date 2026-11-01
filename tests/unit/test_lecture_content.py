import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.lecture_content import LectureContent
from tum_mcp.study_models import Resource

FIXTURE = Path(__file__).parents[1] / "fixtures/course_app/lectures.json"


def fixture() -> dict:
    return json.loads(FIXTURE.read_bytes())


def test_highlights_validate_without_assessments_and_keep_actual_frame_time() -> None:
    lecture = LectureContent.model_validate_json(FIXTURE.read_bytes()).lectures[0]
    assert [item.key for item in lecture.highlights] == ["h-first", "h-second"]
    assert lecture.highlights[0].thumbnail.captured_at_s == 37.5
    assert lecture.coverage.status == "complete"
    assert not hasattr(lecture, "questions")


@pytest.mark.parametrize("timestamp", [-1, float("nan"), float("inf"), 601, 12])
def test_thumbnail_time_must_be_finite_in_its_actual_evidence_interval(timestamp: float) -> None:
    value = fixture()
    value["lectures"][0]["highlights"][0]["thumbnail"]["captured_at_s"] = timestamp
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


@pytest.mark.parametrize(
    "path", ["../private.png", "/outside/frame.png", "https://example.invalid/f.png"]
)
def test_thumbnails_cannot_reference_unmanaged_paths(path: str) -> None:
    value = fixture()
    value["lectures"][0]["highlights"][0]["thumbnail"]["asset"] = path
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_incomplete_processing_cannot_be_declared_complete() -> None:
    value = fixture()
    value["lectures"][0]["coverage"]["processed"][0]["end_s"] = 400
    value["lectures"][0]["coverage"]["missing"] = [{"start_s": 400, "end_s": 600}]
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)
    value["lectures"][0]["coverage"]["status"] = "partial"
    assert LectureContent.model_validate(value).lectures[0].coverage.missing[0].start_s == 400


def test_undeclared_or_other_recording_evidence_is_rejected() -> None:
    original = fixture()
    for field, replacement in (("recording_id", 99), ("source_sha256", "b" * 64)):
        value = copy.deepcopy(original)
        value["evidence"][0][field] = replacement
        with pytest.raises(ValidationError):
            LectureContent.model_validate(value)
    value = copy.deepcopy(original)
    value["lectures"][0]["highlights"][0]["evidence"] = ["speech", "missing"]
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def _swap_highlights(value: dict) -> None:
    highlights = value["lectures"][0]["highlights"]
    highlights.reverse()


def _overlap(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["interval"]["end_s"] = 130
    value["evidence"][0]["interval"]["end_s"] = 130


def _outside_processed(value: dict) -> None:
    lecture = value["lectures"][0]
    lecture["coverage"].update(
        status="partial",
        processed=[{"start_s": 0, "end_s": 150}],
        missing=[{"start_s": 150, "end_s": 600}],
    )


def _four_points(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["points"] = ["One.", "Two.", "Three.", "Four."]


def _long_title(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["title"] = "x" * 161


def _thumbnail_outside_highlight(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["thumbnail"]["captured_at_s"] = 70
    value["evidence"][1]["interval"] = {"start_s": 69.9, "end_s": 70.1}


def _wide_thumbnail(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["thumbnail"]["width"] = 961


def _frame_only(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["evidence"] = ["board", "board-second"]
    value["evidence"].pop(0)


def _speech_outside_highlight(value: dict) -> None:
    value["evidence"][0]["interval"]["end_s"] = 90


def _pages_without_source(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["sources"] = []


def _document_evidence(value: dict) -> None:
    value["evidence"][0]["kind"] = "document"


def _undeclared_highlight_source(value: dict) -> None:
    value["lectures"][0]["highlights"][0]["sources"] = ["other-slides"]


@pytest.mark.parametrize(
    "corrupt",
    [
        _swap_highlights,
        _overlap,
        _outside_processed,
        _four_points,
        _long_title,
        _thumbnail_outside_highlight,
        _wide_thumbnail,
        _frame_only,
        _speech_outside_highlight,
        _pages_without_source,
        _document_evidence,
        _undeclared_highlight_source,
    ],
)
def test_malformed_highlights_are_rejected(corrupt: Callable[[dict], None]) -> None:
    value = fixture()
    corrupt(value)
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_harmless_receipt_update_preserves_semantic_revision_but_text_edit_does_not() -> None:
    value = fixture()
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    value["lectures"][0]["checked_at"] = "2026-10-26T14:00:00Z"
    assert LectureContent.model_validate(value).lectures[0].semantic_revision == before
    value["lectures"][0]["summary"] = "Changed teaching."
    assert LectureContent.model_validate(value).lectures[0].semantic_revision != before


def test_reconciled_recording_and_thumbnail_provenance_does_not_edit_teaching() -> None:
    value = fixture()
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    lecture = value["lectures"][0]
    lecture["recording"]["duration_s"] = 600.5
    lecture["coverage"]["eligible"][0]["end_s"] = 600.5
    lecture["coverage"]["processed"][0]["end_s"] = 600.5
    lecture["sources"][0]["sha256"] = "b" * 64
    for evidence in value["evidence"]:
        evidence["source_sha256"] = "b" * 64
    lecture["highlights"][0]["thumbnail"].update(
        {
            "sha256": "c" * 64,
            "asset": "lecture-assets/" + "c" * 64 + ".png",
            "width": 320,
            "height": 180,
            "captured_at_s": 37.55,
        }
    )
    assert LectureContent.model_validate(value).lectures[0].semantic_revision == before


@pytest.mark.parametrize(
    "edit",
    [
        lambda highlight: highlight.update(teaches="A revised explanation."),
        lambda highlight: highlight["interval"].update(end_s=61),
    ],
)
def test_teaching_text_and_timing_are_authored_and_change_revision(
    edit: Callable[[dict], None],
) -> None:
    value = fixture()
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    edit(value["lectures"][0]["highlights"][0])
    assert LectureContent.model_validate(value).lectures[0].semantic_revision != before


@pytest.mark.parametrize("query", ["jwt=synthetic", "access_token=synthetic", "password=synthetic"])
def test_source_links_reject_authentication_parameters(query: str) -> None:
    with pytest.raises(ValidationError):
        Resource(
            key="s",
            binding="demo",
            kind="content",
            title="Source",
            url=f"https://example.invalid/watch?{query}",
        )


@pytest.mark.parametrize("keep", ["notes", "highlights", "neither"])
def test_lecture_does_not_force_either_content_kind(keep: str) -> None:
    value = fixture()
    lecture = value["lectures"][0]
    for kind in ("notes", "highlights"):
        if kind != keep:
            lecture[kind] = []
    used = {key for item in lecture["notes"] + lecture["highlights"] for key in item["evidence"]}
    value["evidence"] = [item for item in value["evidence"] if item["key"] in used]
    result = LectureContent.model_validate(value).lectures[0]
    assert bool(result.notes) == (keep == "notes")
    assert bool(result.highlights) == (keep == "highlights")
    assert len(result.images) == (2 if keep == "highlights" else 0)


@pytest.mark.parametrize("failure", ["frame_only", "unknown", "source", "pages", "duplicate_key"])
def test_note_evidence_and_shared_keys_are_validated(failure: str) -> None:
    value = fixture()
    note = value["lectures"][0]["notes"][0]
    if failure == "frame_only":
        note["evidence"] = ["board"]
    elif failure == "unknown":
        note["evidence"] = ["missing"]
    elif failure == "source":
        note["sources"] = ["missing"]
    elif failure == "pages":
        note["sources"] = []
    else:
        note["key"] = value["lectures"][0]["highlights"][0]["key"]
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


@pytest.mark.parametrize("failure", ["alt", "frame", "time"])
def test_meaningful_note_image_needs_alt_and_corresponding_frame(failure: str) -> None:
    value = fixture()
    lecture = value["lectures"][0]
    note = lecture["notes"][0]
    note.update(
        evidence=["speech", "board"],
        image=lecture["highlights"][0]["thumbnail"] | {"alt": "A path from A through B to C."},
    )
    # The same frame may support a note and a highlight without being copied twice.
    note["evidence"].append("speech-note")
    assert LectureContent.model_validate(value).lectures[0].notes[0].image is not None
    if failure == "alt":
        note["image"].pop("alt")
    elif failure == "frame":
        note["evidence"].remove("board")
    else:
        note["image"]["captured_at_s"] = 90
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_note_text_edit_invalidates_comments_but_evidence_refresh_does_not() -> None:
    value = fixture()
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    value["evidence"][-1]["interval"] = {"start_s": 300.1, "end_s": 310}
    assert LectureContent.model_validate(value).lectures[0].semantic_revision == before
    value["lectures"][0]["notes"][0]["text"] = "Count both stored adjacency entries."
    assert LectureContent.model_validate(value).lectures[0].semantic_revision != before
