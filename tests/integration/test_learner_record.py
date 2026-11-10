import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from knowledge_fixture import fidelity_project
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.learner import record
from tum_mcp.errors import CampusError

BLOCK = "study/unit/observer/block/observer-definition"
PRACTICE = "exercises/set/sheet-1/exercise/observer-practice"
NOTE = "Registers observers after the first notification"


@pytest.fixture
def course(tmp_path: Path, course_memory: Path) -> Path:
    root = fidelity_project(tmp_path)
    # The record must work for students without the Course Memory extension.
    selection = json.loads((course_memory / "extensions.json").read_text())
    (course_memory / "extensions.json").write_text(json.dumps(selection | {"course_memory": False}))
    return root


def on(course: Path) -> Path:
    record.set_consent(course, "on", "setup")
    return course


def days(n: int) -> date:
    return date.today() - timedelta(days=n)


def test_a_course_without_a_setup_answer_records_nothing(course: Path):
    assert record.brief(course) == {"learner": "off"}
    with pytest.raises(CampusError):
        record.record(course, "attempt", item="observer-practice", outcome="wrong")
    assert not (course / ".tum-mcp/learner/events.jsonl").exists()


def test_writes_need_no_confirmation_when_on_and_resolve_unique_suffixes(course: Path):
    result = record.record(on(course), "attempt", item="observer-practice", outcome="hint")
    assert result["recorded"]
    assert record.events(course)[0].item == PRACTICE
    with pytest.raises(CampusError, match="No single course item"):
        record.record(course, "attempt", item="no-such-item", outcome="hint")
    with pytest.raises(CampusError, match="future"):
        record.record(course, "attempt", item=PRACTICE, outcome="hint", on=days(-1))


def test_the_same_event_on_the_same_day_is_recorded_once(course: Path):
    first = record.record(on(course), "attempt", item=PRACTICE, outcome="wrong")
    again = record.record(course, "attempt", item=PRACTICE, outcome="wrong")
    assert again == {"id": first["id"], "recorded": False}
    assert len(record.events(course)) == 1


def test_brief_lists_open_mistakes_with_prerequisite_review_and_drops_resolved(course: Path):
    on(course)
    kept = record.record(course, "mistake", item=PRACTICE, note=NOTE, source="exam-ws23")
    gone = record.record(course, "mistake", item="exam/concept/observer", note="Old confusion")
    record.record(course, "resolved", ref=gone["id"])
    result = record.brief(course)
    assert [row["id"] for row in result["open_mistakes"]] == [kept["id"]]
    assert result["open_mistakes"][0]["review"][0]["item"] == BLOCK
    with pytest.raises(CampusError, match="Unknown course source"):
        record.record(course, "mistake", item=PRACTICE, note="x", source="nowhere")


def test_items_come_back_after_a_miss_and_later_successes_push_them_out(course: Path):
    on(course)
    record.record(course, "attempt", item=PRACTICE, outcome="wrong", on=days(5))
    record.record(course, "attempt", item=PRACTICE, outcome="solved", on=days(4))
    assert [row["due"] for row in record.brief(course)["due"]] == [days(1).isoformat()]
    record.record(course, "attempt", item=PRACTICE, outcome="solved", on=days(1))
    assert record.brief(course)["due"] == []
    assert record.due(record.events(course), days(-6)) == {PRACTICE: (days(-6), "solved")}


def test_items_solved_at_the_first_try_are_never_scheduled(course: Path):
    record.record(on(course), "attempt", item=PRACTICE, outcome="solved", on=days(30))
    assert record.brief(course)["due"] == []


def test_brief_stays_within_its_byte_cap_by_cutting_the_least_useful_sections(course: Path):
    on(course)
    for index in range(12):
        record.record(course, "mistake", item=PRACTICE, note=f"{NOTE} {index}" * 3, on=days(index))
        record.record(course, "attempt", item=PRACTICE, outcome="wrong", on=days(index))
    result = record.brief(course)
    assert len(json.dumps(result, ensure_ascii=False)) <= record.BRIEF_BYTES
    assert result["open_mistakes"] and result["last_14_days"] is None


def test_forget_removes_by_id_item_set_or_everything_and_closes_dangling_resolutions(course: Path):
    on(course)
    mistake = record.record(course, "mistake", item=PRACTICE, note=NOTE)
    record.record(course, "resolved", ref=mistake["id"])
    record.record(course, "attempt", item="exam/concept/observer", outcome="hint")
    assert record.forget(course, event=mistake["id"]) == {"forgotten": 2, "kept": 1}
    record.record(course, "attempt", item=PRACTICE, outcome="hint")
    assert record.forget(course, item="sheet-1")["forgotten"] == 1
    assert record.forget(course, everything=True) == {"forgotten": 1, "kept": 0}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_record_files_are_private_to_the_owner(course: Path):
    record.record(on(course), "attempt", item=PRACTICE, outcome="hint")
    for name in ("consent.json", "events.jsonl"):
        assert os.stat(course / ".tum-mcp/learner" / name).st_mode & 0o077 == 0


def test_cli_records_and_shows_what_the_student_asks_about(course: Path):
    runner = CliRunner()
    base = ["study", "learner"]
    assert runner.invoke(app, [*base, "enable", str(course)]).exit_code == 0
    step = [*base, "note", str(course), "--item", PRACTICE, "--outcome", "hint"]
    assert json.loads(runner.invoke(app, step).output)["recorded"]
    shown = json.loads(runner.invoke(app, [*base, "show", str(course)]).output)
    assert shown["learner"] == "on" and shown["events"][0]["item"] == PRACTICE
    assert runner.invoke(app, [*base, "forget", str(course)]).exit_code != 0


def test_study_init_requires_the_one_time_setup_answer_before_binding(tmp_path: Path):
    example = Path(__file__).parents[1] / "fixtures/course_app"
    root = tmp_path / "new"
    command = ["study", "init", str(root), "--course", "Algorithms & Graphs"]
    command += ["--snapshot", str(example / "snapshot.json")]
    result = CliRunner().invoke(app, command)
    assert result.exit_code != 0 and "learning record" in str(result.exception)
    assert not (root / ".tum-mcp/state.json").exists()
    assert CliRunner().invoke(app, [*command, "--learner", "on"]).exit_code == 0
    assert record.consent(root) == "on"
    inspected = json.loads(CliRunner().invoke(app, ["study", "inspect", str(root)]).output)
    assert inspected["learner"] == "on" and inspected["course_memory"] is False
