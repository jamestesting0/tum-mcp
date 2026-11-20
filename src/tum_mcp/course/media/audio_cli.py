"""Audio Notes commands for the course agent; data commands print JSON."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from tum_mcp.errors import CampusError, Code
from tum_mcp.extension_selection import audio_notes_enabled

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


class SchemaName(StrEnum):
    CATEGORY = "category"
    VOICE = "voice"


def _ready(project: Path) -> Path:
    if not audio_notes_enabled():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Install the optional Audio Notes extension with tum-mcp install audio-notes.",
        )
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise CampusError(Code.ACTION_REQUIRED, "Pass the course project folder.")
    return root


def _emit(value: object, next_action: str | None = None) -> None:
    if next_action is not None and isinstance(value, dict):
        value = {**value, "next_action": next_action}
    typer.echo(json.dumps(value, indent=2, default=str))


@app.command()
def schema(
    name: Annotated[str | None, typer.Argument()] = None,
    example: Annotated[bool, typer.Option("--example", help="Show an example to copy.")] = False,
) -> None:
    """Print the category script or voice contract, or with --example an example and its rule."""
    from tum_mcp.course.media.audio_project import CategoryScript
    from tum_mcp.course.media.examples import catalogue
    from tum_mcp.course.media.examples import example as show
    from tum_mcp.course.media.video_content import VoiceFile

    if example:
        if name is None or name == "list":
            _emit(sorted(catalogue("audio")))
            return
        rule, value = show("audio", name)
        typer.echo(f"Rule: {rule}", err=True)
        _emit(value)
        return
    if name not in {item.value for item in SchemaName}:
        raise CampusError(Code.ACTION_REQUIRED, "Choose a schema name or use --example list.")
    _emit((CategoryScript if name == SchemaName.CATEGORY else VoiceFile).model_json_schema())


@app.command()
def sources(project: Path) -> None:
    """List Study units, exercises, Exam entries and patterns with their required parts."""
    from tum_mcp.course.media.audio_project import sources as run

    _emit(run(_ready(project)))


@app.command()
def outline(
    project: Path,
    stem: str,
    source: Annotated[
        list[str],
        typer.Option(help="unit:KEY, exercise:SET/KEY, pattern:KEY or concept:KEY; repeatable."),
    ],
    title: Annotated[str | None, typer.Option(help="Track title.")] = None,
) -> None:
    """Write a draft script whose chapters already cover every required part."""
    from tum_mcp.course.media.outline import audio as run

    _emit(
        run(_ready(project), stem, source, title),
        "Replace every Write: sentence, then run check. The request ends with a published "
        "track, not a script.",
    )


@app.command()
def check(project: Path, stem: str) -> None:
    """Validate audio/categories/STEM.json: sources, coverage and speakable sentences."""
    from tum_mcp.course.media.audio_project import check as run

    report = run(_ready(project), stem)
    _emit(
        report,
        None
        if report["errors"]
        else "Review the script as continuous speech, then run narration, synthesize every "
        "listed file and publish.",
    )
    if report["errors"]:
        raise typer.Exit(1)


@app.command()
def narration(project: Path, stem: str) -> None:
    """List the audio file to synthesize for each sentence of a category."""
    from tum_mcp.course.media.audio_project import narration as run

    _emit(run(_ready(project), stem))


@app.command()
def listen(
    project: Path,
    stem: str,
    dispose: Annotated[
        list[str] | None,
        typer.Option("--dispose", help="Record SENTENCE=REASON for a flag in the current report."),
    ] = None,
) -> None:
    """Transcribe a published track and compare it with its script and timing."""
    from tum_mcp.course.media.listening import listen_audio

    _emit(listen_audio(_ready(project), stem, tuple(dispose or ())))


@app.command()
def publish(
    project: Path,
    stem: str,
    teaching_review: Annotated[Path, typer.Option(help="Teaching review notes (Markdown).")],
) -> None:
    """Assemble, check and install one category track with its manifest receipt."""
    from tum_mcp.course.media.audio_project import publish as run

    _emit(
        run(_ready(project), stem, teaching_review.expanduser().resolve()),
        f"Run listen on {stem}; reword what it flags, then publish again.",
    )
