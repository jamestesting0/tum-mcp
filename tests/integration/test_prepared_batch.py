import json
from pathlib import Path

import pytest
from lecture_prepared_fixture import Prepared, prepare_recording
from test_review_loop import answer, packets

from tum_mcp.course.app.build import build
from tum_mcp.course.checks.batch import assess_batch
from tum_mcp.course.review import loop
from tum_mcp.errors import CampusError


@pytest.fixture
def prepared(tmp_path: Path, lecture_extension: Path, monkeypatch: pytest.MonkeyPatch) -> Prepared:
    result = prepare_recording(tmp_path)
    monkeypatch.setattr("tum_mcp.course.checks.batch._browser_problems", lambda *args: [])
    build(result.root, publish=False)
    return result


def selection(prepared: Prepared) -> dict:
    spans = [
        (0, 20, "omit", None),
        (20, 60, "highlight", "h-first"),
        (60, 120, "omit", None),
        (120, 180, "highlight", "h-second"),
        (180, 300, "omit", None),
        (300, 310, "note", "n-adjacency"),
        (310, 600, "omit", None),
    ]
    return {
        "recording": prepared.recording.key,
        "transcript_sha256": prepared.receipt().transcript_sha256,
        "decisions": [
            {
                "interval": {"start_s": start, "end_s": end},
                "disposition": disposition,
                "entry": entry,
                "reason": "Retain the useful working." if entry else "No additional teaching.",
            }
            for start, end, disposition, entry in spans
        ],
    }


def write_selection(prepared: Prepared, value: dict) -> None:
    path = prepared.root / f".tum-mcp/lecture-review/{prepared.recording.key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_batch(prepared: Prepared, extra: tuple[str, ...] = ()) -> None:
    path = prepared.root / ".tum-mcp/batches/complete.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "course_key": prepared.notes["course_key"],
                "request": "Prepare the selected recording, then review the complete batch once.",
                "items": ["lecture/bfs-lecture", *extra],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("missing", ["map", "interval", "output"])
def test_incomplete_batch_cannot_consume_the_review_round(prepared: Prepared, missing: str) -> None:
    value = selection(prepared)
    if missing == "interval":
        value["decisions"][0]["interval"]["end_s"] = 19
    if missing != "map":
        write_selection(prepared, value)
    write_batch(prepared, ("exam/pattern/missing",) if missing == "output" else ())

    report = assess_batch(prepared.root, "complete")

    assert not report.ready and report.problems
    if missing == "output":
        assert "course" in report.items
    with pytest.raises(CampusError, match="not ready"):
        loop.start(prepared.root, batch="complete")
    with pytest.raises(CampusError, match="declared batch"):
        loop.start(prepared.root, workspaces=("lectures",))
    assert loop.read_state(prepared.root) is None


def test_combined_round_includes_full_recording_selection_and_invalidates_changed_decisions(
    prepared: Prepared,
) -> None:
    value = selection(prepared)
    write_selection(prepared, value)
    write_batch(prepared)
    assert assess_batch(prepared.root, "complete").ready

    started = loop.start(prepared.root, batch="complete")
    sent = packets(prepared.root, loop.next_round(prepared.root))

    assert started.budget == 1 and started.batch
    assert set(started.scope) == {
        "lecture/bfs-lecture",
        "lecture/bfs-lecture/h-first",
        "lecture/bfs-lecture/h-second",
        "lecture/bfs-lecture/n-adjacency",
    }
    packet = next(packet for packet in sent if packet["profile"] == "lecture-selection")
    (item,) = packet["items"]
    assert len(item["evidence"]["passages"]) == 9
    assert all("words" not in passage for passage in item["evidence"]["passages"])
    assert "coverage.lecture_selection" in item["needs"]
    value["decisions"][0]["reason"] = "A changed omission decision needs a fresh reader."
    write_selection(prepared, value)
    with pytest.raises(CampusError, match="content changed"):
        loop.record(prepared.root, answer(packet), "fresh")


def test_no_selected_additions_still_gets_a_selection_review(prepared: Prepared) -> None:
    prepared.notes["lectures"][0]["notes"] = []
    prepared.notes["lectures"][0]["highlights"] = []
    prepared.notes["evidence"] = []
    prepared.write_notes()
    value = selection(prepared)
    value["decisions"] = [
        {
            "interval": {"start_s": 0, "end_s": 600},
            "disposition": "omit",
            "reason": "All useful teaching is already fully covered by the compared source.",
        }
    ]
    write_selection(prepared, value)
    write_batch(prepared)
    build(prepared.root, publish=False)

    started = loop.start(prepared.root, batch="complete")

    assert started.scope == ("lecture/bfs-lecture",)
    (packet,) = packets(prepared.root, loop.next_round(prepared.root))
    assert packet["profile"] == "lecture-selection"


