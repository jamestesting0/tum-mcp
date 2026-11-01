"""Structural teaching checks shared by the two prepared video source variants."""

from itertools import groupby

from tum_mcp.video_content import ExerciseStoryboard, Storyboard


def lesson_errors(board: Storyboard) -> list[str]:
    beats = board.beats()
    errors = []
    if beats[0].kind != "overview":
        errors.append("lesson.overview: open with the learning question and section map")
    if beats[-1].kind != "recap":
        errors.append("lesson.closure: finish by connecting the taught results")
    teaching = [beat for beat in beats if beat.kind not in {"overview", "recap"}]
    if not teaching:
        errors.append("lesson.teaching: the overview and recap need an actual explanation between")
    for beat in teaching:
        if beat.point is None:
            errors.append(
                f"lesson.point {beat.key}: name the knowledge point taught in this section"
            )
    return errors


def exercise_errors(board: ExerciseStoryboard) -> list[str]:
    errors = []
    if board.beats()[0].kind != "setup":
        errors.append("exercise.setup: establish the actual problem before solving it")
    groups = groupby(board.chapters, key=lambda chapter: chapter.answer)
    for answer, chapters in groups:
        if answer is None:
            continue
        beats = [beat for chapter in chapters for beat in chapter.beats]
        kinds = [beat.kind for beat in beats]
        required = ("setup", "strategy", "work", "verify", "answer")
        missing = [kind for kind in required if kind not in kinds]
        if missing:
            errors.append(f"exercise.stages {answer.ref}: missing {', '.join(missing)}")
            continue
        first_work = kinds.index("work")
        last_work = len(kinds) - 1 - kinds[::-1].index("work")
        last_verify = len(kinds) - 1 - kinds[::-1].index("verify")
        first_answer = kinds.index("answer")
        if not (
            kinds[0] == "setup"
            and kinds.index("strategy") < first_work
            and last_work < last_verify < first_answer
            and kinds[-1] == "answer"
        ):
            errors.append(
                f"exercise.order {answer.ref}: establish the task, choose a method, "
                "work, verify, then emphasize the result"
            )
    return errors
