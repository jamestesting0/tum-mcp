"""Video Notes commands for the course agent; data commands print JSON."""

import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from tum_mcp.errors import CampusError, Code
from tum_mcp.extension_selection import require_video_notes

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
runtime_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
storyboard_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(runtime_app, name="runtime", help="Check or install the optional render runtime.")
app.add_typer(storyboard_app, name="storyboard", help="Validate storyboards against content.")


class SchemaName(StrEnum):
    STORYBOARD = "storyboard"
    SELECTION = "selection"
    STYLE = "style"
    VOICE = "voice"
    MANIFEST = "manifest"
    TIMING = "timing"


class Review(StrEnum):
    PERFORMED = "performed"
    NOT_PERFORMED = "not-performed"


def _project(project: Path) -> Path:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise CampusError(Code.ACTION_REQUIRED, "Pass the course project folder.")
    return root


def _emit(value: object) -> None:
    if isinstance(value, BaseModel):
        typer.echo(value.model_dump_json(indent=2))
    else:
        typer.echo(json.dumps(value, indent=2, default=str))


@runtime_app.command("status")
def runtime_status(
    json_output: Annotated[bool, typer.Option("--json", help="Print machine-readable status.")] = (
        False
    ),
) -> None:
    """Check host support and render prerequisites without installing anything."""
    from tum_mcp.video_runtime import status

    report = status()
    if json_output:
        _emit(report)
        return
    from tum_mcp.ui import State, heading, status_rows, terminal_console

    console = terminal_console()
    heading(console, "Video runtime", "Manim, Typst and encoder for Video Notes.")
    state = (
        State.READY
        if report.installed
        else State.UNAVAILABLE
        if not report.supported
        else State.ACTION
        if report.missing
        else State.MISSING
    )
    detail = (
        "Installed."
        if report.installed
        else report.reason
        if not report.supported
        else "Run: " + "; ".join(report.commands)
        if report.missing
        else "Run tum-mcp video-notes runtime install."
    )
    status_rows(console, [("Render runtime", state, detail)])


@runtime_app.command("install")
def runtime_install() -> None:
    """Install the hash-locked render runtime in shared user storage."""
    require_video_notes()
    from tum_mcp.video_runtime import install

    _emit(install())


@app.command()
def schema(name: SchemaName) -> None:
    """Print a JSON schema for a Video Notes input or record."""
    from tum_mcp.video_project import schemas

    typer.echo(json.dumps(schemas()[name.value].model_json_schema(), indent=2))


@app.command()
def inspect(
    project: Path,
    video: Annotated[str | None, typer.Option(help="Limit to one video stem.")] = None,
    verify: Annotated[bool, typer.Option(help="Hash published files fully.")] = False,
) -> None:
    """Report planned, stale, pending and published videos. Read-only."""
    from tum_mcp.video_project import inspect as run

    _emit(run(_project(project), stem=video, verify=verify))


@app.command()
def unit(project: Path, key: str) -> None:
    """Print a unit's locators, fingerprints and teaching hash for storyboards. Read-only."""
    from tum_mcp.video_project import unit_locators

    _emit(unit_locators(_project(project), key))


@app.command()
def exercise(project: Path, key: str) -> None:
    """Print prepared SET/EXERCISE source, answers and exact walkthrough locators."""
    from tum_mcp.video_project import exercise_locators

    _emit(exercise_locators(_project(project), key))


@app.command()
def plan(project: Path, selection: Annotated[Path, typer.Option(help="Selection JSON.")]) -> None:
    """Select Study units or Exercises for videos; keep existing video numbers."""
    require_video_notes()
    from tum_mcp.video_project import plan as run

    _emit(run(_project(project), selection.expanduser().resolve()))


@storyboard_app.command("check")
def storyboard_check(project: Path, video: str) -> None:
    """Validate videos/storyboards/VIDEO.json and write its working transcript."""
    require_video_notes()
    from tum_mcp.video_project import check

    report = check(_project(project), video)
    _emit(report)
    if report.errors:
        raise typer.Exit(1)


