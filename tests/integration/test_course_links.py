"""Link decisions between workspaces: every exercise, cheatsheet entry, note and unit links each
existing workspace or records why none fits; new content reopens those decisions."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(project)]).exit_code == 0
    return project


def links(project: Path, *args: str) -> dict:
    result = CliRunner().invoke(app, ["study", "links", str(project), *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def open_pairs(project: Path) -> set[tuple[str, str]]:
    return {(entry["item"], entry["target"]) for entry in links(project)["undecided"]}


def test_a_none_decision_closes_a_pair_until_the_target_workspace_changes(demo: Path) -> None:
    concept = json.loads(
        sorted((demo / "app/exam/concepts").glob("*.json"))[0].read_text(encoding="utf-8")
    )
    pair = (f"concept:{concept['key']}", "study")
    assert pair in open_pairs(demo)

    links(demo, "--none", pair[0], "--target", "study", "--reason", "Taught in a later lecture.")

    assert pair not in open_pairs(demo)
    # A new Study section (a new lecture's lesson) reopens the decision.
    path = demo / "app/study/units/components.json"
    unit = json.loads(path.read_text(encoding="utf-8"))
    unit["blocks"][0]["key"] = "a-new-section"
    path.write_text(json.dumps(unit), encoding="utf-8")
    assert pair in open_pairs(demo)


def test_a_link_in_the_content_decides_the_pair(demo: Path) -> None:
    path = sorted((demo / "app/exam/concepts").glob("*.json"))[0]
    concept = json.loads(path.read_text(encoding="utf-8"))
    concept["exercises"] = [{"set": "preview", "exercise": "controls"}]
    path.write_text(json.dumps(concept), encoding="utf-8")

    assert ("exercises/preview/controls", "cheatsheet") not in open_pairs(demo)
    assert (f"concept:{concept['key']}", "exercises") not in open_pairs(demo)


def test_only_pairs_that_need_a_decision_can_be_waived(demo: Path) -> None:
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.checks.links import record_none
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.lecture.data import read_lectures

    documents = (read_content(demo), read_exercises(demo), read_exam(demo), read_lectures(demo))
    with pytest.raises(CampusError, match="needs no lectures link"):
        record_none(demo, *documents, "exercises/preview/controls", "lectures", "Not taught yet.")


def test_a_link_edit_leaves_the_review_fingerprint_of_the_teaching_unchanged(demo: Path) -> None:
    from tum_mcp.course.review import loop

    def blocks() -> dict[str, str]:
        return loop.load(demo).items["exercises/preview/controls"].blocks

    path = demo / "app/exercises/preview/controls.json"
    before = blocks()
    exercise = json.loads(path.read_text(encoding="utf-8"))
    exercise["prerequisites"][0]["explanation"] = "A different reminder of the invariant."
    path.write_text(json.dumps(exercise), encoding="utf-8")
    assert blocks() == before
    exercise["objectives"][0] = "Explain a different idea."
    path.write_text(json.dumps(exercise), encoding="utf-8")
    assert blocks() != before
