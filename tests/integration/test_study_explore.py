"""Explore preparation, source closure and learning-state boundaries."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from study_explore_fixture import add_explore

from tum_mcp.errors import CampusError
from tum_mcp.study_build import build, read_content, unit_revision
from tum_mcp.study_coverage import CoverageLedger, coverage_report, read_ledger
from tum_mcp.study_publish_site import export_site
from tum_mcp.study_store import load_state, private_path


def test_optional_source_edits_require_review_without_resetting_core_progress(
    project: Path,
) -> None:
    before = next(unit for unit in read_content(project).units if unit.key == "bfs")
    add_explore(project)
    build(project, publish=False)
    payload = json.loads(
        (project / "study/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    assert unit["revision"] == unit_revision(before)
    assert len(unit["explore"][0]["revision"]) == 64
    assert payload["sources"]["explore-source"]["title"] == "Context and origins"
    exported = export_site(project)["data.mjs"]
    assert b"Where the idea came from" in exported
    assert b"https://example.invalid/explore" in exported
    assert b"Core tasks do not depend" not in exported
    assert b"materials/content/material-explore-source.md" not in exported
    # A changed optional file must be reviewed just as a changed core source is.
    (project / "materials/content/material-explore-source.md").write_text(
        "Changed supporting source"
    )
    with pytest.raises(CampusError, match="changed source"):
        build(project, publish=False)


@pytest.mark.parametrize("broken", ["absent", "wrong_source", "wrong_item", "core_role"])
def test_explore_requires_resolving_enrichment_classification(project: Path, broken: str) -> None:
    add_explore(project)
    path = private_path(project, "coverage.json")
    ledger = json.loads(path.read_bytes())
    outcome = ledger["sources"][0]["outcomes"][0]
    match broken:
        case "absent":
            path.unlink()
        case "wrong_source":
            ledger["sources"][0]["source"] = "graphs"
        case "wrong_item":
            outcome["explore"][0]["item"] = "missing"
        case "core_role":
            outcome.pop("classification")
            outcome.pop("explore")
            outcome.pop("role")
            outcome["units"] = ["bfs"]
    if path.exists():
        path.write_text(json.dumps(ledger))
    with pytest.raises(CampusError, match="Explore|Enrichment"):
        build(project, publish=False)


def test_optional_backlog_does_not_hide_core_gaps_or_unknown_coverage(project: Path) -> None:
    add_explore(project)
    state = load_state(project)
    source = next(item for item in state.resources if item.resource.key == "explore-source")
    core = next(item for item in state.resources if item.resource.key == "bfs")
    state = state.model_copy(update={"resources": (source, core)})
    ledger = read_ledger(project).model_dump(mode="json")
    outcome = ledger["sources"][0]["outcomes"][0]
    outcome["status"] = "gap"
    outcome["note"] = "Optional reading is still to prepare."
    outcome.pop("explore")
    ledger["sources"].append(
        {
            "source": "bfs",
            "status": {"checked_at": "2026-10-30"},
            "outcomes": [
                {
                    "key": "queue",
                    "text": "Use a queue.",
                    "locator": "Section 1",
                    "status": "covered",
                    "units": ["bfs"],
                }
            ],
        }
    )
    report = coverage_report(
        state, read_content(project), None, CoverageLedger.model_validate(ledger)
    )
    assert report["core_complete"] and not report["complete"]
    assert report["outcome_gaps"] == []
    assert report["study_preparation"]["pending"] == []
    assert report["study_preparation"]["enrichmentPending"][0]["source"] == "explore-source"
    ledger["sources"][1]["outcomes"][0].update(status="gap", units=[], note="Core gap remains.")
    report = coverage_report(
        state, read_content(project), None, CoverageLedger.model_validate(ledger)
    )
    assert not report["core_complete"]
    assert report["outcome_gaps"][0]["outcome"] == "queue"
    ledger["sources"].pop()
    report = coverage_report(
        state, read_content(project), None, CoverageLedger.model_validate(ledger)
    )
    assert not report["core_complete"]
    assert report["study_preparation"]["unrecorded"][0]["source"] == "bfs"
    # Enrichment cannot borrow core unit references to pretend it has been prepared.
    outcome.update(status="covered", units=["bfs"])
    with pytest.raises(ValidationError):
        CoverageLedger.model_validate(ledger)


def test_classification_and_optional_content_invalidate_the_correct_reviews(project: Path) -> None:
    from tum_mcp.study_report import quality_flags
    from tum_mcp.study_review import revision
    from tum_mcp.study_structure import structure_revision

    add_explore(project)
    before = read_content(project)
    unit = next(unit for unit in before.units if unit.key == "bfs")
    ledger = read_ledger(project)
    original = structure_revision(before, None, None, None, ledger=ledger)
    edited = ledger.model_dump(mode="json")
    edited["sources"][0]["outcomes"][0]["classification"]["reason"] = (
        "A reviewed, different reason."
    )
    assert (
        structure_revision(before, None, None, None, ledger=CoverageLedger.model_validate(edited))
        != original
    )
    payload = before.model_dump(mode="json")
    changed = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    changed["explore"][0]["blocks"][0]["paragraphs"] = ["The answer is 2 + 2 = 5."]
    from tum_mcp.study_content import StudyContent

    after = StudyContent.model_validate(payload)
    changed_unit = next(unit for unit in after.units if unit.key == "bfs")
    assert unit_revision(changed_unit) == unit_revision(unit)
    assert revision(changed_unit) != revision(unit)
    assert any(
        flag["flag"] == "arithmetic" and "explore" in flag["item"]
        for flag in quality_flags(after, None)
    )


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned render checks require opt-in.",
)
def test_render_checker_measures_the_real_optional_route(project: Path) -> None:
    from typer.testing import CliRunner

    from tum_mcp.cli import app
    from tum_mcp.study_visuals import render_report, report_path

    add_explore(project)
    path = project / "study/content.json"
    payload = json.loads(path.read_bytes())
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    unit["explore"][0]["blocks"].append(
        {
            "key": "comparison",
            "kind": "table",
            "title": "Supporting comparison",
            "sources": ["explore-source"],
            "columns": ["Context", "Purpose"],
            "rows": [["Origins", "Additional context"]],
            "caption": "An optional synthetic table.",
        }
    )
    path.write_text(json.dumps(payload))
    build(project, publish=False)
    result = CliRunner().invoke(app, ["study", "visuals", str(project), "--unit", "bfs"])
    assert result.exit_code == 0, result.output
    checked = json.loads(result.output)
    assert checked["passed"], checked["defects"]
    assert "explore:origin:1" in {
        v["id"]
        for v in json.loads(report_path(project).read_text())["items"]["study/bfs"]["visuals"]
    }
    unit["explore"][0]["blocks"][-1]["caption"] = "A changed supporting caption."
    path.write_text(json.dumps(payload))
    assert "study/bfs" in render_report(project, read_content(project), None)["stale"]


def test_optional_math_and_image_are_exported_without_private_inventory(project: Path) -> None:
    from PIL import Image

    add_explore(project)
    path = project / "study/content.json"
    payload = json.loads(path.read_bytes())
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    item = unit["explore"][0]
    item["blocks"][0]["paragraphs"].append(r"An optional expression is \(x^2\).")
    image = project / "study/figures/explore-only.png"
    image.parent.mkdir(exist_ok=True)
    Image.new("RGB", (16, 16), "white").save(image)
    item["blocks"].append(
        {
            "key": "optional-picture",
            "kind": "figure",
            "sources": ["explore-source"],
            "alt": "A synthetic white square",
            "image": "figures/explore-only.png",
        }
    )
    path.write_text(json.dumps(payload))
    build(project, publish=False)
    exported = export_site(project)
    assert exported["figures/explore-only.png"] == image.read_bytes()
    assert b"<msup>" in exported["data.mjs"]
    assert b"Core tasks do not depend" not in exported["data.mjs"]
    assert b"materials/content/" not in exported["data.mjs"]


def test_optional_definition_cannot_supply_core_teaching_or_exercise_prerequisites(
    exercise_project: Path,
) -> None:
    from tum_mcp.exercise_data import check_prerequisites, read_exercises
    from tum_mcp.study_content import StudyContent

    add_explore(exercise_project)
    path = exercise_project / "study/content.json"
    payload = json.loads(path.read_bytes())
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    unit["explore"][0]["blocks"].append(
        {
            "key": "optional-definition",
            "kind": "definition",
            "term": "Optional origin",
            "statement": "A definition for supporting reading only.",
            "sources": ["explore-source"],
        }
    )
    study = StudyContent.model_validate(payload)
    assert "Optional origin" not in study.definitions()
    unit["blocks"][0]["paragraphs"].append("Use {{Optional origin}} to solve this.")
    with pytest.raises(ValidationError, match="Marked terms need a definition"):
        StudyContent.model_validate(payload)
    exercises = read_exercises(exercise_project).model_dump(mode="json")
    exercises["sets"][0]["exercises"][0]["prerequisites"] = [
        {"unit": "bfs", "block": "history", "explanation": "Requires the optional passage."}
    ]
    from tum_mcp.exercise_content import ExerciseContent

    with pytest.raises(CampusError, match="does not have"):
        check_prerequisites(ExerciseContent.model_validate(exercises), study)
