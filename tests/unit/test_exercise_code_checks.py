import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.exercise_checks import Check
from tum_mcp.exercise_content import ExerciseContent

CHECK = TypeAdapter(Check)


def test_line_ordering_is_not_a_check_kind() -> None:
    with pytest.raises(ValidationError):
        CHECK.validate_python(
            {"kind": "order", "items": [], "answers": [], "feedback": "Write the code instead."}
        )


def test_text_checks_show_one_literal_answer() -> None:
    check = CHECK.validate_python(
        {
            "kind": "text",
            "format": "code",
            "language": "java",
            "answer": "map.get($key)",
            "feedback": "Look the value up by its key.",
        }
    )
    assert check.answer == "map.get($key)"
    with pytest.raises(ValidationError, match="code answers only"):
        CHECK.validate_python({"kind": "text", "language": "java", "answer": "x", "feedback": "f"})
    with pytest.raises(ValidationError):
        CHECK.validate_python({"kind": "text", "accepted": ["x"], "feedback": "f"})


def exercise(key: str, **overrides: object) -> dict:
    value = {
        "key": key,
        "label": key,
        "title": key.title(),
        "sources": [{"key": "sheet", "sha256": "0" * 64}],
        "statement": [
            {"kind": "text", "title": "Task", "sources": ["sheet"], "paragraphs": ["Do it."]}
        ],
        "objectives": ["Apply the idea."],
        "steps": [{"key": "s1", "purpose": "p", "prompt": "Try.", "explanation": "Done."}],
        "solution": {
            "blocks": [
                {"kind": "text", "title": "Solution", "sources": ["sheet"], "paragraphs": ["It."]}
            ]
        },
    }
    return value | overrides


STATEMENT_CODE = {
    "kind": "code",
    "title": "Account",
    "sources": ["sheet"],
    "language": "java",
    "code": "class Account<T> { T id; }",
    "explanation": "Make the id type generic.",
}


def content(*exercises: dict) -> dict:
    return {
        "course_key": "c",
        "sets": [{"key": "w1", "title": "Week 1", "exercises": list(exercises)}],
    }


def test_distilled_practice_names_existing_originals() -> None:
    valid = ExerciseContent.model_validate(
        content(
            exercise("bank"),
            exercise(
                "bank-drill",
                kind="distilled",
                distilled_from=["bank"],
                statement=[STATEMENT_CODE],
            ),
        )
    )
    assert valid.sets[0].exercises[1].kind == "distilled"
    with pytest.raises(ValidationError, match="needs a code snippet, diagram"):
        ExerciseContent.model_validate(
            content(exercise("bank"), exercise("drill", kind="distilled", distilled_from=["bank"]))
        )
    with pytest.raises(ValidationError, match="names the original"):
        ExerciseContent.model_validate(content(exercise("drill", kind="distilled")))
    with pytest.raises(ValidationError, match="original exercises in this file"):
        ExerciseContent.model_validate(
            content(
                exercise(
                    "drill",
                    kind="distilled",
                    distilled_from=["missing"],
                    statement=[STATEMENT_CODE],
                )
            )
        )
