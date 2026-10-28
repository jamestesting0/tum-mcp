import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.exercise_checks import Check
from tum_mcp.exercise_content import ExerciseContent

CHECK = TypeAdapter(Check)


def order(**overrides: object) -> dict:
    value = {
        "kind": "order",
        "language": "java",
        "items": [
            {"key": "a", "code": "List<Integer> copy = new ArrayList<>(items);"},
            {"key": "b", "code": "copy.sort(Comparator.reverseOrder());"},
            {"key": "c", "code": "return copy;"},
            {"key": "d", "code": "items.sort(null);"},
        ],
        "answers": [["a", "b", "c"]],
        "feedback": "Copy before sorting so the caller's list stays unchanged.",
    }
    return value | overrides


def test_order_checks_accept_distractors_and_reject_inconsistent_answers() -> None:
    assert CHECK.validate_python(order()).kind == "order"
    with pytest.raises(ValidationError, match="same items"):
        CHECK.validate_python(order(answers=[["a", "b", "c"], ["a", "b", "d"]]))
    with pytest.raises(ValidationError, match="language"):
        CHECK.validate_python(order(language=None))
    with pytest.raises(ValidationError, match="either text or one line"):
        CHECK.validate_python(
            order(items=[{"key": "a", "text": "x", "code": "y"}, {"key": "b", "text": "z"}])
        )


def test_text_checks_keep_code_answers_literal() -> None:
    check = CHECK.validate_python(
        {
            "kind": "text",
            "format": "code",
            "language": "java",
            "accepted": ["map.get($key)", "map.get( $key )"],
            "feedback": "Look the value up by its key.",
        }
    )
    assert check.case_sensitive and check.whitespace == "collapse"
    with pytest.raises(ValidationError, match="code answers only"):
        CHECK.validate_python(
            {"kind": "text", "language": "java", "accepted": ["x"], "feedback": "f"}
        )


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
                "bank-drill", kind="distilled", distilled_from=["bank"], concepts=["Generics"]
            ),
        )
    )
    assert valid.sets[0].exercises[1].kind == "distilled"
    with pytest.raises(ValidationError, match="names the original"):
        ExerciseContent.model_validate(content(exercise("drill", kind="distilled")))
    with pytest.raises(ValidationError, match="original exercises in this file"):
        ExerciseContent.model_validate(
            content(exercise("drill", kind="distilled", distilled_from=["missing"]))
        )
