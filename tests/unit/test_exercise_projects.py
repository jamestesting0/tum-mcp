import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.report import project_flags
from tum_mcp.course.content.exercises import Exercise, exercise_revision
from tum_mcp.course.content.study import changed_lines

STARTER = "class Idle {\n    void request() {\n        // TODO\n    }\n}\n"
SOLVED = "class Idle {\n    void request() {\n        controller.open();\n    }\n}\n"
STATE = "abstract class State {\n    abstract void request();\n}\n"


def project(**file_changes: object) -> dict:
    return {
        "kind": "files",
        "key": "project",
        "sources": ["sheet"],
        "description": "The cable car project.",
        "files": [
            {"path": "src/State.java", "code": STATE},
            {"path": "src/Idle.java", "code": STARTER, "editable": True, "solution": SOLVED}
            | file_changes,
        ],
    }


def writing_step(**check_changes: object) -> dict:
    check = {
        "kind": "self_check",
        "format": "code",
        "language": "java",
        "file": "src/Idle.java",
        "rubric": ["Opens the doors."],
        "solution_code": [{"path": "src/Idle.java", "lines": "3"}],
    } | check_changes
    return {
        "key": "s1",
        "purpose": "Write the reaction.",
        "prompt": "Implement `request` in `Idle`.",
        "code": [{"path": "src/Idle.java", "lines": "2-4"}],
        "check": check,
        "explanation": "Idle reacts to a request by opening the doors.",
    }


def exercise(statement: list | None = None, steps: list | None = None, **changes: object) -> dict:
    return {
        "key": "idle",
        "label": "W02E01",
        "title": "State",
        "sources": [{"key": "sheet", "sha256": "0" * 64}],
        "statement": statement or [project()],
        "objectives": ["Implement a state."],
        "steps": steps or [writing_step()],
        "solution": {"answers": [{"code": [{"path": "src/Idle.java", "lines": "3"}]}]},
    } | changes


def test_a_project_exercise_points_steps_and_solution_at_solved_lines() -> None:
    value = Exercise.model_validate(exercise())
    assert project_flags(value, frozenset()) == []
    assert changed_lines(STARTER, SOLVED) == ((3, 3),)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (exercise([project(editable=False)]), "Only an editable file has a solution"),
        (exercise(steps=[writing_step(file=None)]), "belong to a step that writes"),
        (exercise(steps=[writing_step(model_answer="x")]), "instead of a model answer"),
        (
            exercise(steps=[writing_step(solution_code=[{"path": "src/Idle.java", "lines": "9"}])]),
            "outside the solved src/Idle.java",
        ),
        (exercise([project(), project() | {"key": "other"}]), "one project"),
        (
            exercise(
                steps=[
                    writing_step(
                        solution_code=[
                            {
                                "path": "src/Idle.java",
                                "lines": "3",
                                "walkthrough": [{"lines": "2", "note": "Outside."}],
                            }
                        ]
                    )
                ]
            ),
            "outside 3",
        ),
        (exercise([project() | {"rebuilt_because": "Not started."}]), "Only a rebuilt project"),
    ],
)
def test_project_contracts_reject_inconsistent_content(value: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Exercise.model_validate(value)


def kinds(value: dict, programming: frozenset[str] = frozenset()) -> set[str]:
    return {flag["flag"] for flag in project_flags(Exercise.model_validate(value), programming)}


def test_project_flags_name_each_gap() -> None:
    starter_step = writing_step(file=None, solution_code=[], starter_code="class A {}")
    starter_step["check"]["model_answer"] = "class A { int x; }"
    assert kinds(exercise(steps=[starter_step])) == {
        "code_step_without_project",
        "unwritten_editable",
    }
    unsolved = project(solution=None)
    legacy = writing_step(solution_code=[], model_answer="controller.open();")
    assert kinds(exercise([unsolved], [legacy], solution=SOLUTION_BLOCKS)) == {
        "editable_without_solution"
    }
    assert kinds(exercise([project(solution=STARTER + "\n")])) == {"solved_lines_unchanged"}
    rebuilt = project() | {"origin": "rebuilt"}
    assert kinds(exercise([rebuilt]), frozenset({"sheet"})) == {"rebuilt_without_reason"}
    assert (
        kinds(exercise([rebuilt | {"rebuilt_because": "Not started."}]), frozenset({"sheet"}))
        == set()
    )


SOLUTION_BLOCKS = {
    "answers": [
        {
            "blocks": [
                {
                    "kind": "code",
                    "sources": ["sheet"],
                    "language": "java",
                    "code": "x();",
                    "explanation": "Opens.",
                }
            ]
        }
    ]
}


def test_legacy_project_content_keeps_its_shape_and_revision() -> None:
    legacy = exercise(
        [project(solution=None)],
        [writing_step(solution_code=[], model_answer="controller.open();")],
        solution=SOLUTION_BLOCKS,
    )
    value = Exercise.model_validate(legacy)
    dumped = value.model_dump(mode="json")
    block, check = dumped["statement"][0], dumped["steps"][0]["check"]
    assert {"origin", "rebuilt_because"}.isdisjoint(block)
    assert "solution" not in block["files"][1] and "solution_code" not in check
    assert exercise_revision(value) == exercise_revision(
        Exercise.model_validate(value.model_dump())
    )
