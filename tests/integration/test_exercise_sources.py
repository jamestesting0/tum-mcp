import json
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_build import build


def _data(project: Path) -> dict:
    return json.loads(
        (project / "study/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )


def test_combined_build_includes_prepared_guidance_and_revisions(exercise_project: Path) -> None:
    # Given both authored workspaces bound to reviewed local source bytes.
    before = _data(exercise_project)
    # When the existing builder prepares the combined course.
    build(exercise_project, publish=False)
    data = _data(exercise_project)
    # Then guidance is available without changing Study identities or data.
    assert data["workspaces"] == ["study", "exercises"]
    assert data["units"] == before["units"]
    exercise = data["exercises"]["sets"][0]["exercises"][0]
    assert exercise["steps"][0]["check"]["answer"] == 3
    assert len(exercise["revision"]) == 64


def test_exercises_only_build_requires_no_dummy_study_content(exercise_project: Path) -> None:
    # Given an exercises-only course with the same source inventory.
    (exercise_project / "study/content.json").unlink()
    # When building prepared content.
    build(exercise_project, publish=False)
    # Then the sole available workspace is Exercises, with no authored Study stub.
    assert _data(exercise_project)["workspaces"] == ["exercises"]
    assert _data(exercise_project)["units"] == []
    assert not (exercise_project / "study/content.json").exists()


@pytest.mark.parametrize("fault", ["course", "source"])
def test_invalid_exercise_binding_preserves_the_last_verified_build(
    exercise_project: Path, fault: str
) -> None:
    # Given an edited exercise file that cannot be trusted for this inventory.
    path = exercise_project / "study/exercises.json"
    payload = json.loads(path.read_bytes())
    if fault == "course":
        payload["course_key"] = "another-course"
    else:
        for exercise in payload["sets"][0]["exercises"]:
            exercise["sources"][0]["sha256"] = "b" * 64
    path.write_text(json.dumps(payload))
    before = (exercise_project / "study/data.mjs").read_bytes()
    # When rebuilding, neither a foreign exercise nor stale content can disappear silently.
    with pytest.raises(CampusError) as caught:
        build(exercise_project, publish=False)
    assert caught.value.code == (Code.SCOPE_DENIED if fault == "course" else Code.STALE_RESULT)
    assert (exercise_project / "study/data.mjs").read_bytes() == before
