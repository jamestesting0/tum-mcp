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


@pytest.mark.parametrize(
    "answer,tolerance",
    [(float("inf"), 0), (float("nan"), 0), (3, -1), (3, float("inf")), (True, 0)],
)
def test_numeric_checks_reject_nonfinite_or_ambiguous_values(
    answer: float, tolerance: float
) -> None:
    # Given untrusted deterministic check data.
    # When it cannot represent a finite numeric answer with explicit absolute tolerance.
    with pytest.raises(ValidationError):
        NumericCheck(kind="numeric", answer=answer, tolerance=tolerance, feedback="Compare costs.")


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
