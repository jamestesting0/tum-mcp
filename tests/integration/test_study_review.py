import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.study_review import DIMENSIONS, read_scorecard, scorecard_path
from tum_mcp.study_store import load_state


def report(project: Path) -> dict:
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "review"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["review"]


def score(project: Path, reviews: list[dict]) -> None:
    scorecard_path(project).write_text(
        json.dumps({"course_key": load_state(project).course.key, "reviews": reviews}),
        encoding="utf-8",
    )


def test_scores_follow_the_content_they_read_and_low_scores_need_a_fix(
    exercise_project: Path,
) -> None:
    # Given a course with no review yet, every unit and exercise is listed with its revision.
    project = exercise_project
    first = report(project)
    assert first["scorecard"] is False and first["passed"] is False
    items = {entry["item"]: entry["revision"] for entry in first["unreviewed"]}
    assert any(key.startswith("study/") for key in items)
    assert any(key.startswith("exercises/") for key in items)
    # When every item scores 3 on every dimension, the review passes.
    good = {name: 3 for name in DIMENSIONS}
    reviews = [
        {"item": key, "revision": value, "reviewed_at": "2026-10-29", "scores": good}
        for key, value in items.items()
    ]
    score(project, reviews)
    assert report(project)["passed"] is True
    # A score below 3 must name what the student meets.
    unit = next(key for key in items if key.startswith("study/"))
    reviews[0] = reviews[0] | {"scores": good | {"cognitive_load": 2}}
    score(project, reviews)
    with pytest.raises(CampusError, match="names its finding"):
        read_scorecard(project)
    finding = {"dimension": "cognitive_load", "note": "Three ideas in one paragraph."}
    reviews[0] |= {"findings": [finding]}
    score(project, reviews)
    low = report(project)
    assert low["passed"] is False and low["below_bar"][0]["scores"] == {"cognitive_load": 2}
    # A friction kept for a stated reason passes; an item that blocks learning never does.
    reviews[0] |= {"kept": "The source gives no smaller example."}
    score(project, reviews)
    assert report(project)["passed"] is True
    reviews[0] |= {"scores": good | {"cognitive_load": 1}}
    score(project, reviews)
    assert report(project)["passed"] is False
    # Editing a reviewed unit makes its review stale.
    reviews[0] = {**reviews[0], "scores": good, "findings": []}
    reviews[0].pop("kept")
    score(project, reviews)
    content_path = project / "study/content.json"
    content = json.loads(content_path.read_bytes())
    target = next(u for u in content["units"] if f"study/{u['key']}" == unit)
    target["summary"] += " Revised."
    content_path.write_text(json.dumps(content), encoding="utf-8")
    stale = report(project)
    assert [entry["item"] for entry in stale["stale"]] == [unit] and stale["passed"] is False
