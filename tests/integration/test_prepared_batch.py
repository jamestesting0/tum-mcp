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


@pytest.mark.parametrize(
    "title, ready",
    [("BFS — 22 October 2026", False), ("BFS (Oct 22, 2026)", False), ("BFS in 3 steps", True)],
)
def test_a_lecture_title_names_its_topic_not_its_date(
    prepared: Prepared, title: str, ready: bool
) -> None:
    # A trial titled a lecture "Uninformed Search — 22 October 2026" beside the shown date.
    write_selection(prepared, selection(prepared))
    write_batch(prepared)
    prepared.notes["lectures"][0]["title"] = title
    prepared.write_notes()
    build(prepared.root, publish=False)

    report = assess_batch(prepared.root, "complete")

    assert report.ready is ready
    assert any("repeats a date" in problem for problem in report.problems) is not ready


@pytest.mark.parametrize(
    "summary, ready",
    [
        ("The earliest available recording introduces search problems.", False),
        ("The notes preserve selected clarifications.", False),
        ("Search problems, tree search and graph search.", True),
    ],
)
def test_a_lecture_summary_says_what_it_teaches(
    prepared: Prepared, summary: str, ready: bool
) -> None:
    # Two pilot runs opened the summary with the recording or the notes instead of the topic.
    write_selection(prepared, selection(prepared))
    write_batch(prepared)
    prepared.notes["lectures"][0]["summary"] = summary
    prepared.write_notes()
    build(prepared.root, publish=False)

    report = assess_batch(prepared.root, "complete")

    assert report.ready is ready


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


@pytest.mark.parametrize("unclear, ready", [((70, 100), True), ((40, 50), False)])
def test_unclear_speech_blocks_only_the_entries_that_rely_on_it(
    prepared: Prepared, monkeypatch: pytest.MonkeyPatch, unclear: tuple[int, int], ready: bool
) -> None:
    # A trial's lecture could never become ready: recognition was uncertain in time the
    # author had omitted, and the author cannot listen to the audio.
    from tum_mcp.course.lecture import selection as module
    from tum_mcp.course.lecture.evidence import Interval

    receipt = module.usable_receipt(prepared.root, prepared.recording.key)
    gap = Interval(start_s=unclear[0], end_s=unclear[1])
    monkeypatch.setattr(
        module,
        "usable_receipt",
        lambda *_: receipt.model_copy(update={"status": "partial", "uncertain": (gap,)}),
    )
    value = selection(prepared)
    value["comparison_limits"] = ["Slides 3-4 were unavailable for comparison."]
    write_selection(prepared, value)
    write_batch(prepared)

    report = assess_batch(prepared.root, "complete")

    assert report.ready is ready
    assert any("uncertain speech" in problem for problem in report.problems) is not ready


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


def test_plain_typed_mathematics_is_flagged_in_patterns_and_mocks(tmp_path: Path) -> None:
    # A trial's exam patterns typed "U1=R+6" and "0.192/0.72" as plain characters 55 times.
    from material_fixture import exam_document, exam_project

    from tum_mcp.course.content.exam import ExamContent
    from tum_mcp.course.content.exam_data import exam_item_flags

    exam = exam_document(exam_project(tmp_path))
    pattern, mock = exam["patterns"][0], exam["mocks"][0]
    for each in exam["patterns"]:
        each["workflow"][0]["apply"] = {"code": "Logger(Service())", "language": "python"}
    assert not exam_item_flags(ExamContent.model_validate(exam))
    pattern["workflow"][0]["do"] = "Solve the policy equations: U1=R+6."
    text = next(block for block in mock["questions"][0]["statement"] if "paragraphs" in block)
    text["paragraphs"] = ["Compute 0.192/0.72 to two decimals."]

    flagged = {flag["item"] for flag in exam_item_flags(ExamContent.model_validate(exam))}

    assert flagged == {
        f"exam/pattern/{pattern['key']}",
        f"exam/mock/{mock['key']}/{mock['questions'][0]['key']}",
    }
    mock_item = f"exam/mock/{mock['key']}/{mock['questions'][0]['key']}"
    # A state name or a lone symbol beside LaTeX is mathematics too; a word like "Group B" is not.
    for paragraph, typed in [
        ("The terminal utility of S3 is 4.", True),
        (r"With \(U_3=6\), each state has reward R.", True),
        ("Group B sat the exam.", False),
    ]:
        text["paragraphs"] = [paragraph]
        found = {flag["item"] for flag in exam_item_flags(ExamContent.model_validate(exam))}
        assert (mock_item in found) is typed, paragraph
    for step in pattern["workflow"]:
        step.pop("apply", None)
        for case in step.get("cases") or ():
            case.pop("apply", None)
    bare = exam_item_flags(ExamContent.model_validate(exam))
    assert {"item": f"exam/pattern/{pattern['key']}", "flag": "bare_workflow"}.items() <= next(
        flag for flag in bare if flag["flag"] == "bare_workflow"
    ).items()


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
