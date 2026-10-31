import pytest

from tum_mcp.video_content import ExerciseStoryboard
from tum_mcp.video_teaching import exercise_errors


def walkthrough(kinds: tuple[str, ...], split: int | None = None) -> ExerciseStoryboard:
    answer = {"kind": "answer", "ref": "answers[0]", "fingerprint": "a" * 64}
    beats = [
        {
            "key": f"b{i:02d}",
            "kind": kind,
            "narration": ["A source-bound solution step."],
            "intent": "Explain the prepared solution.",
            "locators": [answer],
        }
        for i, kind in enumerate(kinds, 1)
    ]
    chapters = [{"key": "c01", "title": "Part one", "answer": answer, "beats": beats}]
    if split is not None:
        chapters[0]["beats"] = beats[:split]
        chapters.append(
            {
                "key": "c02",
                "title": "Continue the same part",
                "answer": answer,
                "beats": beats[split:],
            }
        )
    return ExerciseStoryboard.model_validate(
        {
            "video": "01_walkthrough",
            "exercise": {"set": "sheet", "exercise": "problem"},
            "exercise_hash": "b" * 64,
            "title": "Walkthrough",
            "language": "en",
            "answers": [answer],
            "chapters": chapters,
        }
    )


def test_answer_mapping_does_not_substitute_for_a_worked_solution() -> None:
    errors = exercise_errors(walkthrough(("work",)))
    assert any(error.startswith("exercise.setup:") for error in errors)
    assert any(error.startswith("exercise.stages answers[0]:") for error in errors)


@pytest.mark.parametrize(
    "kinds",
    [
        ("setup", "work", "strategy", "verify", "answer"),
        ("setup", "strategy", "verify", "work", "answer"),
        ("setup", "strategy", "work", "answer", "verify"),
    ],
)
def test_answer_is_emphasized_after_reasoning_and_final_verification(
    kinds: tuple[str, ...],
) -> None:
    assert any(
        error.startswith("exercise.order answers[0]:")
        for error in exercise_errors(walkthrough(kinds))
    )


def test_one_part_can_span_chapters_and_several_worked_steps() -> None:
    board = walkthrough(("setup", "strategy", "work", "work", "verify", "answer"), split=3)
    assert exercise_errors(board) == []
