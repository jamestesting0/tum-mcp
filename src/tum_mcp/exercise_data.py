"""Read prepared exercise content and verify its existing local source inventory."""

from pathlib import Path

from pydantic import JsonValue, ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import ExerciseContent, exercise_revision
from tum_mcp.study_content import StudyContent, render_blocks
from tum_mcp.study_models import StudyState, resolved_material_path
from tum_mcp.study_store import confined, digest


def read_exercises(root: Path) -> ExerciseContent | None:
    path = app_path(root, "exercises.json")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.INVALID_RESPONSE, "Exercise content must be a file below 8 MiB.")
    try:
        return ExerciseContent.model_validate_json(path.read_bytes())
    except ValidationError as error:
        locations = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)]
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid exercise content at: " + ", ".join(locations[:5])
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
                relative = resolved_material_path(state, stored)
                path = confined(root, relative) if relative else None
                if path is None or not path.is_file() or digest(path.read_bytes()) != source.sha256:
                    stale.append(exercise.key)
                    break
    return tuple(stale)


def check_prerequisites(content: ExerciseContent, study: StudyContent | None) -> None:
    """An absent Study workspace uses inline explanations; broken prepared links fail."""
    if study is None:
        return
    units = {unit.key for unit in study.units}
    if any(
        prerequisite.unit not in units
        for group in content.sets
        for exercise in group.exercises
        for prerequisite in exercise.prerequisites
    ):
        raise CampusError(Code.INVALID_RESPONSE, "An exercise links to an unknown Study topic.")


def render_exercises(content: ExerciseContent) -> dict[str, JsonValue]:
    """Compile safe blocks and attach stable learning revisions for the renderer."""
    value = content.model_dump(mode="json", exclude_none=True)
    for group, rendered_group in zip(content.sets, value["sets"], strict=True):
        for exercise, rendered in zip(group.exercises, rendered_group["exercises"], strict=True):
            rendered["revision"] = exercise_revision(exercise)
            rendered["statement"] = render_blocks(exercise.statement)
            rendered["solution"]["blocks"] = render_blocks(exercise.solution.blocks)
            for step, rendered_step in zip(exercise.steps, rendered["steps"], strict=True):
                rendered_step["blocks"] = render_blocks(step.blocks)
    return value
