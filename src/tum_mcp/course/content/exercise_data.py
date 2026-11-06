"""Read prepared exercise content and verify its existing local source inventory."""

import json
from pathlib import Path

from pydantic import JsonValue, ValidationError

from tum_mcp.course.content.exercises import ExerciseContent, exercise_revision
from tum_mcp.course.content.store import locate, read_json
from tum_mcp.course.content.study import StudyContent, compile_formulas, term_markers
from tum_mcp.course.project.models import StudyState
from tum_mcp.course.project.store import confined, digest
from tum_mcp.errors import CampusError, Code


def read_exercises(root: Path) -> ExerciseContent | None:
    body = read_json(root, "exercises")
    if body is None:
        return None
    try:
        return ExerciseContent.model_validate_json(body)
    except ValidationError as error:
        document = json.loads(body)
        locations = [
            locate("exercises", document, item["loc"])
            + f" ({item['msg'].removeprefix('Value error, ')})"
            for item in error.errors(include_input=False)
        ]
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid exercise content: " + "; ".join(locations[:5])
        ) from None


def stale_exercises(root: Path, state: StudyState, content: ExerciseContent) -> tuple[str, ...]:
    if state.course.key != content.course_key:
        raise CampusError(Code.SCOPE_DENIED, "Exercises belong to a different course.")
    resources = {item.resource.key: item for item in state.resources}
    stale: list[str] = []
    for group in content.sets:
        for exercise in group.exercises:
            for source in exercise.sources:
                stored = resources.get(source.key)
                if stored is None or stored.status != "current" or stored.sha256 != source.sha256:
                    stale.append(exercise.key)
                    break
                relative = stored.path
                path = confined(root, relative) if relative else None
                if path is None or not path.is_file() or digest(path.read_bytes()) != source.sha256:
                    stale.append(exercise.key)
                    break
    return tuple(stale)


def check_prerequisites(content: ExerciseContent, study: StudyContent | None) -> None:
    """An absent Study workspace uses inline explanations; broken prepared links fail."""
    if study is None:
        return
    blocks = {unit.key: {block.key for block in unit.blocks if block.key} for unit in study.units}
    for group in content.sets:
        for exercise in group.exercises:
            for prerequisite in exercise.prerequisites:
                if prerequisite.unit not in blocks:
                    raise CampusError(
                        Code.INVALID_RESPONSE, "An exercise links to an unknown Study topic."
                    )
                if prerequisite.block and prerequisite.block not in blocks[prerequisite.unit]:
                    raise CampusError(
                        Code.INVALID_RESPONSE,
                        f"Exercise {exercise.key} links to block {prerequisite.block}, which "
                        f"unit {prerequisite.unit} does not have.",
                    )
    names = study.annotation_names()
    for group in content.sets:
        if term_markers(group.model_dump(mode="json", exclude={"exercises"}), fold=False) & names:
            raise CampusError(
                Code.INVALID_RESPONSE, "Exercise set labels cannot contain annotations."
            )
        for exercise in group.exercises:
            prose = {"steps", "solution"}
            misplaced = (
                term_markers(exercise.model_dump(mode="json", exclude=prose), fold=False) & names
            )
            misplaced |= study.annotation_problems(exercise.model_dump(mode="json", include=prose))
            if misplaced:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Exercise {exercise.key} annotations belong in guide or solution prose: "
                    f"{sorted(misplaced)[:5]}.",
                )
    check_terms(content.model_dump(mode="json"), study, "Exercises")


def check_terms(value: JsonValue, study: StudyContent | None, workspace: str) -> None:
    """Marked terms in other workspaces open Study definitions, so each must exist."""
    if study is None:
        return
    known = {term.casefold() for term in study.definitions()}
    annotations = study.annotation_names() if workspace == "Exercises" else set()
    missing = term_markers(value, fold=False) - annotations
    if unknown := {term for term in missing if term.casefold() not in known}:
        raise CampusError(
            Code.INVALID_RESPONSE,
            f"{workspace} mark terms that Study does not define: {sorted(unknown)[:5]}.",
        )


def render_exercises(content: ExerciseContent) -> dict[str, JsonValue]:
    """Compile safe blocks and attach stable learning revisions for the renderer."""
    from tum_mcp.course.media.video_sources import exercise_hash

    value = compile_formulas(content.model_dump(mode="json", exclude_none=True))
    for group, rendered_group in zip(content.sets, value["sets"], strict=True):
        for exercise, rendered in zip(group.exercises, rendered_group["exercises"], strict=True):
            rendered["revision"] = exercise_revision(exercise)
            rendered["videoRevision"] = exercise_hash(exercise)
    return value
