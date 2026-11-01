"""Prepared Study and Exercise source projections shared by the video workflow."""

from dataclasses import dataclass
from pathlib import Path

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import Exercise, ExerciseContent
from tum_mcp.exercise_data import read_exercises, stale_exercises
from tum_mcp.settings import Frozen
from tum_mcp.study_content import SourceVersion, StudyContent, Unit
from tum_mcp.study_store import load_state
from tum_mcp.video_content import (
    ExerciseLocator,
    ExerciseRef,
    ExerciseStoryboard,
    StoryboardReport,
    _teaching,
    canonical,
    estimate_seconds,
    fingerprint,
    semantic_hash,
    sha256,
    unit_revision,
)


def exercise_hash(exercise: Exercise) -> str:
    value = exercise.model_dump(
        mode="json",
        exclude_none=True,
        exclude={"label", "title", "sources", "kind", "distilled_from", "objectives", "transfer"},
    )
    for step in value["steps"]:
        step.pop("hints", None)
    for name in ("origin", "official_source"):
        value["solution"].pop(name, None)
    return sha256(canonical(_teaching(value)))


@dataclass(frozen=True, slots=True)
class VideoSource:
    identity: str
    data: Unit | Exercise
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

    @property
    def revision(self) -> str:
        match self.data:
            case Unit():
                return unit_revision(self.data)
            case Exercise():
                return exercise_hash(self.data)

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

    def locator_hash(self, locator: ExerciseLocator) -> str | None:
        value = self.resolve(locator)
        match value:
            case None:
                return None
            case Unit():
                return semantic_hash(value)
            case _:
                if locator.kind == "step":
                    data = value.model_dump(mode="json", exclude_none=True, exclude={"hints"})
                    return sha256(canonical(_teaching(data)))
                return fingerprint(value)

    def locators(self) -> tuple[ExerciseLocator, ...]:
        match self.data:
            case Unit():
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
    from tum_mcp.study_build import read_content
    from tum_mcp.video_project import _hash_file

    study_path = app_path(root, "content.json")
    study = read_content(root) if study_path.exists() else None
    exercises = read_exercises(root)
    if study is None and exercises is None:
        raise CampusError(Code.ACTION_REQUIRED, "Prepare Study or Exercises before Video Notes.")
    course_key = study.course_key if study is not None else exercises.course_key
    stale = ()
    if exercises is not None:
        if exercises.course_key != course_key:
            raise CampusError(Code.SCOPE_DENIED, "Exercise and Study course identities differ.")
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
    return VideoSources(
        course_key,
        study,
        exercises,
        _hash_file(study_path) if study is not None else None,
        _hash_file(app_path(root, "exercises.json")) if exercises is not None else None,
        items,
    )


def check_exercise(board: ExerciseStoryboard, source: VideoSource) -> StoryboardReport:
    from tum_mcp.video_teaching import exercise_errors

    errors = exercise_errors(board)
    if source.identity != f"exercises/{board.exercise.key}":
        errors.append("plan.exercise: storyboard does not match the selected exercise")
    if source.teaching_hash != board.exercise_hash:
        errors.append("exercise.stale: prepared problem or solution changed; revise affected beats")
    required = tuple(locator for locator in source.locators() if locator.kind == "answer")
    if board.answers != required:
        errors.append("answer.coverage: required answers must match the complete prepared solution")
    for beat in board.beats():
        for locator in beat.locators:
            actual = source.locator_hash(locator)
            if actual is None:
                errors.append(f"locator.missing {beat.key}: {locator.kind} {locator.ref}")
            elif actual != locator.fingerprint:
                errors.append(f"locator.changed {beat.key}: {locator.kind} {locator.ref}")
    seconds, words = estimate_seconds(board)
    return StoryboardReport(
        video=board.video,
        exercise=board.exercise,
        errors=tuple(errors),
        warnings=(),
        estimated_seconds=seconds,
        words=words,
    )
