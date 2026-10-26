import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.lecture_content import LectureContent
from tum_mcp.study_models import Resource

FIXTURE = Path(__file__).parents[1] / "fixtures/course_app/lectures.json"


def test_notes_validate_without_assessments_and_keep_actual_frame_time() -> None:
    notes = LectureContent.model_validate_json(FIXTURE.read_bytes())
    lecture = notes.lectures[0]
    assert lecture.sections[0].figures[0].captured_at_s == 37.5
    assert lecture.coverage.status == "complete"
    assert not hasattr(lecture, "questions")


@pytest.mark.parametrize("timestamp", [-1, float("nan"), float("inf"), 601, 12])
def test_frame_time_must_be_finite_in_its_actual_evidence_interval(timestamp: float) -> None:
    value = json.loads(FIXTURE.read_bytes())
    value["lectures"][0]["sections"][0]["figures"][0]["captured_at_s"] = timestamp
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


@pytest.mark.parametrize(
    "path", ["../private.png", "/outside/frame.png", "https://example.invalid/f.png"]
)
def test_recording_figures_cannot_reference_unmanaged_paths(path: str) -> None:
    value = json.loads(FIXTURE.read_bytes())
    value["lectures"][0]["sections"][0]["figures"][0]["asset"] = path
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_incomplete_processing_cannot_be_declared_complete() -> None:
    value = json.loads(FIXTURE.read_bytes())
    value["lectures"][0]["coverage"]["processed"][0]["end_s"] = 200
    value["lectures"][0]["coverage"]["missing"] = [{"start_s": 200, "end_s": 600}]
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)
    value["lectures"][0]["coverage"]["status"] = "partial"
    assert LectureContent.model_validate(value).lectures[0].coverage.missing[0].start_s == 200


def test_undeclared_or_other_recording_evidence_is_rejected() -> None:
    original = json.loads(FIXTURE.read_bytes())
    for field, replacement in (("recording_id", 99), ("source_sha256", "b" * 64)):
        value = copy.deepcopy(original)
        value["evidence"][0][field] = replacement
        with pytest.raises(ValidationError):
            LectureContent.model_validate(value)
    value = copy.deepcopy(original)
    value["lectures"][0]["sections"][0]["evidence"] = ["missing"]
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_harmless_receipt_update_preserves_semantic_revision_but_text_edit_does_not() -> None:
    value = json.loads(FIXTURE.read_bytes())
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    value["lectures"][0]["checked_at"] = "2026-10-26T14:00:00Z"
    assert LectureContent.model_validate(value).lectures[0].semantic_revision == before
    value["lectures"][0]["overview"] = "Changed teaching."
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
