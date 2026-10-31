import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.exercise_content import ExerciseContent, NumericCheck, exercise_revision

FIXTURE = Path(__file__).parents[1] / "fixtures/exercises.json"


def test_reviewed_provenance_and_navigation_preserve_learning_revision() -> None:
    # Given reviewed guidance with independent identity and source freshness.
    original = ExerciseContent.model_validate_json(FIXTURE.read_bytes())
    payload = json.loads(FIXTURE.read_bytes())
    payload["sets"][0]["category"] = "Another grouping"
    exercise = payload["sets"][0]["exercises"][0]
    exercise["title"] = "A clearer title"
    for item in payload["sets"][0]["exercises"]:
        item["sources"][0]["sha256"] = "b" * 64
    # When provenance and grouping are updated after source review.
    changed = ExerciseContent.model_validate(payload)
    # Then only a meaningful content change affects learning evidence.
    assert exercise_revision(original.sets[0].exercises[0]) == exercise_revision(
        changed.sets[0].exercises[0]
    )
    exercise["steps"][0]["check"]["answer"] = 4
    semantic = ExerciseContent.model_validate(payload)
    assert exercise_revision(semantic.sets[0].exercises[0]) != exercise_revision(
        original.sets[0].exercises[0]
    )


@pytest.mark.parametrize("answer", [float("inf"), float("nan"), True])
def test_numeric_checks_reject_nonfinite_or_ambiguous_values(answer: float) -> None:
    # A shown answer must be a finite number, never a boolean or infinity.
    with pytest.raises(ValidationError):
        NumericCheck(kind="numeric", answer=answer, feedback="Compare costs.")


@pytest.mark.parametrize("fault", ["duplicate-step", "duplicate-exercise", "source", "execution"])
def test_invalid_exercise_references_or_executable_checks_are_rejected(fault: str) -> None:
    # Given a complete, source-bound synthetic statement.
    payload = json.loads(FIXTURE.read_bytes())
    exercise = payload["sets"][0]["exercises"][0]
    match fault:
        case "duplicate-step":
            exercise["steps"][1]["key"] = exercise["steps"][0]["key"]
        case "duplicate-exercise":
            payload["sets"][0]["exercises"].append(exercise)
        case "source":
            exercise["statement"][0]["sources"] = ["unknown"]
        case "execution":
            exercise["steps"][0]["check"]["evaluate"] = "arbitrary()"
    # When parsing at the authoring boundary, the unsafe contract is rejected.
    with pytest.raises(ValidationError):
        ExerciseContent.model_validate(payload)


def test_an_official_solution_requires_its_declared_source() -> None:
    # Given an authored solution with no evidence of official status.
    payload = json.loads(FIXTURE.read_bytes())
    payload["sets"][0]["exercises"][0]["solution"]["origin"] = "official"
    # When labeling it official, attribution is required.
    with pytest.raises(ValidationError):
        ExerciseContent.model_validate(payload)


def _parted(step_parts: list[str | None]) -> dict:
    payload = json.loads(FIXTURE.read_bytes())
    exercise = payload["sets"][0]["exercises"][0]
    exercise["parts"] = ["(a)", "(b)"]
    answer = exercise["solution"]["answers"][0]
    exercise["solution"]["answers"] = [{**answer, "label": "(a)"}, {**answer, "label": "(b)"}]
    first = exercise["statement"][0]
    first.update(key="cost", title="(a)")
    exercise["statement"].append(
        {
            "kind": "text",
            "key": "decision",
            "title": "(b)",
            "sources": first["sources"],
            "paragraphs": ["Decide whether to replace the previous distance."],
        }
    )
    if any(step_parts):
        exercise["part_blocks"] = {"(a)": "cost", "(b)": "decision"}
    for step, part in zip(exercise["steps"], step_parts, strict=True):
        if part is None:
            step.pop("part", None)
        else:
            step["part"] = part
    return payload


def test_each_part_of_a_multi_part_exercise_gets_its_own_guide() -> None:
    # Steps grouped by part, in the order of the parts, give one guide per part.
    ExerciseContent.model_validate(_parted(["(a)", "(a)", "(b)"]))
    # Steps without parts keep one shared guide.
    ExerciseContent.model_validate(_parted([None, None, None]))


@pytest.mark.parametrize(
    "step_parts",
    [["(a)", None, "(b)"], ["(a)", "(a)", "(a)"], ["(b)", "(a)", "(a)"], ["(a)", "(b)", "(a)"]],
)
def test_part_guides_must_cover_every_part_in_order(step_parts: list[str | None]) -> None:
    with pytest.raises(ValidationError):
        ExerciseContent.model_validate(_parted(step_parts))


@pytest.mark.parametrize("fault", ["missing", "unknown", "untitled", "reversed", "duplicate"])
def test_part_guides_require_unambiguous_statement_anchors(fault: str) -> None:
    payload = _parted(["(a)", "(a)", "(b)"])
    exercise = payload["sets"][0]["exercises"][0]
    match fault:
        case "missing":
            exercise["part_blocks"].pop("(b)")
        case "unknown":
            exercise["part_blocks"]["(a)"] = "absent"
        case "untitled":
            exercise["statement"][0].pop("title")
        case "reversed":
            exercise["part_blocks"] = {"(a)": "decision", "(b)": "cost"}
        case "duplicate":
            exercise["part_blocks"]["(b)"] = "cost"
    with pytest.raises(ValidationError):
        ExerciseContent.model_validate(payload)
