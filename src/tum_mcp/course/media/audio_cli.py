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


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, indent=2, default=str))


@app.command()
def schema(name: SchemaName) -> None:
    """Print the category script or voice contract."""
    from tum_mcp.course.media.audio_project import CategoryScript
    from tum_mcp.course.media.video_content import VoiceFile

    model = CategoryScript if name == SchemaName.CATEGORY else VoiceFile
    _emit(model.model_json_schema())


@app.command()
def sources(project: Path) -> None:
    """List Study units and Exam cheatsheet entries and patterns with their locators."""
    from tum_mcp.course.media.audio_project import sources as run

    _emit(run(_ready(project)))


@app.command()
def check(project: Path, stem: str) -> None:
    """Validate audio/categories/STEM.json: sources, coverage and speakable sentences."""
    from tum_mcp.course.media.audio_project import check as run

    report = run(_ready(project), stem)
    _emit(report)
    if report["errors"]:
        raise typer.Exit(1)


@app.command()
def narration(project: Path, stem: str) -> None:
    """List the audio file to synthesize for each sentence of a category."""
    from tum_mcp.course.media.audio_project import narration as run

    _emit(run(_ready(project), stem))


@app.command()
def listen(project: Path, stem: str) -> None:
    """Transcribe a published track and compare it with its script and timing."""
    from tum_mcp.course.media.listening import listen_audio

    _emit(listen_audio(_ready(project), stem))


@app.command()
def publish(
    project: Path,
    stem: str,
    teaching_review: Annotated[Path, typer.Option(help="Teaching review notes (Markdown).")],
) -> None:
    """Assemble, check and install one category track with its manifest receipt."""
    from tum_mcp.course.media.audio_project import publish as run

    _emit(run(_ready(project), stem, teaching_review.expanduser().resolve()))