def test_complete_filtered_review_keeps_matching_batch_requirements(prepared: Prepared) -> None:
    write_selection(prepared, selection(prepared))
    write_batch(prepared)
    state = loop.start(prepared.root, workspaces=("lectures",), ad_hoc=True)
    assert state.batch and state.batch.identifier == "complete"
    assert state.batch_contract and state.budget == 1


def test_batch_rejects_unchecked_highlight_boundaries(prepared: Prepared) -> None:
    write_selection(prepared, selection(prepared))
    write_batch(prepared)
    prepared.notes["lectures"][0]["highlights"][0]["interval"]["end_s"] = 61
    prepared.write_notes()
    build(prepared.root, publish=False)

    report = assess_batch(prepared.root, "complete")

    assert not report.ready
    assert any("boundaries" in problem for problem in report.problems)


@pytest.mark.parametrize("decision", [1, 5], ids=["highlight", "note"])
def test_selection_cannot_omit_speech_used_by_a_retained_entry(
    prepared: Prepared, decision: int
) -> None:
    value = selection(prepared)
    boundary = value["decisions"][decision]["interval"]["end_s"] - 1
    value["decisions"][decision]["interval"]["end_s"] = boundary
    value["decisions"][decision + 1]["interval"]["start_s"] = boundary
    write_selection(prepared, value)
    write_batch(prepared)

    report = assess_batch(prepared.root, "complete")

    assert not report.ready
    assert any("omitted" in problem for problem in report.problems)
    with pytest.raises(CampusError, match="not ready"):
        loop.start(prepared.root, batch="complete")
    assert loop.read_state(prepared.root) is None


def test_a_note_and_highlight_can_share_retained_speech(prepared: Prepared) -> None:
    lecture = prepared.notes["lectures"][0]
    note = lecture["notes"][0]
    note["title"] = "Why first discovery is shortest"
    speech_keys = {e["key"] for e in prepared.notes["evidence"] if e["kind"] != "frame"}
    note["evidence"] = [key for key in lecture["highlights"][0]["evidence"] if key in speech_keys]
    note["context"] = "BFS discovers vertices in increasing distance from its starting vertex."
    note["text"] = (
        "The queue holds only the current distance and the next, so first discovery is shortest."
    )
    used = {key for entry in lecture["notes"] + lecture["highlights"] for key in entry["evidence"]}
    prepared.notes["evidence"] = [e for e in prepared.notes["evidence"] if e["key"] in used]
    prepared.write_notes()
    value = selection(prepared)
    value["decisions"][1]["interval"]["start_s"] = 30
    note_decision = value["decisions"][5]
    note_decision.update(disposition="omit", entry=None)
    value["decisions"].insert(
        1,
        {
            "interval": {"start_s": 20, "end_s": 30},
            "disposition": "note",
            "entry": note["key"],
            "reason": "Keep the queue invariant as a note and its explanation as a highlight.",
        },
    )
    write_selection(prepared, value)
    write_batch(prepared)
    build(prepared.root, publish=False)

    assert assess_batch(prepared.root, "complete").ready


def test_a_pattern_batch_also_checks_its_visible_cheatsheet(tmp_path: Path) -> None:
    from documents import content_file
    from material_fixture import exam_document, exam_project

    root = exam_project(tmp_path)
    (root / "app").mkdir()
    exam = exam_document(root)
    (content_file(root, "exam")).write_text(json.dumps(exam))
    folder = root / ".tum-mcp/batches"
    folder.mkdir()
    (folder / "pattern.json").write_text(
        json.dumps(
            {
                "course_key": exam["course_key"],
                "request": "Prepare the first exam pattern.",
                "items": [
                    f"exam/pattern/{exam['patterns'][0]['key']}",
                    f"exam/mock/{exam['mocks'][0]['key']}/{exam['mocks'][0]['questions'][0]['key']}",
                ],
            }
        )
    )

    report = assess_batch(root, "pattern")

    assert "exam/sheet" in report.items
    assert any(key.startswith("exam/mock/") for key in report.items)
