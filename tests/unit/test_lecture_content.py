import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.course.lecture.content import LectureContent
from tum_mcp.course.project.models import Resource

FIXTURE = Path(__file__).parents[1] / "fixtures/course_app/lectures.json"


def fixture() -> dict:
    return json.loads(FIXTURE.read_bytes())


def test_highlights_validate_without_assessments_and_keep_actual_frame_time() -> None:
    lecture = LectureContent.model_validate_json(FIXTURE.read_bytes()).lectures[0]
    assert [item.key for item in lecture.highlights] == ["h-first", "h-second"]
    assert lecture.highlights[0].thumbnail.captured_at_s == 37.5
    assert lecture.coverage.status == "complete"
    assert not hasattr(lecture, "questions")


def test_chapter_preview_uses_a_cited_page_without_moving_comment_anchors() -> None:
    value = fixture()
    chapter = value["lectures"][0]["chapters"][0]
    chapter.update(sources=["graphs"], pages="2-5")
    original = LectureContent.model_validate(value).lectures[0].semantic_revision
    chapter["preview_page"] = 4
    assert LectureContent.model_validate(value).lectures[0].semantic_revision == original
    chapter["preview_page"] = 6
    with pytest.raises(ValidationError, match="within the chapter"):
        LectureContent.model_validate(value)


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


def test_legacy_note_figure_and_label_load_with_their_old_revision() -> None:
    value = fixture()
    del value["lectures"][0]["chapters"]
    # Revisions computed by the code before note blocks existed: comments keep their anchors.
    assert (
        LectureContent.model_validate(value).lectures[0].semantic_revision
        == "374679900b615c6b7087386f958db1f237feea4c9dfc4e066d88f51f3ff34b22"
    )
    note = value["lectures"][0]["notes"][0]
    note["kind"] = "clarification"
    note["figure"] = {
        "kind": "figure",
        "alt": "A circle representing one search region.",
        "svg": '<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="80"/></svg>',
        "sources": note["sources"],
    }
    parsed = LectureContent.model_validate(value)
    migrated = parsed.lectures[0].notes[0]
    assert migrated.kind is None
    assert [block.kind for block in migrated.blocks] == ["figure"]
    assert (
        parsed.lectures[0].semantic_revision
        == "f1ae52404f5892e4b48fc8e5456a5d22e1e66fbbcf5a0ce3ca589fd07c34bfce"
    )
    note["figure"]["svg"] = note["figure"]["svg"].replace('r="80"', 'r="60"')
    assert LectureContent.model_validate(value).lectures[0].semantic_revision != (
        "f1ae52404f5892e4b48fc8e5456a5d22e1e66fbbcf5a0ce3ca589fd07c34bfce"
    )
    note["figure"]["svg"] = (
        '<svg viewBox="0 0 200 200"><script>alert(1)</script>'
        '<circle cx="100" cy="100" r="80"/></svg>'
    )
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_note_blocks_show_objects_from_the_note_sources() -> None:
    value = fixture()
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    note = value["lectures"][0]["notes"][0]
    note["blocks"] = [
        {
            "kind": "figure",
            "alt": "The slide's adjacency lists of the three vertices.",
            "image": "figures/adjacency.png",
            "sources": note["sources"],
        },
        {
            "kind": "formula",
            "sources": note["sources"],
            "latex": r"\sum_{v} \deg(v) = 2|E|",
            "plain": "The degrees add up to twice the number of edges.",
            "symbols": [{"symbol": "|E|", "meaning": "Number of edges in the graph"}],
        },
    ]
    parsed = LectureContent.model_validate(value)
    assert [block.kind for block in parsed.lectures[0].notes[0].blocks] == ["figure", "formula"]
    assert parsed.lectures[0].semantic_revision != before
    note["blocks"][1]["sources"] = ["undeclared"]
    with pytest.raises(ValidationError, match="declared sources"):
        LectureContent.model_validate(value)
    # Prose belongs to the note's own fields, a stepped run to a highlight.
    note["blocks"][1] = {"kind": "text", "sources": note["sources"], "paragraphs": ["Prose."]}
    with pytest.raises(ValidationError):
        LectureContent.model_validate(value)


