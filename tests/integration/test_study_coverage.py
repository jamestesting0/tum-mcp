import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError
from tum_mcp.study_build import build
from tum_mcp.study_coverage import ledger_path, read_ledger, study_preparation
from tum_mcp.study_store import load_state


def ledger(project: Path, sources: list[dict]) -> None:
    state = load_state(project)
    ledger_path(project).write_text(
        json.dumps({"course_key": state.course.key, "sources": sources}), encoding="utf-8"
    )


def test_coverage_is_judged_against_source_outcomes_and_shown_to_learners(
    exercise_project: Path,
) -> None:
    # Given a course whose first lecture states two outcomes, one taught and one not,
    # and whose exercise sheet from an earlier semester has one problem left to prepare.
    project = exercise_project
    state = load_state(project)
    content = json.loads((project / "study/content.json").read_bytes())
    exercises = json.loads((project / "study/exercises.json").read_bytes())
    lecture = content["units"][0]["sources"][0]["key"]
    sheet = exercises["sets"][0]["exercises"][0]["sources"][0]["key"]
    prepared = exercises["sets"][0]["exercises"][0]["key"]
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
                        "status": "covered",
                        "units": [content["units"][0]["key"]],
                    },
                    {
                        "key": "o2",
                        "text": "Apply the idea to a new graph.",
                        "locator": "Slide 2",
                        "status": "gap",
                        "note": "Not yet taught.",
                    },
                ],
            },
            {
                "source": sheet,
                "status": {"semester": "WS24/25", "checked_at": "2026-10-29"},
                "items": [
                    {"label": "Problem 1.1", "status": "prepared", "exercise": prepared},
                    {"label": "Problem 1.2", "status": "pending"},
                ],
            },
        ],
    )
    # When the course is built and the coverage is reported.
    build(project, publish=False)
    result = CliRunner().invoke(app, ["study", "report", str(project), "--section", "coverage"])
    report = json.loads(result.stdout)["coverage"]
    # Then the gap, the unprepared problem and the other semester are named, nothing is complete,
    # and learners see which problem is not prepared yet under its set.
    assert result.exit_code == 0
    assert not report["complete"]
    assert [item["outcome"] for item in report["outcome_gaps"]] == ["o2"]
    assert report["unprepared_items"] == [
        {"source": sheet, "label": "Problem 1.2", "status": "pending"}
    ]
    assert report["other_semester"] == [{"source": sheet, "semester": "WS24/25"}]
    recorded = {lecture, sheet}
    assert {item["source"] for item in report["not_inspected"]} == {
        item.resource.key
        for item in state.resources
        if item.resource.kind in {"content", "exercise"} and item.resource.key not in recorded
    }
    data = (project / "study/data.mjs").read_text(encoding="utf-8")
    payload = json.loads(data.removeprefix("export default ").removesuffix(";\n"))
    assert payload["pending"] == [
        {
            "set": exercises["sets"][0]["key"],
            "source": payload["sources"][sheet]["title"],
            "labels": ["Problem 1.2"],
        }
    ]
    assert payload["studyPreparation"] == {"pending": report["study_preparation"]["pending"]}
    assert payload["studyPreparation"]["pending"] == [
        {
            "source": lecture,
            "title": payload["sources"][lecture]["title"],
            "outcomes": [
                {
                    "key": "o2",
                    "text": "Apply the idea to a new graph.",
                    "status": "gap",
                    "locator": "Slide 2",
                }
            ],
        }
    ]


def test_study_preparation_preserves_unknown_coverage_and_removes_only_resolved_gaps(
    project: Path,
) -> None:
    state = load_state(project)
    content = json.loads((project / "study/content.json").read_bytes())
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
                {
                    "key": "partial",
                    "text": "Apply the graph model.",
                    "locator": "Slide 3",
                    "status": "partial",
                    "units": [unit],
                },
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
                {
                    "key": "covered",
                    "text": "Use a queue.",
                    "locator": "Slide 2",
                    "status": "covered",
                    "units": [unit],
                }
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
        {
            "source": "exercise-graph",
            "status": {"checked_at": "2026-10-30"},
            "outcomes": [
                {
                    "key": "exercise",
                    "text": "Exercise-only gap.",
                    "locator": "Problem 1",
                    "status": "gap",
                    "note": "Not a Study source.",
                }
            ],
        },
    ]
    ledger(project, entries)
    build(project, publish=False)
    payload = json.loads(
        (project / "study/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    before = study_preparation(state, read_ledger(project))
    assert payload["studyPreparation"] == {"pending": before["pending"]}
    assert [entry["source"] for entry in before["pending"]] == ["graphs"]
    assert [outcome["status"] for outcome in before["pending"][0]["outcomes"]] == [
        "partial",
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
    # When only the reviewed graph outcomes are completed and the site is rebuilt.
    for outcome in entries[0]["outcomes"]:
        outcome.update(status="covered", units=[unit])
    ledger(project, entries)
    build(project, publish=False)
    after = json.loads(
        (project / "study/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    # Then resolved gaps disappear, unrelated unknowns and prepared topic identities survive.
    assert after["studyPreparation"]["pending"] == []
    assert after["studyPreparation"] == {"pending": []}
    assert study_preparation(state, read_ledger(project))["unrecorded"] == before["unrecorded"]
    assert after["units"] == payload["units"]


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
    content = json.loads((exercise_project / "study/content.json").read_bytes())
    entry = {
        "source": content["units"][0]["sources"][0]["key"],
        "status": {"checked_at": "2026-10-29"},
        "outcomes": [
            {
                "key": "o1",
                "text": "Explain the idea.",
                "locator": "Slide 2",
                "status": "covered",
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

    from tum_mcp.exam_data import read_exam

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
                {**requirement, "status": "covered", "concepts": [held]},
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
    from tum_mcp.study_coverage import sheet_flags

    flags = sheet_flags(load_state(project), read_ledger(project), exam)
    assert [flag["flag"] for flag in flags] == (
        ["unrecorded_sources"] if sheet["sources_without_requirements"] else []
    )
    ledger(
        project, with_exam([{**requirement, "status": "covered", "concepts": ["no-such-entry"]}])
    )
    with pytest.raises(CampusError, match="does not have"):
        build(project, publish=False)
