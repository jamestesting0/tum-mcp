"""Trusted local commands supporting the study skills. Campus access stays in read tools."""

import json
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.course_app_paths import app_folder, app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_comment_cli import app as comments_app
from tum_mcp.study_publish_cli import app as publish_app

app = typer.Typer(invoke_without_command=True, pretty_exceptions_show_locals=False)
app.add_typer(comments_app, name="comments", help="Read and address local passage comments.")
app.add_typer(
    publish_app, name="publish", help="Publish a study website in a private GitHub repository."
)


@app.callback()
def launch(
    context: typer.Context,
    port: Annotated[int, typer.Option(min=0, max=65535, help="Local app port.")] = 8765,
) -> None:
    """Open this course's study app, or run a study management command."""
    if context.invoked_subcommand is None:
        from tum_mcp.study_preview import serve as preview

        preview(Path.cwd(), port, open_browser=True)


@app.command()
def template() -> None:
    """Describe the packaged study starter; build installs it without overwriting edits."""
    from tum_mcp.study_build import TEMPLATE_FILES
    from tum_mcp.study_store import digest

    source = files("tum_mcp") / "bundled/course_app/site"
    hashes = {name: digest((source / name).read_bytes()) for name in TEMPLATE_FILES}
    typer.echo(
        json.dumps(
            {
                "template": "course_app/site",
                "revision": digest(json.dumps(hashes, sort_keys=True).encode()),
                "files": list(TEMPLATE_FILES),
                "author": "app/content.json",
                "exercise_author": "app/exercises.json",
                "install": "tum-mcp study build PROJECT",
                "synthetic_preview": "tum-mcp study demo PROJECT",
            },
            indent=2,
        )
    )


@app.command()
def init(
    project: Path,
    course: Annotated[str, typer.Option(help="Required, explicitly chosen course title.")],
    snapshot: Annotated[Path, typer.Option(help="Validated source snapshot JSON.")],
) -> None:
    """Bind one chosen course and initialize its local study inventory."""
    from tum_mcp.study_sync import sync

    if not course.strip():
        raise CampusError(Code.ACTION_REQUIRED, "An explicit course input is required.")
    report = sync(project, snapshot, course_input=course)
    typer.echo(json.dumps(asdict(report), indent=2))
    if report.conflicts:
        raise typer.Exit(2)


@app.command(name="sync")
def synchronize(project: Path, snapshot: Annotated[Path, typer.Option()]) -> None:
    """Reconcile one course snapshot; preserve edits and incomplete source checks."""
    from tum_mcp.study_sync import sync

    report = sync(project, snapshot)
    typer.echo(json.dumps(asdict(report), indent=2))
    if report.conflicts:
        raise typer.Exit(2)


@app.command()
def status(project: Path) -> None:
    """Choose initialization, synchronization or local recovery without writing files."""
    from tum_mcp.study_status import project_status

    typer.echo(project_status(project).model_dump_json(indent=2))


@app.command()
def upgrade(project: Path) -> None:
    """Move legacy private course state/docs to .tum-mcp without changing the website."""
    from tum_mcp.study_store import private_folder, upgrade_private

    root = project.expanduser().resolve()
    upgrade_private(root)
    typer.echo(
        json.dumps(
            {
                "private_folder": private_folder(root),
                "preserved": "state, comments, publication settings and user files",
            }
        )
    )


@app.command()
def inspect(project: Path) -> None:
    """Show course identity, source coverage and units that need regeneration."""
    from tum_mcp.course_context import context_review
    from tum_mcp.exercise_data import read_exercises, stale_exercises
    from tum_mcp.lecture_data import lecture_health, read_lectures, stale_lectures
    from tum_mcp.study_build import read_content, stale_units
    from tum_mcp.study_store import load_state, private_folder

    root = project.expanduser().resolve()
    state = load_state(root)
    stale = (
        stale_units(root, state, read_content(root))
        if app_path(root, "content.json").is_file()
        else ()
    )
    exercises = read_exercises(root)
    lectures = read_lectures(root)
    typer.echo(
        json.dumps(
            {
                "course": state.course.model_dump(mode="json"),
                "generation": state.generation,
                "private_folder": private_folder(root),
                "course_context": context_review(root, state).model_dump(mode="json"),
                "coverage": [item.model_dump(mode="json") for item in state.coverage],
                "resources": len(state.resources),
                "content_path": f"{app_folder(root)}/content.json",
                "exercises_path": f"{app_folder(root)}/exercises.json",
                "lectures_path": f"{app_folder(root)}/lectures.json",
                "lectures": len(lectures.lectures) if lectures else 0,
                "stale_lectures": stale_lectures(root, state, lectures) if lectures else (),
                "lecture_evidence": lecture_health(root, lectures) if lectures else (),
                "stale_units": stale,
                "stale_exercises": stale_exercises(root, state, exercises) if exercises else (),
            },
            indent=2,
        )
    )


@app.command()
def build(
    project: Path,
    upgrade_layout: Annotated[
        bool,
        typer.Option(help="Explicitly upgrade a verified study/ layout to app/ with a backup."),
    ] = False,
    local_only: Annotated[
        bool, typer.Option(help="Skip configured GitHub publishing for this build.")
    ] = False,
) -> None:
    """Validate current source-linked content and build the local study app."""
    from tum_mcp.study_build import build as build_site

    result = build_site(project, publish=not local_only, upgrade_layout=upgrade_layout)
    typer.echo(json.dumps(asdict(result), indent=2))
    if result.publication is not None and result.publication.status in {"pending", "failed"}:
        raise typer.Exit(2)


@app.command()
def schema(kind: Literal["snapshot", "content", "exercises", "lectures"]) -> None:
    """Print the machine-readable input schema for the calling agent."""
    from tum_mcp.study_content import StudyContent
    from tum_mcp.study_models import Snapshot

    match kind:
        case "snapshot":
            result = Snapshot.model_json_schema()
        case "content":
            result = StudyContent.model_json_schema()
        case "exercises":
            from tum_mcp.exercise_content import ExerciseContent

            result = ExerciseContent.model_json_schema()
        case "lectures":
            from tum_mcp.extensions import require_lecture
            from tum_mcp.lecture_content import LectureContent

            require_lecture()
            result = LectureContent.model_json_schema()
        case unreachable:
            assert_never(unreachable)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def serve(project: Path, port: Annotated[int, typer.Option(min=0, max=65535)] = 8765) -> None:
    """Preview the prepared app and local comments without external hosting or logs."""
    from tum_mcp.study_preview import serve as preview

    preview(project, port)


@app.command()
def demo(project: Path) -> None:
    """Create a minimal component-template preview, not a teaching example."""
    from tum_mcp.study_build import build as build_site
    from tum_mcp.study_store import Write, apply, read_bytes
    from tum_mcp.study_sync import read_snapshot, sync

    root = project.expanduser().resolve()
    example = Path(str(files("tum_mcp") / "bundled/course_app/example"))
    writes = []
    for name in ("content.json", "exercises.json"):
        desired = (example / name).read_bytes()
        before = read_bytes(app_path(root, name))
        if before is not None and before != desired:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Existing edited content was preserved.")
        writes.append(Write(f"{app_folder(root)}/{name}", before, desired))
    snapshot = example / "snapshot.json"
    sync(root, snapshot, course_input=read_snapshot(snapshot).course.title)
    apply(root, tuple(writes))
    typer.echo(json.dumps(asdict(build_site(root)), indent=2))
    typer.echo(
        "Component template only; not necessarily a good teaching example. "
        "Run tum-mcp study to open it."
    )
