import json
from pathlib import Path
from uuid import uuid4

from study_comments_data import operation
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.comment_models import Create, ExerciseAnchor
from tum_mcp.course.app.comments import change_comment, read_comments
from tum_mcp.course.content.exercise_data import read_exercises
from tum_mcp.course.content.exercises import exercise_revision


def test_v1_comments_upgrade_only_on_mutation_and_keep_legacy_notes(exercise_project: Path) -> None:
    project = exercise_project
    first = operation(project)
    change_comment(project, first)
    path = project / ".tum-mcp/comments.json"
    document = json.loads(path.read_bytes())
    document["schema_version"] = 1
    path.write_text(json.dumps(document))
    before = path.read_bytes()
    current = read_comments(project)
    assert path.read_bytes() == before
    content = read_exercises(project)
    exercise = content.sets[0].exercises[0]
    second = Create(
        op="create",
        id=uuid4(),
        text="Explain this step.",
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        anchor=ExerciseAnchor(
            set_key=content.sets[0].key,
            exercise_key=exercise.key,
            exercise_revision=exercise_revision(exercise),
            step_key=exercise.steps[0].key,
            field="prompt",
            block_title=exercise.title,
            quote=exercise.steps[0].prompt,
        ),
    )
    saved = change_comment(project, second)
    assert saved["schema_version"] == 2
    assert saved["comments"][0] == current["comments"][0]
    result = CliRunner().invoke(
        app,
        [
            "study",
            "comments",
            "list",
            str(project),
            "--view",
            "exercises",
            "--exercise",
            exercise.key,
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["comments"][0]["content_state"] == "current"
