import json
from pathlib import Path

import pytest
from documents import content_file
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.build import build
from tum_mcp.course.ledger.coverage import ledger_path, read_ledger, study_preparation
from tum_mcp.course.project.store import load_state
from tum_mcp.errors import CampusError


def ledger(project: Path, sources: list[dict]) -> None:
    state = load_state(project)
    ledger_path(project).write_text(
        json.dumps({"course_key": state.course.key, "sources": sources}), encoding="utf-8"
    )


def app_data(project: Path) -> dict:
    text = (project / "app/data.mjs").read_text(encoding="utf-8")
    return json.loads(text.removeprefix("export default ").removesuffix(";\n"))


def declare_sheet(project: Path) -> tuple[dict, str]:
    path = content_file(project, "exercises")
    exercises = json.loads(path.read_bytes())
    sheet = exercises["sets"][0]["exercises"][0]["sources"][0]["key"]
    exercises["sets"][0]["sheet"] = sheet
    path.write_text(json.dumps(exercises), encoding="utf-8")
    return exercises, sheet


def linked(*extra: dict) -> list[dict]:
    return [
        {"label": "1", "exercise": "sample-relaxation"},
        {"label": "2", "exercise": "sample-minimum-proof"},
        *extra,
    ]


def test_preparation_is_derived_from_links_and_shown_to_learners(exercise_project: Path) -> None:
    # Given one linked outcome, one with nothing linked yet, and a sheet whose two prepared
    # problems are linked while a third has no exercise.
    project = exercise_project
    state = load_state(project)
    content = json.loads((content_file(project, "study")).read_bytes())
    exercises, sheet = declare_sheet(project)
    lecture = content["units"][0]["sources"][0]["key"]
    ledger(
        project,
        [
            {
                "source": lecture,
                "status": {"availability": "released", "checked_at": "2026-10-29"},
                "outcomes": [
                    {
                        "key": "o1",
                        "text": "Explain the idea.",
                        "locator": "Slide 2",
                        "units": [content["units"][0]["key"]],
                    },
                    {"key": "o2", "text": "Apply the idea to a new graph.", "locator": "Slide 2"},
                ],
            },
            {
                "source": sheet,
                "status": {"semester": "WS24/25", "checked_at": "2026-10-29"},
                "items": linked({"label": "3"}),
            },
        ],
    )
    # When the course is built and the coverage is reported.
    build(project, publish=False)
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "coverage"])
    report = json.loads(result.stdout)["coverage"]
    # Then only what nothing links is pending, for the agent and for learners alike.
    assert result.exit_code == 0
    assert not report["complete"]
    assert [(item["outcome"], item["status"]) for item in report["outcome_gaps"]] == [
        ("o2", "pending")
    ]
    assert report["unprepared_items"] == [{"source": sheet, "label": "3", "status": "pending"}]
    assert report["other_semester"] == [{"source": sheet, "semester": "WS24/25"}]
    recorded = {lecture, sheet}
    assert {item["source"] for item in report["not_inspected"]} == {
        item.resource.key
        for item in state.resources
        if item.resource.kind in {"content", "exercise"} and item.resource.key not in recorded
    }
    payload = app_data(project)
    assert payload["pending"] == [
        {
            "set": exercises["sets"][0]["key"],
            "source": payload["sources"][sheet]["title"],
            "labels": ["3"],
        }
    ]
    assert payload["studyPreparation"] == {"pending": report["study_preparation"]["pending"]}
    assert [o["key"] for o in payload["studyPreparation"]["pending"][0]["outcomes"]] == ["o2"]


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([{"label": "1", "exercise": "sample-relaxation"}, {"label": "2"}], "link it"),
        ([{"label": "1", "exercise": "sample-relaxation"}], "no ledger item"),
        (linked({"label": "1b", "exercise": "sample-relaxation"}), "more than once"),
        (
            [
                {"label": "1", "exercise": "sample-relaxation", "part": "(z)"},
                {"label": "2", "exercise": "sample-minimum-proof"},
            ],
            "lacks",
        ),
    ],
)
def test_a_prepared_problem_cannot_hide_behind_a_missing_or_wrong_link(
    exercise_project: Path, items: list[dict], message: str
) -> None:
    _, sheet = declare_sheet(exercise_project)
    ledger(
        exercise_project,
        [{"source": sheet, "status": {"checked_at": "2026-11-05"}, "items": items}],
    )
    with pytest.raises(CampusError, match=message):
        build(exercise_project, publish=False)


