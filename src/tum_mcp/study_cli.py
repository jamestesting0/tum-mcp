"""Trusted local commands supporting the study skills. Campus access stays in read tools."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.errors import CampusError, Code

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


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
def build(project: Path) -> None:
    """Validate current source-linked content and build the local study app."""
    from tum_mcp.study_build import build as build_site

    typer.echo(json.dumps(asdict(build_site(project)), indent=2))


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
    """Preview only study/ on this computer, without request logging or external hosting."""
    from tum_mcp.study_preview import serve as preview

    preview(project, port)


@app.command()
def demo(project: Path) -> None:
    """Create the synthetic Algorithms & Graphs course for local design review."""
    from importlib.resources import files

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
    typer.echo("Synthetic course only. Preview with: tum-mcp study serve PROJECT")
