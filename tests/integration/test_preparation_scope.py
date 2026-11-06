import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.ledger.coverage import CoverageLedger
from tum_mcp.course.ledger.preparation import Preparation, read_preparation, scope_problems
from tum_mcp.course.project.schedule import Schedule
from tum_mcp.course.project.store import load_state
from tum_mcp.errors import CampusError


def test_scope_accounts_for_intro_cutoff_and_new_inventory(project: Path) -> None:
    state = load_state(project)
    lectures = [entry for entry in state.resources if entry.resource.kind == "content"]
    intro, csp, *remaining = lectures
    expected = {
        "course_key": state.course.key,
        "semester": state.course.semester,
        "workspaces": ["study"],
        "mode": "through_date",
        "cutoff": "2026-11-06",
        "inventory": [
            {
                "source": entry.resource.key,
                "sha256": entry.sha256,
                "disposition": "required" if index < 2 else "later",
                "basis": "corroborated" if index == 1 else "schedule",
                "on": "2026-10-29" if index < 2 else "2026-11-12",
                "reason": "Synthetic teaching schedule.",
                "locator": "Week 3",
                "deferred_outcomes": {"semester": "Taught later."} if index == 0 else {},
            }
            for index, entry in enumerate([intro, csp, *remaining])
        ],
        "demands": [
            {
                "kind": "study",
                "id": "core",
                "source": entry.resource.key,
                "outcome": "core",
                "text": "Apply the method.",
                "locator": "Slide 2",
                "level": "apply",
            }
            for entry in (intro, csp)
        ],
    }
    ledger = CoverageLedger.model_validate(
        {
            "course_key": state.course.key,
            "sources": [
                {
                    "source": entry.resource.key,
                    "status": {"availability": "released", "checked_at": "2026-11-06"},
                    "outcomes": [
                        {"key": "core", "text": "Apply the method.", "locator": "Slide 2"},
                        *(
                            [{"key": "semester", "text": "A later topic.", "locator": "Slide 1"}]
                            if index == 0
                            else []
                        ),
                    ],
                }
                for index, entry in enumerate([intro, csp])
            ],
        }
    )
    scope = Preparation.model_validate(expected)
    schedule = Schedule.model_validate(
        {
            "sessions": [
                {
                    "on": candidate.on,
                    "sources": [candidate.source],
                    "basis": "course page",
                }
                for candidate in scope.inventory
                if candidate.basis == "schedule"
            ],
        }
    )
    assert scope_problems(scope, state, ledger, schedule) == []
    incorrect = scope.inventory[0].model_copy(
        update={"disposition": "later", "on": schedule.sessions[-1].on}
    )
    claimed_later = scope.model_copy(
        update={"inventory": (incorrect, *scope.inventory[1:]), "demands": scope.demands[1:]}
    )
    assert (
        f"{intro.resource.key}: dated evidence does not match the recorded schedule."
        in scope_problems(claimed_later, state, ledger, schedule)
    )

    incomplete = scope.model_copy(update={"inventory": scope.inventory[1:]})
    assert f"{intro.resource.key}: missing inventory disposition." in scope_problems(
        incomplete, state, ledger, schedule
    )
    demand = scope.demands[1].model_copy(update={"outcome": "semester"})
    wrong = scope.model_copy(update={"demands": (scope.demands[0], demand)})
    assert f"{csp.resource.key}: missing required outcomes core." in scope_problems(
        wrong, state, ledger, schedule
    )
    candidate = scope.inventory[1].model_copy(update={"on": None, "basis": "release"})
    undated = scope.model_copy(
        update={"inventory": (scope.inventory[0], candidate, *scope.inventory[2:])}
    )
    assert (
        f"{csp.resource.key}: dated evidence does not support its cutoff disposition."
        in scope_problems(undated, state, ledger, schedule)
    )
    with pytest.raises(CampusError, match="another course or term"):
        scope_problems(
            scope.model_copy(update={"semester": "Another term"}), state, ledger, schedule
        )


def test_preparation_schema_and_local_scope_path(project: Path) -> None:
    result = CliRunner().invoke(app, ["study", "schema", "preparation"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["properties"]["inventory"]["type"] == "array"
    assert read_preparation(project, "missing") is None
    with pytest.raises(CampusError, match="Invalid preparation scope"):
        read_preparation(project, "../outside")


def test_a_selected_sheet_part_can_explicitly_exclude_other_sheet_entries(project: Path) -> None:
    state = load_state(project)
    sheet = next(resource for resource in state.resources if resource.resource.kind == "exercise")
    ledger = CoverageLedger.model_validate(
        {
            "course_key": state.course.key,
            "sources": [
                {
                    "source": sheet.resource.key,
                    "status": {"availability": "released", "checked_at": "2026-11-06"},
                    "items": [{"label": "1(a)"}, {"label": "1(b)", "status": "not_inspected"}],
                }
            ],
        }
    )
    candidate = {
        "source": sheet.resource.key,
        "sha256": sheet.sha256,
        "disposition": "required",
        "basis": "corroborated",
        "on": "2026-11-05",
        "reason": "Use part (a) for proof practice.",
        "locator": "Page 1",
    }
    selected = {
        "course_key": state.course.key,
        "semester": state.course.semester,
        "workspaces": ["exercises"],
        "mode": "selected_sources",
        "inventory": [candidate],
        "demands": [
            {
                "kind": "exercises",
                "id": "proof",
                "source": sheet.resource.key,
                "label": "1(a)",
                "part": "(a)",
                "text": "Prove the identity.",
                "locator": "Page 1",
            }
        ],
    }
    scope = Preparation.model_validate(selected)
    assert any(
        "missing required sheet entries 1(b)" in p
        for p in scope_problems(scope, state, ledger, None)
    )

    candidate["deferred_items"] = {"1(b)": "Outside the selected problem part."}
    scope = Preparation.model_validate(selected)
    assert scope_problems(scope, state, ledger, None) == []
    assert ledger.sources[0].items[1].status == "not_inspected"

    dated = Preparation.model_validate(selected | {"mode": "through_date", "cutoff": "2026-11-06"})
    assert any(
        "cannot defer required sheet entries" in p
        for p in scope_problems(dated, state, ledger, None)
    )
