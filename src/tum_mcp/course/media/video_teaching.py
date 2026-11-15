"""Structural teaching checks for lesson, exercise and Exam pattern videos."""

import re
from itertools import groupby

from tum_mcp.course.content.exam import Pattern
from tum_mcp.course.media.video_content import (
    Beat,
    ExerciseBeat,
    ExerciseStoryboard,
    PatternBeat,
    PatternStoryboard,
    Storyboard,
)

# Arithmetic or a numeric comparison typed as label text ("0.8 x 1 + 0.2 x 0 = 0.8", "1/2").
# An ASCII hyphen between digits is a range, not a subtraction.
CALCULATION = re.compile(
    r"[\d)]\s*[\u00d7*\u00b7+\u2212/]\s*[(\d]|[=<>\u2264\u2265]\s*[\u2212+-]?\d"
)


def screen_errors(
    beats: tuple[Beat, ...] | tuple[ExerciseBeat, ...] | tuple[PatternBeat, ...],
) -> list[str]:
    return [
        f"screen.calculation {beat.key}: '{item.text}' is mathematics; make it a math item "
        "so it is typeset and can transform step by step"
        for beat in beats
        for item in beat.on_screen
        if item.kind == "label" and item.text and CALCULATION.search(item.text)
    ]


def lesson_errors(board: Storyboard) -> list[str]:
    beats = board.beats()
    errors = screen_errors(beats)
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


def pattern_errors(board: PatternStoryboard, pattern: Pattern | None = None) -> list[str]:
    beats = board.beats()
    errors = screen_errors(beats)
    if beats[0].kind != "cue":
        errors.append("pattern.cue: open with when the pattern applies, from its cues")
    if beats[-1].kind != "recap":
        errors.append("pattern.recap: close by listing the workflow steps")
    needs = {"step": "workflow", "case": "case", "pitfall": "pitfall", "example": "example"}
    for beat in beats:
        kinds = {locator.kind for locator in beat.locators}
        if beat.kind in needs and needs[beat.kind] not in kinds:
            errors.append(
                f"pattern.locator {beat.key}: a {beat.kind} beat locates its {needs[beat.kind]}"
            )
        if beat.kind == "step" and not beat.on_screen:
            errors.append(
                f"pattern.apply {beat.key}: show what this step applies (formula, rule or code)"
            )
        if beat.kind == "pitfall" and len(beat.on_screen) < 2:
            errors.append(f"pattern.pitfall {beat.key}: show the wrong working, then the right one")
    if pattern is None:
        return errors
    steps = len(pattern.workflow)
    # A worked example passing through a step does not teach the step itself.
    taught = {loc.ref for beat in beats if beat.kind == "step" for loc in beat.locators}
    taught |= {item.locator.ref for item in board.left_to_page}
    errors.extend(
        f"pattern.step workflow[{i}]: give this step its own step beat"
        for i in range(steps)
        if f"workflow[{i}]" not in taught
    )
    worked: dict[str, list[int]] = {}
    for beat in beats:
        if beat.kind != "example":
            continue
        example = next(loc.ref for loc in beat.locators if loc.kind == "example")
        worked.setdefault(example, []).extend(
            int(loc.ref[9:-1]) for loc in beat.locators if loc.kind == "workflow"
        )
    for example, order in worked.items():
        gaps = [f"workflow[{i}]" for i in range(steps) if i not in order]
        if order != sorted(order) or gaps:
            errors.append(
                f"pattern.example {example}: work every workflow step in order"
                + (f" (missing {', '.join(gaps)})" if gaps else "")
            )
    return errors


def exercise_errors(board: ExerciseStoryboard) -> list[str]:
    errors = screen_errors(board.beats())
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
