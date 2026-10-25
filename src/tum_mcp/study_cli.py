"""Trusted local commands supporting the study skills. Campus access stays in read tools."""

import json
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer

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

    source = files("tum_mcp") / "bundled/skills/prepare-study/assets/site"
    hashes = {name: digest((source / name).read_bytes()) for name in TEMPLATE_FILES}
    typer.echo(
        json.dumps(
            {
                "template": "prepare-study/assets/site",
                "revision": digest(json.dumps(hashes, sort_keys=True).encode()),
                "files": list(TEMPLATE_FILES),
                "author": "study/content.json",
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
def inspect(project: Path) -> None:
    """Show course identity, source coverage and units that need regeneration."""
    from tum_mcp.study_build import read_content, stale_units
    from tum_mcp.study_store import confined, load_state

    root = project.expanduser().resolve()
    state = load_state(root)
    stale = (
        stale_units(root, state, read_content(root))
        if confined(root, "study/content.json").is_file()
        else ()
    )
    typer.echo(
        json.dumps(
            {
                "course": state.course.model_dump(mode="json"),
                "generation": state.generation,
                "coverage": [item.model_dump(mode="json") for item in state.coverage],
                "resources": len(state.resources),
                "stale_units": stale,
            },
            indent=2,
        )
    )


@app.command()
def build(
    project: Path,
    local_only: Annotated[
        bool, typer.Option(help="Skip configured GitHub publishing for this build.")
    ] = False,
) -> None:
    """Validate current source-linked content and build the local study app."""
    from tum_mcp.study_build import build as build_site

    result = build_site(project, publish=not local_only)
    typer.echo(json.dumps(asdict(result), indent=2))
    if result.publication is not None and result.publication.status in {"pending", "failed"}:
        raise typer.Exit(2)


@app.command()
def schema(kind: Literal["snapshot", "content"]) -> None:
    """Print the machine-readable input schema for the calling agent."""
    from tum_mcp.study_content import StudyContent
    from tum_mcp.study_models import Snapshot

    match kind:
        case "snapshot":
            result = Snapshot.model_json_schema()
        case "content":
            result = StudyContent.model_json_schema()
        case unreachable:
            assert_never(unreachable)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def serve(project: Path, port: Annotated[int, typer.Option(min=0, max=65535)] = 8765) -> None:
    """Preview study/ and save local passage comments, without external hosting or logs."""
    from tum_mcp.study_preview import serve as preview

    preview(project, port)


@app.command()
def demo(project: Path) -> None:
    """Create the synthetic Algorithms & Graphs course for local design review."""
    from tum_mcp.study_build import build as build_site
    from tum_mcp.study_store import Write, apply, confined, read_bytes
    from tum_mcp.study_sync import sync

    root = project.expanduser().resolve()
    example = Path(str(files("tum_mcp") / "bundled/skills/prepare-study/assets/example"))
    desired = (example / "content.json").read_bytes()
    target = confined(root, "study/content.json")
    before = read_bytes(target)
    if before is not None and before != desired:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Existing edited study content was preserved.")
    sync(root, example / "snapshot.json", course_input="Algorithms & Graphs")
    apply(root, (Write("study/content.json", before, desired),))
    typer.echo(json.dumps(asdict(build_site(root)), indent=2))
    typer.echo("Synthetic course only. Run tum-mcp study inside the project to open it.")
