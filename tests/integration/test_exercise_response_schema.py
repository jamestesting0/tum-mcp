import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.exercise_content import ExerciseContent, exercise_revision


@pytest.fixture
def responses() -> dict:
    return json.loads((Path(__file__).parents[1] / "fixtures/exercise-responses.json").read_bytes())


def test_all_prepared_response_types_validate_and_compile(responses: dict) -> None:
    from tum_mcp.exercise_data import render_exercises

    value = ExerciseContent.model_validate(responses)
    rendered = render_exercises(value)
    steps = rendered["sets"][0]["exercises"][0]["steps"]
    assert "mathml" in steps[4]["blocks"][0]
    assert steps[5]["check"]["starter_code"].startswith("def add")


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate-cell",
        "row-width",
        "unknown-node",
        "backward-path",
        "unknown-source",
        "infinite",
        "code-on-math",
        "plot-axis",
        "plot-count",
        "plot-bounds",
        "plot-source",
    ],
)
def test_invalid_prepared_responses_fail_before_build(responses: dict, failure: str) -> None:
    exercise = responses["sets"][0]["exercises"][0]
    steps = exercise["steps"]
    if failure == "duplicate-cell":
        steps[3]["check"]["rows"][0]["cells"][1]["key"] = "sum"
    elif failure == "row-width":
        steps[3]["check"]["columns"].append("Extra")
    elif failure == "unknown-node":
        steps[6]["check"]["answers"] = [["missing"]]
    elif failure == "backward-path":
        steps[6]["check"]["answers"] = [["c", "b", "a"]]
    elif failure == "unknown-source":
        steps[4]["blocks"][0]["sources"] = ["missing"]
    elif failure == "infinite":
        steps[3]["check"]["rows"][0]["cells"][0]["answer"] = float("inf")
    elif failure == "plot-axis":
        steps[-1]["check"]["plot"]["x_max"] = -1
    elif failure == "plot-count":
        steps[-1]["check"]["answer"].pop()
    elif failure == "plot-bounds":
        steps[-1]["check"]["answer"][0] = 9
    elif failure == "plot-source":
        steps[-1]["check"]["plot"]["sources"] = ["missing"]
    else:
        steps[4]["check"]["starter_code"] = "Do not execute"
    with pytest.raises(ValidationError):
        ExerciseContent.model_validate(responses)


def test_new_optional_fields_preserve_legacy_learning_revision(responses: dict) -> None:
    # Reconstruct the old canonical algorithm using only pre-existing fields.
    from tum_mcp.study_store import digest

    raw = copy.deepcopy(responses)
    exercise = raw["sets"][0]["exercises"][0]
    exercise["steps"] = exercise["steps"][:3]
    model = ExerciseContent.model_validate(raw).sets[0].exercises[0]
    legacy = model.model_dump(mode="json", exclude={"label", "title", "sources"})
    for step in legacy["steps"]:
        step.pop("blocks")
        if step.get("check", {}).get("kind") == "self_check":
            for field in ("format", "language", "starter_code"):
                step["check"].pop(field)
    legacy["source_keys"] = sorted(source.key for source in model.sources)
    assert exercise_revision(model) == digest(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
    )
