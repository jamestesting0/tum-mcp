import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.study_content import Block

BLOCK = TypeAdapter(Block)
CODE = "public class Counter {\n    private int count;\n\n    public void increment() {\n    }\n}\n"


def files(**overrides: object) -> dict:
    value = {
        "kind": "files",
        "title": "Files",
        "sources": ["sheet"],
        "key": "counter",
        "description": "A counter.",
        "files": [
            {"path": "src/Counter.java", "code": CODE, "editable": True},
            {"path": "src/Main.java", "code": "class Main {}\n"},
        ],
    }
    return value | overrides


def test_files_blocks_take_safe_relative_paths_only() -> None:
    assert BLOCK.validate_python(files()).kind == "files"
    for path in ("../secret.txt", "/etc/passwd", "src//A.java", ".hidden"):
        with pytest.raises(ValidationError):
            BLOCK.validate_python(files(files=[{"path": path, "code": ""}]))
    with pytest.raises(ValidationError, match="both a file and a folder"):
        BLOCK.validate_python(
            files(files=[{"path": "src", "code": ""}, {"path": "src/A.java", "code": ""}])
        )
    with pytest.raises(ValidationError, match="opens a file"):
        BLOCK.validate_python(files(open="src/Missing.java"))


def test_walkthrough_stops_stay_inside_the_code() -> None:
    code = {
        "kind": "code",
        "title": "C",
        "sources": ["s"],
        "language": "java",
        "code": "a\nb",
        "explanation": "e",
    }
    assert BLOCK.validate_python(
        code | {"walkthrough": [{"lines": "1-2", "note": "n"}]}
    ).walkthrough
    with pytest.raises(ValidationError, match="outside"):
        BLOCK.validate_python(code | {"walkthrough": [{"lines": "2-3", "note": "n"}]})


def test_state_diagrams_check_their_transitions() -> None:
    state = {"kind": "uml", "title": "S", "sources": ["s"], "diagram": "state", "description": "d"}
    states = [
        {"key": "i", "kind": "initial"},
        {"key": "a", "name": "A"},
        {"key": "f", "kind": "final"},
    ]
    ok = [
        {"start": "i", "end": "a"},
        {"start": "a", "end": "a", "label": "tick"},
        {"start": "a", "end": "f"},
    ]
    assert BLOCK.validate_python(state | {"states": states, "transitions": ok}).diagram == "state"
    with pytest.raises(ValidationError, match="leave the initial"):
        BLOCK.validate_python(
            state | {"states": states, "transitions": [{"start": "a", "end": "i"}]}
        )
    with pytest.raises(ValidationError, match="needs a name"):
        BLOCK.validate_python(state | {"states": [{"key": "a"}], "transitions": []})


def exercise(step: dict) -> dict:
    return {
        "course_key": "c",
        "sets": [
            {
                "key": "w",
                "title": "W",
                "exercises": [
                    {
                        "key": "e",
                        "label": "E",
                        "title": "E",
                        "sources": [{"key": "sheet", "sha256": "0" * 64}],
                        "statement": [files()],
                        "objectives": ["o"],
                        "steps": [
                            {"key": "s", "purpose": "p", "prompt": "q", "explanation": "x"} | step
                        ],
                        "solution": {
                            "blocks": [
                                {
                                    "kind": "text",
                                    "title": "S",
                                    "sources": ["sheet"],
                                    "paragraphs": ["a"],
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    }


def test_steps_point_only_at_shown_lines_and_write_only_into_editable_files() -> None:
    ExerciseContent.model_validate(
        exercise({"code": [{"path": "src/Counter.java", "lines": "4-5"}]})
    )
    with pytest.raises(ValidationError, match="does not show"):
        ExerciseContent.model_validate(exercise({"code": [{"path": "src/Other.java"}]}))
    with pytest.raises(ValidationError, match="outside src/Counter.java"):
        ExerciseContent.model_validate(
            exercise({"code": [{"path": "src/Counter.java", "lines": "9"}]})
        )
    write = {"kind": "self_check", "format": "code", "rubric": ["r"], "model_answer": "m"}
    ExerciseContent.model_validate(exercise({"check": write | {"file": "src/Counter.java"}}))
    with pytest.raises(ValidationError, match="editable workspace file"):
        ExerciseContent.model_validate(exercise({"check": write | {"file": "src/Main.java"}}))
    with pytest.raises(ValidationError, match="either"):
        ExerciseContent.model_validate(
            exercise({"check": write | {"file": "src/Counter.java", "starter_code": "x"}})
        )
