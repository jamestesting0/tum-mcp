"""Prepared Study, Exercise and Exam pattern sources shared by the video workflow."""

from dataclasses import dataclass
from pathlib import Path

from tum_mcp.course.content.exam import ExamContent, Pattern
from tum_mcp.course.content.exercise_data import read_exercises, stale_exercises
from tum_mcp.course.content.exercises import Exercise, ExerciseContent
from tum_mcp.course.content.store import document_digest, present
from tum_mcp.course.content.study import SourceVersion, StudyContent, Unit
from tum_mcp.course.media.sources import exercise_hash, missing, part_fingerprint, teaching_hash
from tum_mcp.course.media.speech import spoken
from tum_mcp.course.media.video_content import (
    ExerciseLocator,
    ExerciseRef,
    ExerciseStoryboard,
    Locator,
    PatternStoryboard,
    StoryboardReport,
    estimate_seconds,
    fingerprint,
    semantic_hash,
    unit_revision,
)
from tum_mcp.course.project.store import load_state
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


@dataclass(frozen=True, slots=True)
class VideoSource:
    identity: str
    data: Unit | Exercise | Pattern
    exercise: ExerciseRef | None = None
    study: StudyContent | None = None
    stale: bool = False

    @property
    def teaching_hash(self) -> str:
        match self.data:
            case Unit():
                return semantic_hash(self.data)
            case Exercise():
                return exercise_hash(self.data)
            case Pattern():
                return teaching_hash(self.data)

    @property
    def revision(self) -> str:
        match self.data:
            case Unit():
                return unit_revision(self.data)
            case Exercise():
                return exercise_hash(self.data)
            case Pattern():
                return teaching_hash(self.data)

    @property
    def source_references(self) -> tuple[SourceVersion, ...]:
        return self.data.sources

    def resolve(self, locator: ExerciseLocator) -> Frozen | None:
        match self.data:
            case Exercise() as exercise:
                match locator.kind:
                    case "statement" | "answer" | "solution_note":
                        index = int(locator.ref.split("[")[1][:-1])
                        values = {
                            "statement": exercise.statement,
                            "answer": exercise.solution.answers,
                            "solution_note": exercise.solution.notes,
                        }[locator.kind]
                        return values[index] if index < len(values) else None
                    case "step":
                        return next((s for s in exercise.steps if s.key == locator.ref), None)
                    case "prerequisite":
                        unit_key, _, block_key = locator.ref.partition("/")
                        declared = any(
                            p.unit == unit_key and (p.block or "") == block_key
                            for p in exercise.prerequisites
                        )
                        if not declared or self.study is None:
                            return None
                        unit = next((u for u in self.study.units if u.key == unit_key), None)
                        if unit is None or not block_key:
                            return unit
                        return next((b for b in unit.blocks if b.key == block_key), None)
            case Unit():
                return None

    def locator_hash(self, locator: ExerciseLocator | Locator) -> str | None:
        if isinstance(self.data, Pattern):
            return part_fingerprint(self.data, locator.kind, locator.ref)
        if isinstance(locator, Locator):
            return None
        value = self.resolve(locator)
        match value:
            case None:
                return None
            case Unit():
                return semantic_hash(value)
            case _:
                if isinstance(self.data, Exercise) and locator.kind in {
                    "statement",
                    "step",
                    "answer",
                }:
                    return part_fingerprint(self.data, locator.kind, locator.ref)
                return fingerprint(value)

    def locators(self) -> tuple[ExerciseLocator, ...]:
        match self.data:
            case Unit() | Pattern():
                return ()
            case Exercise() as exercise:
                addresses = [
                    *(("statement", f"statement[{i}]") for i in range(len(exercise.statement))),
                    *(("step", step.key) for step in exercise.steps),
                    *(("answer", f"answers[{i}]") for i in range(len(exercise.solution.answers))),
                    *(
                        ("solution_note", f"notes[{i}]")
                        for i in range(len(exercise.solution.notes))
                    ),
                    *(
                        ("prerequisite", f"{p.unit}/{p.block}" if p.block else p.unit)
                        for p in exercise.prerequisites
                    ),
                ]
                result = []
                for kind, ref in addresses:
                    probe = ExerciseLocator(kind=kind, ref=ref, fingerprint="0" * 64)
                    actual = self.locator_hash(probe)
                    if actual is not None:
                        result.append(probe.model_copy(update={"fingerprint": actual}))
                return tuple(result)


@dataclass(frozen=True, slots=True)
class VideoSources:
    course_key: str
    study: StudyContent | None
    exercises: ExerciseContent | None
    content_sha256: str | None
    exercises_sha256: str | None
    items: dict[str, VideoSource]
    exam: ExamContent | None = None
    exam_sha256: str | None = None

    def get(self, key: str) -> VideoSource:
        item = self.items.get(key)
        if item is None:
            raise CampusError(Code.STALE_RESULT, f"Prepared source '{key}' was removed or moved.")
        if item.stale:
            raise CampusError(
                Code.STALE_RESULT, f"Source material for '{key}' changed; prepare Exercises first."
            )
        return item