def test_pending_problems_stay_under_the_set_whose_sheet_they_come_from(
    exercise_project: Path,
) -> None:
    # Given a second set whose problem also cites the first set's sheet, as a later sheet
    # that continues an earlier problem does.
    project = exercise_project
    exercises, sheet = declare_sheet(project)
    state = load_state(project)
    other = next(
        item for item in state.resources if item.status == "current" and item.resource.key != sheet
    )
    follow_up = json.loads(json.dumps(exercises["sets"][0]["exercises"][0]))
    follow_up.update(key="follow-up", label="Exercise 5")
    follow_up["sources"].append({"key": other.resource.key, "sha256": other.sha256})
    exercises["sets"].append(
        {
            "key": "sheet-2",
            "title": "Sheet 2",
            "sheet": other.resource.key,
            "exercises": [follow_up],
        }
    )
    (content_file(project, "exercises")).write_text(json.dumps(exercises), encoding="utf-8")
    ledger(
        project,
        [
            {
                "source": sheet,
                "status": {"checked_at": "2026-11-05"},
                "items": linked({"label": "4"}),
            },
            {
                "source": other.resource.key,
                "status": {"checked_at": "2026-11-05"},
                "items": [{"label": "5", "exercise": "follow-up"}],
            },
        ],
    )
    # When the course is built.
    build(project, publish=False)
    # Then the first sheet's open problem is listed under the first set, not the citing one.
    assert [(entry["set"], entry["labels"]) for entry in app_data(project)["pending"]] == [
        ("sheet-1", ["4"])
    ]


def test_bonus_problems_are_skipped_by_default_and_never_shown_as_missing(
    exercise_project: Path,
) -> None:
    _, sheet = declare_sheet(exercise_project)
    ledger(
        exercise_project,
        [
            {
                "source": sheet,
                "status": {"checked_at": "2026-11-05"},
                "items": linked({"label": "3*", "role": "bonus"}),
            }
        ],
    )
    build(exercise_project, publish=False)
    result = CliRunner().invoke(
        app, ["study", "report", str(exercise_project), "--section", "coverage"]
    )
    report = json.loads(result.stdout)["coverage"]
    assert app_data(exercise_project)["pending"] == []
    assert report["unprepared_items"] == []
    assert report["skipped_bonus"] == [{"source": sheet, "label": "3*"}]


def test_study_preparation_preserves_unknown_coverage_and_removes_only_resolved_gaps(
    project: Path,
) -> None:
    state = load_state(project)
    content = json.loads((content_file(project, "study")).read_bytes())
    unit = content["units"][0]["key"]
    current = {
        item.resource.key
        for item in state.resources
        if item.status == "current" and item.resource.kind == "content"
    }
    # Given prepared topics but no ledger, preparation is unknown, not a confirmed gap.
    initial = study_preparation(state, None)
    assert initial["pending"] == []
    assert {item["source"] for item in initial["unrecorded"]} == current
    entries = [
        {
            "source": "graphs",
            "status": {"checked_at": "2026-10-30"},
            "outcomes": [
                {"key": "pending", "text": "Apply the graph model.", "locator": "Slide 3"},
                {
                    "key": "gap",
                    "text": "Compare representations.",
                    "locator": "Slide 4",
                    "status": "gap",
                    "note": "Comparison is not prepared.",
                },
            ],
        },
        {
            "source": "bfs",
            "status": {"checked_at": "2026-10-30"},
            "outcomes": [
                {"key": "covered", "text": "Use a queue.", "locator": "Slide 2", "units": [unit]}
            ],
        },
        {
            "source": "dfs",
            "status": {"checked_at": "2026-10-30"},
            "outcomes": [
                {
                    "key": "excluded",
                    "text": "Compare recursive implementations.",
                    "locator": "Slide 2",
                    "status": "out_of_scope",
                    "note": "Outside the requested batch.",
                }
            ],
        },
    ]
    ledger(project, entries)
    build(project, publish=False)
    payload = app_data(project)
    before = study_preparation(state, read_ledger(project))
    assert payload["studyPreparation"] == {"pending": before["pending"]}
    assert [entry["source"] for entry in before["pending"]] == ["graphs"]
    assert [outcome["status"] for outcome in before["pending"][0]["outcomes"]] == [
        "pending",
        "gap",
    ]
    assert {entry["source"] for entry in before["unrecorded"]} == current - {"graphs", "bfs", "dfs"}
    withdrawn = state.model_copy(
        update={
            "resources": tuple(
                item.model_copy(update={"status": "withdrawn"})
                if item.resource.key == "graphs"
                else item
                for item in state.resources
            )
        }
    )
    assert study_preparation(withdrawn, read_ledger(project))["pending"] == []
    # When the graph outcomes link the unit that teaches them and the site is rebuilt.
    for outcome in entries[0]["outcomes"]:
        outcome.pop("status", None)
        outcome.pop("note", None)
        outcome["units"] = [unit]
    ledger(project, entries)
    build(project, publish=False)
    after = app_data(project)
    # Then resolved gaps disappear, unrelated unknowns and prepared topic identities survive.
    assert after["studyPreparation"] == {"pending": []}
    assert study_preparation(state, read_ledger(project))["unrecorded"] == before["unrecorded"]
    assert after["units"] == payload["units"]