@app.command()
def narration(
    project: Path,
    video: str,
    profile: Annotated[str, typer.Option(help="Voice profile key from videos/voice.json.")],
) -> None:
    """List narration chunks to synthesize, one audio file per sentence."""
    require_video_notes()
    from tum_mcp.video_project import narration as run

    _emit(run(_project(project), video, profile))


@app.command()
def timing(
    project: Path,
    video: str,
    profile: Annotated[str | None, typer.Option(help="Voice profile key.")] = None,
    silent: Annotated[bool, typer.Option(help="Estimate timing for a silent draft.")] = False,
) -> None:
    """Measure narration audio and lay out beat timing."""
    require_video_notes()
    from tum_mcp.video_project import timing as run

    if silent == (profile is not None):
        raise CampusError(Code.ACTION_REQUIRED, "Pass exactly one of --profile or --silent.")
    _emit(run(_project(project), video, profile=profile, silent=silent))


@app.command()
def render(
    project: Path,
    video: str,
    final: Annotated[bool, typer.Option("--final/--draft", help="Render quality.")] = False,
    jobs: Annotated[int, typer.Option(min=1, max=8, help="Parallel chapter renders.")] = 2,
    max_minutes: Annotated[
        float | None, typer.Option(min=1, help="Stop at a chapter boundary after this time.")
    ] = None,
    run: Annotated[str | None, typer.Option(help="Resume this run id.")] = None,
) -> None:
    """Lint scenes, render chapters, mix narration and check the result."""
    require_video_notes()
    from tum_mcp.video_project import render as start

    summary = start(
        _project(project),
        video,
        quality="final" if final else "draft",
        jobs=jobs,
        max_minutes=max_minutes,
        run=run,
    )
    _emit(summary)
    if not summary.get("ok"):
        raise typer.Exit(1)


@app.command()
def frames(
    project: Path,
    video: str,
    run: Annotated[str, typer.Option(help="Run id.")],
    at: Annotated[str, typer.Option(help="Comma-separated seconds, e.g. 12.5,40")],
) -> None:
    """Write a contact sheet of frames at the given times for visual review."""
    from tum_mcp.video_project import frames as extract

    try:
        times = [float(value) for value in at.split(",") if value.strip()]
    except ValueError:
        raise CampusError(Code.INVALID_RESPONSE, "--at takes comma-separated seconds.") from None
    if not times or len(times) > 24 or any(not math.isfinite(t) or t < 0 for t in times):
        raise CampusError(Code.INVALID_RESPONSE, "Give 1 to 24 non-negative times.")
    _emit({"sheet": extract(_project(project), video, run, times)})


@app.command()
def check(project: Path, video: str, run: Annotated[str, typer.Option(help="Run id.")]) -> None:
    """Re-run media checks for a rendered run."""
    from tum_mcp.video_project import recheck

    report = recheck(_project(project), video, run)
    _emit(report)
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def publish(
    project: Path,
    video: str,
    run: Annotated[str, typer.Option(help="Checked final run id.")],
    teaching_review: Annotated[Path, typer.Option(help="Teaching review notes (Markdown).")],
    visual_review: Annotated[Review, typer.Option(help="Whether frames were inspected.")],
) -> None:
    """Install a checked final run under videos/ and record its receipt."""
    require_video_notes()
    from tum_mcp.video_project import publish as install

    receipt = install(
        _project(project),
        video,
        run,
        teaching_review=teaching_review.expanduser().resolve(),
        visual_review="performed" if visual_review == Review.PERFORMED else "not_performed",
    )
    _emit(receipt)


@app.command()
def acknowledge(
    project: Path,
    video: str,
    review: Annotated[Path, typer.Option(help="Coverage review notes (Markdown).")],
) -> None:
    """Keep a published video after a unit edit that does not touch its teaching."""
    require_video_notes()
    from tum_mcp.video_project import acknowledge as run

    _emit(run(_project(project), video, review.expanduser().resolve()))


@app.command()
def prune(
    project: Path,
    keep: Annotated[int, typer.Option(min=0, max=20, help="Newest idle runs kept per video.")] = 1,
) -> None:
    """Remove older idle runs and caches of older runtimes from videos/.build."""
    from tum_mcp.video_project import prune as run

    _emit(run(_project(project), keep=keep))
