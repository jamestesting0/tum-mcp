import json
import os
import sys
from pathlib import Path

import pytest
from lecture_prepared_fixture import Prepared, prepare_recording
from test_review_loop import answer, packets
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.browser_evidence import browser_identity, save_receipt
from tum_mcp.course.app.build import build
from tum_mcp.course.checks.batch import assess_batch
from tum_mcp.course.project.store import load_state
from tum_mcp.course.review import loop
from tum_mcp.course.sources import text
from tum_mcp.errors import CampusError
from tum_mcp.moodle.browsers import BrowserChoice


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


@pytest.mark.parametrize(
    ("gate", "command"),
    [
        ("build", "tum-mcp study build . --local-only"),
        ("browser", "tum-mcp study visuals . --interact --lecture bfs-lecture"),
    ],
)
def test_lecture_readiness_reports_the_shared_check(
    prepared: Prepared, monkeypatch: pytest.MonkeyPatch, gate: str, command: str
) -> None:
    write_selection(prepared, selection(prepared))
    write_batch(prepared)
    assert assess_batch(prepared.root, "complete").ready
    if gate == "build":
        (prepared.root / "app/data.mjs").unlink()
    else:
        from tum_mcp.course.checks import batch, preparation

        monkeypatch.setattr(batch, "_browser_problems", preparation._browser_problems)
    result = CliRunner().invoke(
        app,
        [
            "study",
            "report",
            str(prepared.root),
            "--section",
            "readiness",
            "--batch",
            "complete",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output or repr(result.exception)
    readiness = json.loads(result.output)["readiness"]
    assert not readiness["ready"]
    assert readiness["workspace_actions"]["lecture"]["status"] == "pending"
    assert readiness["workspace_actions"]["lecture"]["command"] == command


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param("interact/desktop/#lectures/bfs-lecture", id="interaction"),
        pytest.param("shell/desktop/dark/lectures", id="shell"),
        pytest.param("visual/desktop/lecture", id="index-picture"),
        pytest.param(None, id="passing"),
    ],
)
def test_exercise_blocker_does_not_hide_lecture_receipt(
    prepared: Prepared, monkeypatch: pytest.MonkeyPatch, missing: str | None
) -> None:
    from tum_mcp.course.checks import batch, preparation

    write_selection(prepared, selection(prepared))
    exercise = "exercises/week-two/withheld"
    write_batch(prepared, (exercise,))
    monkeypatch.setattr(batch, "_browser_problems", preparation._browser_problems)
    browser = BrowserChoice("Synthetic browser", sys.executable)
    identity = browser_identity(prepared.root, browser)
    monkeypatch.setattr(preparation, "browser_choice", lambda: browser)
    states = {
        "interact/desktop/#lectures": True,
        "interact/desktop/#lectures/bfs-lecture/h-first": True,
        "visual/desktop/lecture": True,
        "visual/desktop/lecture/bfs-lecture": True,
        "interact/desktop/#lectures/bfs-lecture": True,
        "interact/phone/#lectures/bfs-lecture": True,
        "shell/phone/light/lectures": True,
        "shell/phone/dark/lectures": True,
        "shell/desktop/light/lectures": True,
        "shell/desktop/dark/lectures": True,
    }
    if missing:
        states.pop(missing)
    from PIL import Image

    picture = ".tum-mcp/visuals/lecture.png"
    (prepared.root / picture).parent.mkdir(exist_ok=True)
    Image.new("RGB", (20, 20)).save(prepared.root / picture)
    save_receipt(
        prepared.root,
        identity,
        states,
        captures={key: (picture,) for key in states if key.startswith("visual/")},
    )

    readiness = assess_batch(prepared.root, "complete")

    exercise_problem = f"{exercise}: requested draft is missing."
    lecture_problems = (f"{missing}: browser evidence is missing.",) if missing else ()
    assert readiness.problems == (exercise_problem, *lecture_problems)
    assert readiness.workspace_problems == {
        "exercises": (exercise_problem,),
        "lecture": lecture_problems,
    }
    assert not readiness.ready
    actions = readiness.report()["workspace_actions"]
    assert isinstance(actions, dict)
    assert actions["lecture"] == {
        "status": "pending" if missing else "prepared",
        "prerequisite": next(iter(lecture_problems), None),
        "command": (
            "tum-mcp study visuals . --lecture bfs-lecture"
            if missing and missing.startswith("visual/")
            else "tum-mcp study visuals . --interact --lecture bfs-lecture"
            if missing
            else None
        ),
        "problems": len(lecture_problems),
    }