def test_a_linked_outcome_cannot_also_claim_a_gap(project: Path) -> None:
    unit = json.loads((content_file(project, "study")).read_bytes())["units"][0]["key"]
    outcome = {
        "key": "o",
        "text": "T",
        "locator": "L",
        "units": [unit],
        "status": "gap",
        "note": "n",
    }
    ledger(
        project,
        [{"source": "graphs", "status": {"checked_at": "2026-11-05"}, "outcomes": [outcome]}],
    )
    with pytest.raises(CampusError, match="coverage ledger"):
        build(project, publish=False)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"units": ["no-such-unit"]}, "units Study does not have"),
        ({"source": "no-such-source"}, "unknown source"),
    ],
)
def test_ledger_references_must_resolve_before_the_build_trusts_them(
    exercise_project: Path, change: dict, message: str
) -> None:
    content = json.loads((content_file(exercise_project, "study")).read_bytes())
    entry = {
        "source": content["units"][0]["sources"][0]["key"],
        "status": {"checked_at": "2026-10-29"},
        "outcomes": [
            {
                "key": "o1",
                "text": "Explain the idea.",
                "locator": "Slide 2",
                "units": change.get("units", [content["units"][0]["key"]]),
            }
        ],
    }
    entry["source"] = change.get("source", entry["source"])
    ledger(exercise_project, [entry])
    with pytest.raises(CampusError, match=message):
        build(exercise_project, publish=False)


def test_cheatsheet_is_judged_against_source_exam_requirements(
    tmp_path: Path, course_memory: Path
) -> None:
    # Past-exam links alone never showed what the sources make exam-relevant; the ledger's
    # exam requirements do, and a requirement may not point at an entry that does not exist.
    from knowledge_fixture import knowledge_project

    from tum_mcp.course.content.exam_data import read_exam

    project = knowledge_project(tmp_path)
    exam = read_exam(project)
    source = exam.concepts[0].sources[0].key
    held = exam.concepts[0].key
    requirement = {"key": "r1", "text": "State the rule.", "locator": "Slide 3"}
    existing = json.loads(ledger_path(project).read_bytes())["sources"]

    def with_exam(requirements: list[dict]) -> list[dict]:
        others = [entry for entry in existing if entry["source"] != source]
        mine = next(
            (entry for entry in existing if entry["source"] == source),
            {"source": source, "status": {"checked_at": "2026-11-02"}},
        )
        return [*others, {**mine, "exam": requirements}]

    ledger(
        project,
        with_exam(
            [
                {**requirement, "concepts": [held]},
                {
                    "key": "r2",
                    "text": "Compare the access levels.",
                    "locator": "Slide 4",
                    "status": "gap",
                    "note": "No entry yet.",
                },
            ]
        ),
    )
    build(project, publish=False)
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "coverage"])
    sheet = json.loads(result.stdout)["coverage"]["cheatsheet"]
    assert sheet["requirements"] == 2
    assert [gap["requirement"] for gap in sheet["gaps"]] == ["r2"]
    assert held not in sheet["entries_without_requirement"]
    assert source not in sheet["sources_without_requirements"]
    from tum_mcp.course.ledger.coverage import sheet_flags

    flags = sheet_flags(load_state(project), read_ledger(project), exam)
    assert [flag["flag"] for flag in flags] == (
        ["unrecorded_sources"] if sheet["sources_without_requirements"] else []
    )
    ledger(project, with_exam([{**requirement, "concepts": ["no-such-entry"]}]))
    with pytest.raises(CampusError, match="does not have"):
        build(project, publish=False)