def test_lecture_text_gets_the_shared_content_flags() -> None:
    from tum_mcp.course.checks.report import lecture_flags

    value = fixture()
    assert lecture_flags(LectureContent.model_validate(value)) == []
    lecture = value["lectures"][0]
    note = lecture["notes"][0]
    note["text"] = (
        "The lecturer notes that the parent links G ← C ← A are followed back from the goal, "
        "so the actions are replayed in reverse order. Replaying them fails under a "
        "disturbance. The agent must then observe the state it actually reached and search "
        "again from there."
    )
    found = {
        (flag["item"], flag["flag"]) for flag in lecture_flags(LectureContent.model_validate(value))
    }
    item = f"lecture/{lecture['key']}/{note['key']}"
    assert {
        (item, "plain_math"),
        (item, "recording_narration"),
        (item, "dense_paragraph"),
    } <= found


def test_a_chapter_without_pages_or_entries_is_flagged() -> None:
    # A trial made chapters of a guest talk and the recording's last 40 seconds.
    from tum_mcp.course.checks.report import lecture_flags

    value = fixture()
    lecture = value["lectures"][0]
    lecture["chapters"] = [
        {"key": "layers", "title": "Layers", "interval": {"start_s": 0, "end_s": 400}},
        {"key": "tail", "title": "Recording tail", "interval": {"start_s": 400, "end_s": 600}},
    ]
    flags = lecture_flags(LectureContent.model_validate(value))
    assert [(f["item"], f["flag"]) for f in flags] == [
        (f"lecture/{lecture['key']}#chapters[1]", "empty_chapter")
    ]
    lecture["chapters"][1] |= {"title": "Running time", "sources": ["graphs"], "pages": "2"}
    assert lecture_flags(LectureContent.model_validate(value)) == []


def test_chapters_hold_their_entries_in_recording_order() -> None:
    value = fixture()
    lecture = value["lectures"][0]
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    lecture["chapters"] = [
        {"key": "layers", "title": "Layers of a search", "interval": {"start_s": 0, "end_s": 300}},
        {
            "key": "cost",
            "title": "Running time",
            "interval": {"start_s": 300, "end_s": 600},
            "sources": ["graphs"],
            "pages": "2",
        },
    ]
    parsed = LectureContent.model_validate(value).lectures[0]
    assert [chapter.key for chapter in parsed.chapters] == ["layers", "cost"]
    assert parsed.semantic_revision != before
    for corrupt, message in (
        ({"interval": {"start_s": 250, "end_s": 600}}, "recording order"),
        ({"interval": {"start_s": 300, "end_s": 700}}, "inside the recording"),
        ({"sources": ["undeclared"]}, "undeclared source"),
        ({"key": "layers"}, "unique"),
    ):
        broken = copy.deepcopy(value)
        broken["lectures"][0]["chapters"][1].update(corrupt)
        with pytest.raises(ValidationError, match=message):
            LectureContent.model_validate(broken)
    # A highlight that spans two topics belongs to neither.
    broken = copy.deepcopy(value)
    broken["lectures"][0]["chapters"][0]["interval"]["end_s"] = 40
    broken["lectures"][0]["chapters"][1]["interval"]["start_s"] = 40
    with pytest.raises(ValidationError, match="inside one chapter"):
        LectureContent.model_validate(broken)


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


def test_note_context_sets_up_its_message_without_repeating_it() -> None:
    value = json.loads(FIXTURE.read_bytes())
    note = value["lectures"][0]["notes"][0]
    note["context"] = note["text"]
    with pytest.raises(ValueError, match="does not repeat it"):
        LectureContent.model_validate(value)
    note.pop("context")
    with pytest.raises(ValueError, match="context"):
        LectureContent.model_validate(value)


def highlight_steps(*times: float) -> list[dict]:
    return [{"action": f"Stage {i}.", "why": "It follows.", "at": at} for i, at in enumerate(times)]


@pytest.mark.parametrize(
    "steps",
    [
        highlight_steps(21),
        highlight_steps(21, 60),
        highlight_steps(25, 21),
        highlight_steps(21, 21),
        [{"action": "Untimed.", "why": "It follows."}, *highlight_steps(22)],
    ],
)
def test_highlight_steps_are_timed_inside_the_highlight_in_recording_order(steps) -> None:
    value = fixture()
    value["lectures"][0]["highlights"][0]["steps"] = steps
    with pytest.raises(ValidationError, match="highlight"):
        LectureContent.model_validate(value)


def test_highlight_steps_change_the_teaching_revision() -> None:
    value = fixture()
    before = LectureContent.model_validate(value).lectures[0].semantic_revision
    value["lectures"][0]["highlights"][0]["steps"] = highlight_steps(21, 22)
    assert LectureContent.model_validate(value).lectures[0].semantic_revision != before