def test_missing_mixed_browser_receipts_offer_a_scoped_lecture_command(prepared: Prepared) -> None:
    from tum_mcp.course.checks.preparation import _browser_problems

    issues = _browser_problems(
        prepared.root, ["#lectures", "#lectures/bfs-lecture", "#exam/sheet"], {"lecture", "exam"}
    )
    assert {issue.command for issue in issues if "lecture" in issue.workspaces} == {
        "tum-mcp study visuals . --interact --lecture bfs-lecture"
    }


def test_lecture_resume_reads_only_a_current_partial_selection(prepared: Prepared) -> None:
    value = selection(prepared)
    value["decisions"] = value["decisions"][:2]
    folder = prepared.root / ".tum-mcp/work/lecture-selection"
    folder.mkdir(parents=True)
    checkpoint = folder / f"{prepared.recording.key}.json"
    checkpoint.write_text(json.dumps(value))

    command = [
        "lecture",
        "selection-progress",
        str(prepared.root),
        "--recording",
        prepared.recording.key,
    ]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["next_interval"]["start_s"] == 60
    assert [
        {key: decision[key] for key in ("interval", "disposition", "entry", "reason")}
        for decision in report["decisions"]
    ] == value["decisions"]
    assert not report["ready_to_finalize"]
    write_batch(prepared)
    assert not assess_batch(prepared.root, "complete").ready

    (resource,) = load_state(prepared.root).resources
    assert resource.path and resource.sha256
    material_path = prepared.root / resource.path
    original = material_path.read_bytes()
    value["materials"] = [{"key": resource.resource.key, "sha256": resource.sha256}]
    value["decisions"][1]["material"] = resource.resource.key
    checkpoint.write_text(json.dumps(value))
    material_path.write_bytes(original + b"\nRevised slide.")
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["next_interval"]["start_s"] == 20
    assert len(report["decisions"]) == 1
    assert any("current material" in problem for problem in report["problems"])
    material_path.write_bytes(original)

    value["transcript_sha256"] = "f" * 64
    checkpoint.write_text(json.dumps(value))
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["next_interval"]["start_s"] == 0
    assert report["decisions"] == []
    assert any("transcript" in problem for problem in report["problems"])

    result = CliRunner().invoke(app, [*command, "--finalize"])
    assert result.exit_code != 0 and "another transcript" in str(result.exception)
    assert not (prepared.root / ".tum-mcp/lecture-review").exists()
    checkpoint.write_text(json.dumps(selection(prepared)))
    result = CliRunner().invoke(app, [*command, "--finalize"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert not any("selection map" in p for p in assess_batch(prepared.root, "complete").problems)


def test_lecture_inspect_distinguishes_missing_and_out_of_scope_meetings(
    prepared: Prepared,
) -> None:
    root = prepared.root
    key = prepared.recording.key
    (root / ".tum-mcp/schedule.json").write_text(
        json.dumps(
            {
                "sessions": [
                    {"on": on, "sources": [key], "label": label, "basis": "course page"}
                    for on, label in (
                        ("2026-10-25", "Search"),
                        ("2026-10-26", "Missing recording"),
                        ("2026-11-02", "Later topic"),
                    )
                ]
            }
        )
    )
    result = CliRunner().invoke(app, ["lecture", "inspect", str(root), "--through", "2026-10-26"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    meetings = json.loads(result.output)["meetings"]
    assert [(row["date"], row["disposition"], row["recordings"]) for row in meetings] == [
        ("2026-10-25", "available", [key]),
        ("2026-10-26", "missing", []),
        ("2026-11-02", "out_of_scope", []),
    ]


def test_all_through_inventory_preserves_unknown_dates_and_explains_subset(
    prepared: Prepared,
) -> None:
    write_batch(prepared)
    write_selection(prepared, selection(prepared))
    receipt = json.loads((prepared.folder / "receipt.json").read_bytes())
    for number, day in [(12, "2026-10-25"), (13, "2026-11-01")]:
        key = f"live-42-{number}"
        folder = prepared.folder.parent / key
        folder.mkdir()
        (folder / "receipt.json").write_text(
            json.dumps(
                {
                    **receipt,
                    "key": key,
                    "recording": {
                        **receipt["recording"],
                        "recording_id": number,
                        "recorded_on": day,
                    },
                }
            )
        )
    silent = prepared.folder.parent / "live-42-14"
    silent.mkdir()
    (silent / "receipt.json").write_text(
        json.dumps(
            {
                "status": "invalid",
                "key": silent.name,
                "course_id": 42,
                "recording_id": 14,
                "reason": "whole_recording_silence",
                "checked_at": "2026-10-26",
                "duration_s": 100,
            }
        )
    )
    args = [
        "lecture",
        "inspect",
        str(prepared.root),
        "--through",
        "2026-10-26",
        "--batch",
        "complete",
    ]
    runner = CliRunner()
    output = runner.invoke(app, args)
    assert output.exit_code == 0, output.output
    result = json.loads(output.output)
    rows = {row["recording"]: row for row in result["accounting"]}
    assert rows[prepared.recording.key]["authored_key"] == "bfs-lecture"
    assert rows[prepared.recording.key]["membership"] == "selected"
    assert rows[silent.name]["recorded_on"] is None
    assert rows[silent.name]["evidence"] == "invalid"
    assert rows["live-42-12"]["membership"] == "undetermined"
    assert rows["live-42-13"]["membership"] == "after_cutoff"
    assert not result["problems"]
    path = prepared.root / ".tum-mcp/batches/complete.json"
    batch = json.loads(path.read_bytes())
    batch["lecture_scope"] = {"through": "2026-10-26"}
    path.write_text(json.dumps(batch))
    assert any("live-42-12" in issue for issue in assess_batch(prepared.root, "complete").problems)
    batch["lecture_scope"]["exclusions"] = {
        "live-42-12": {
            "reason": "Second capture of the same meeting and worked example.",
            "duplicate_of": prepared.recording.key,
        }
    }
    path.write_text(json.dumps(batch))
    assert assess_batch(prepared.root, "complete").ready
    for target in ("live-42-13", silent.name):
        batch["lecture_scope"]["exclusions"]["live-42-12"]["duplicate_of"] = target
        path.write_text(json.dumps(batch))
        issues = assess_batch(prepared.root, "complete").problems
        assert any("live-42-12" in issue and target in issue for issue in issues)


@pytest.mark.skipif(os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Owned browser QA")
def test_scoped_commands_clear_lecture_readiness_and_detect_missing_frame(
    prepared: Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.checks import batch, preparation

    monkeypatch.setattr(batch, "_browser_problems", preparation._browser_problems)
    write_batch(prepared)
    write_selection(prepared, selection(prepared))
    runner = CliRunner()
    root = str(prepared.root)
    requested = ["study", "visuals", root, "--lecture", "bfs-lecture", "--json"]
    for options in (["--interact"], []):
        response = runner.invoke(app, [*requested, *options])
        assert response.exit_code == 0, response.output or repr(response.exception)
        result = json.loads(response.output)
        assert result["passed"], result
        if options:
            assert result["pages"] == 3
        else:
            assert result["checked"] == ["lecture", "lecture/bfs-lecture"]
    assert assess_batch(prepared.root, "complete").ready
    highlight = prepared.notes["lectures"][0]["highlights"][1]
    (prepared.root / "app" / highlight["thumbnail"]["asset"]).unlink()
    failed = json.loads(runner.invoke(app, [*requested, "--interact"]).output)
    assert not failed["passed"]
    assert any(problem["control"] == highlight["key"] for problem in failed["problems"])


def test_reviewer_distinguishes_source_freshness_from_page_bounds(prepared: Prepared) -> None:
    root = prepared.root
    (material,) = load_state(root).resources
    key = material.resource.key
    assert material.sha256
    checkpoint = root / ".tum-mcp/digests" / f"{key}.json"
    checkpoint.parent.mkdir(exist_ok=True)
    checkpoint.write_text(
        json.dumps(
            {
                "source": key,
                "sha256": material.sha256,
                "examples": [{"pages": "2", "text": "An example on the second page."}],
            }
        )
    )

    def evidence() -> dict:
        return loop._digests(root, {"sources": [key]})[0]

    initial = evidence()
    assert initial["status"] == "current" and initial["locator_status"] == "unverified"
    cache = root / ".tum-mcp/cache/text" / f"{material.sha256}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        text.TextRecord(
            extractor=text.EXTRACTOR,
            sha256=material.sha256,
            kind="pdf",
            pages=(text.TextPage(number=1, text="First page.", available=True),),
        ).model_dump_json()
    )
    assert evidence()["locator_status"] == "invalid"
    assert evidence()["pages_outside"] == ["2"]
    path = root / ".tum-mcp/state.json"
    state = json.loads(path.read_bytes())
    state["resources"][0]["status"] = "withdrawn"
    path.write_text(json.dumps(state))
    assert evidence()["availability"] == "unavailable"
    assert "examples" not in evidence()


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


def test_repair_may_remove_a_lecture_entry_while_its_selection_stays_in_review(
    prepared: Prepared,
) -> None:
    # Both baseline reviews dropped a highlight that repeats a worked slide; the loop refused
    # the removal, so one author kept the key as a note and the other could not verify.
    from tum_mcp.course.review.repair_scope import repair_scope

    value = selection(prepared)
    write_selection(prepared, value)
    write_batch(prepared)
    loop.start(prepared.root, batch="complete")
    for packet in packets(prepared.root, loop.next_round(prepared.root)):
        loop.record(prepared.root, answer(packet), "fresh")
    lecture = prepared.notes["lectures"][0]
    lecture["highlights"] = [h for h in lecture["highlights"] if h["key"] != "h-second"]
    used = {key for entry in lecture["notes"] + lecture["highlights"] for key in entry["evidence"]}
    prepared.notes["evidence"] = [e for e in prepared.notes["evidence"] if e["key"] in used]
    prepared.write_notes()
    value["decisions"][2:5] = [
        {
            "interval": {"start_s": 60, "end_s": 300},
            "disposition": "omit",
            "reason": "Pages 2-3 already work through the second trace.",
        }
    ]
    write_selection(prepared, value)
    build(prepared.root, publish=False)

    result = repair_scope(prepared.root, "The second clip repeats the slide's worked trace.")

    assert result["removed"] == ["lecture/bfs-lecture/h-second"] and result["added"] == []
    card = loop.close_round(prepared.root)
    assert card["preparation"]["ready"]
    assert card["structural_repairs"][0]["removed"] == ["lecture/bfs-lecture/h-second"]
    rows = {row["item"] for row in card["items"]}
    assert "lecture/bfs-lecture/h-second" not in rows and "lecture/bfs-lecture" in rows


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


def test_a_lecture_needs_chapters_and_each_decision_stays_inside_one(prepared: Prepared) -> None:
    # Omissions of 12-27 minutes with one-line reasons hid what they skipped; a decision now
    # speaks for one topic.
    value = selection(prepared)
    write_selection(prepared, value)
    write_batch(prepared)
    lecture = prepared.notes["lectures"][0]
    chapters = lecture.pop("chapters")
    prepared.write_notes()
    build(prepared.root, publish=False)

    assert any("add chapters" in p for p in assess_batch(prepared.root, "complete").problems)

    omitted = next(d["interval"] for d in value["decisions"] if d["disposition"] == "omit")
    middle = (omitted["start_s"] + omitted["end_s"]) / 2
    lecture["chapters"] = [
        chapters[0] | {"interval": {"start_s": 0, "end_s": middle}},
        {"key": "second", "title": "Second topic", "interval": {"start_s": middle, "end_s": 600}},
    ]
    prepared.write_notes()
    build(prepared.root, publish=False)
    report = assess_batch(prepared.root, "complete")

    assert not report.ready
    assert any("crosses the chapter boundary" in p for p in report.problems)
    assert not any("add chapters" in p for p in report.problems)


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
