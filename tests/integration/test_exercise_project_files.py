import json
from pathlib import Path

import pytest

from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.projects import drift, pack
from tum_mcp.course.content.store import read_document, write_document
from tum_mcp.course.sources.repository import folder, write_snapshot
from tum_mcp.errors import CampusError

TEMPLATE = {"src/Idle.java": "class Idle {\n    // TODO\n}\n", "src/State.java": "class State {}\n"}


def first_exercise(root: Path) -> dict:
    return read_document(root, "exercises")["sets"][0]["exercises"][0]


def declare_artemis_source(root: Path) -> str:
    document = read_document(root, "exercises")
    exercise = document["sets"][0]["exercises"][0]
    exercise["sources"].append({"key": "artemis-11", "sha256": "1" * 64})
    write_document(root, "exercises", document)
    return exercise["key"]


def test_a_rebuilt_project_is_packed_from_files_on_disk(
    exercise_project: Path, tmp_path: Path
) -> None:
    starter, solved = tmp_path / "starter", tmp_path / "solved"
    (starter / "src").mkdir(parents=True)
    (solved / "src").mkdir(parents=True)
    (starter / "src/Idle.java").write_text(TEMPLATE["src/Idle.java"])
    (solved / "src/Idle.java").write_text("class Idle {\n    void go() {}\n}\n")
    (solved / "src/Moving.java").write_text("class Moving {}\n")
    key = first_exercise(exercise_project)["key"]
    result = pack(
        exercise_project,
        key,
        str(starter),
        origin="rebuilt",
        editable=("src/Idle.java", "src/Moving.java"),
        solutions=solved,
        description="The cable car.",
        rebuilt_because="The student has not started it.",
    )
    assert result["unsolved"] == [] and result["problems"] == []
    block = next(b for b in first_exercise(exercise_project)["statement"] if b["kind"] == "files")
    files = {item["path"]: item for item in block["files"]}
    assert block["origin"] == "rebuilt" and files["src/Moving.java"]["code"] == ""
    assert files["src/Idle.java"]["solution"].startswith("class Idle {\n    void go")


def test_a_repository_project_is_byte_faithful_and_drift_is_flagged(
    exercise_project: Path,
) -> None:
    key = declare_artemis_source(exercise_project)
    write_snapshot(folder(exercise_project, "artemis-11"), "artemis-11", "a" * 40, TEMPLATE)
    result = pack(
        exercise_project, key, "artemis-11", origin="repository", editable=("src/Idle.java",),
        description="The cable car.",
    )  # fmt: skip
    assert result["problems"] == []
    document = read_document(exercise_project, "exercises")
    block = next(
        b for b in document["sets"][0]["exercises"][0]["statement"] if b["kind"] == "files"
    )
    assert block["sources"] == ["artemis-11"]
    assert {f["path"]: f["code"] for f in block["files"]} == TEMPLATE
    block["files"][1]["code"] = "class State { int changed; }\n"
    block["files"].append({"path": "src/Extra.java", "code": "class Extra {}\n"})
    exercise = ExerciseContent.model_validate(document).sets[0].exercises[0]
    assert drift(exercise_project, exercise) == [
        "src/State.java differs from the template.",
        "src/Extra.java is not in the template; only a new editable file that starts empty "
        "may be added.",
    ]


def test_a_repository_project_needs_its_snapshot(exercise_project: Path) -> None:
    key = declare_artemis_source(exercise_project)
    with pytest.raises(CampusError, match="study repository"):
        pack(exercise_project, key, "artemis-11", origin="repository", editable=())
    with pytest.raises(CampusError, match="snapshot"):
        pack(exercise_project, key, str(exercise_project), origin="repository", editable=())
    assert json.dumps(first_exercise(exercise_project)).count('"kind": "files"') == 0