def read_sources(root: Path) -> VideoSources:
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.content.exam_data import read_exam

    study = read_content(root) if present(root, "study") else None
    exercises = read_exercises(root)
    exam = read_exam(root)
    documents = [d for d in (study, exercises, exam) if d is not None]
    if not documents:
        raise CampusError(
            Code.ACTION_REQUIRED, "Prepare Study, Exercises or Exam before Video Notes."
        )
    course_key = documents[0].course_key
    if any(document.course_key != course_key for document in documents):
        raise CampusError(Code.SCOPE_DENIED, "Study, Exercise and Exam course identities differ.")
    stale = ()
    if exercises is not None:
        stale = stale_exercises(root, load_state(root), exercises)
    items = (
        {f"study/{unit.key}": VideoSource(f"study/{unit.key}", unit) for unit in study.units}
        if study
        else {}
    )
    if exercises is not None:
        for group in exercises.sets:
            for exercise in group.exercises:
                ref = ExerciseRef(set=group.key, exercise=exercise.key)
                key = f"exercises/{ref.key}"
                items[key] = VideoSource(key, exercise, ref, study, exercise.key in stale)
    for pattern in exam.patterns if exam else ():
        key = f"exam/patterns/{pattern.key}"
        items[key] = VideoSource(key, pattern)
    return VideoSources(
        course_key,
        study,
        exercises,
        document_digest(root, "study") if study is not None else None,
        document_digest(root, "exercises") if exercises is not None else None,
        items,
        exam,
        document_digest(root, "exam") if exam is not None else None,
    )


def check_pattern(board: PatternStoryboard, source: VideoSource) -> StoryboardReport:
    from tum_mcp.course.media.video_teaching import pattern_errors

    errors = pattern_errors(board, source.data if isinstance(source.data, Pattern) else None)
    if source.identity != f"exam/patterns/{board.pattern}":
        errors.append("plan.pattern: storyboard does not match the selected pattern")
    if source.teaching_hash != board.pattern_hash:
        errors.append("pattern.stale: the prepared pattern changed; revise affected beats")
    placed = [(beat.key, locator) for beat in board.beats() for locator in beat.locators]
    placed += [("left_to_page", item.locator) for item in board.left_to_page]
    for where, locator in placed:
        actual = source.locator_hash(locator)
        if actual is None:
            errors.append(f"locator.missing {where}: {locator.kind} {locator.ref}")
        elif actual != locator.fingerprint:
            errors.append(f"locator.changed {where}: {locator.kind} {locator.ref}")
    if isinstance(source.data, Pattern):
        shown = {(loc.kind, loc.ref) for beat in board.beats() for loc in beat.locators}
        left = {(item.locator.kind, item.locator.ref) for item in board.left_to_page}
        if gaps := missing(source.data, shown, left):
            errors.append(
                "coverage.missing: "
                + ", ".join(gaps)
                + "; present them or leave them to the page with a reason"
            )
    warnings: list[str] = []
    for chapter in board.chapters:
        for index, beat in enumerate(chapter.beats):
            found, notes = spoken(beat.key, beat.narration, opens=index == 0)
            errors.extend(found)
            warnings.extend(notes)
    seconds, words = estimate_seconds(board)
    return StoryboardReport(
        video=board.video,
        pattern=board.pattern,
        errors=tuple(errors),
        warnings=tuple(warnings),
        estimated_seconds=seconds,
        words=words,
    )


def check_exercise(board: ExerciseStoryboard, source: VideoSource) -> StoryboardReport:
    from tum_mcp.course.media.video_teaching import exercise_errors

    errors = exercise_errors(board)
    if source.identity != f"exercises/{board.exercise.key}":
        errors.append("plan.exercise: storyboard does not match the selected exercise")
    if source.teaching_hash != board.exercise_hash:
        errors.append("exercise.stale: prepared problem or solution changed; revise affected beats")
    required = tuple(locator for locator in source.locators() if locator.kind == "answer")
    if board.answers != required:
        errors.append("answer.coverage: required answers must match the complete prepared solution")
    warnings: list[str] = []
    placed = [(beat.key, locator) for beat in board.beats() for locator in beat.locators]
    placed += [("left_to_page", item.locator) for item in board.left_to_page]
    for where, locator in placed:
        actual = source.locator_hash(locator)
        if actual is None:
            errors.append(f"locator.missing {where}: {locator.kind} {locator.ref}")
        elif actual != locator.fingerprint:
            errors.append(f"locator.changed {where}: {locator.kind} {locator.ref}")
    if isinstance(source.data, Exercise):
        shown = {(loc.kind, loc.ref) for beat in board.beats() for loc in beat.locators}
        left = {(item.locator.kind, item.locator.ref) for item in board.left_to_page}
        if gaps := missing(source.data, shown, left):
            errors.append(
                "coverage.missing: "
                + ", ".join(gaps)
                + "; present them or leave them to the page with a reason"
            )
    for chapter in board.chapters:
        for index, beat in enumerate(chapter.beats):
            found, notes = spoken(beat.key, beat.narration, opens=index == 0)
            errors.extend(found)
            warnings.extend(notes)
    seconds, words = estimate_seconds(board)
    return StoryboardReport(
        video=board.video,
        exercise=board.exercise,
        errors=tuple(errors),
        warnings=tuple(warnings),
        estimated_seconds=seconds,
        words=words,
    )
