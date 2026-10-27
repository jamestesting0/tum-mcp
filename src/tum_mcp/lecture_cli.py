"""Explicit lecture preparation and bounded offline evidence inspection."""

import json
from pathlib import Path
from typing import Annotated

import typer

from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import require_lecture
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.progress import read_progress
from tum_mcp.lecture_processing.receipts import (
    PASSAGES,
    evidence_bytes,
    export_snapshot,
    read_receipt,
    recording_dir,
    usable_receipt,
)
from tum_mcp.study_store import confined, digest, load_state, private_path

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
runtime_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(runtime_app, name="runtime")


@runtime_app.command(name="status")
def runtime_status(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable runtime status.")
    ] = False,
) -> None:
    """Check host, decoder and optional engine without installing anything."""
    require_lecture()
    from tum_mcp.lecture_processing.runtime import status

    report = status()
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return
    from tum_mcp.ui import State, heading, status_rows, terminal_console

    console = terminal_console()
    heading(console, "Lecture runtime", "Local speech recognition and recording prerequisites.")
    engine = {"mlx": "MLX acceleration", "cuda": "NVIDIA CUDA acceleration"}.get(
        report.engine, "CPU recognition"
    )
    if report.engine == "cpu" and report.cuda_declined:
        engine += " (NVIDIA GPU failed its CUDA check)"
    status_rows(
        console,
        [
            (
                engine,
                State.READY
                if report.installed
                else State.MISSING
                if report.supported
                else State.UNAVAILABLE,
                "Runtime installed."
                if report.installed
                else "Run tum-mcp lecture runtime install."
                if report.supported
                else "Use captions or imported transcripts on this host.",
            ),
            (
                "Recording tools",
                State.READY if report.ffmpeg else State.MISSING,
                "FFmpeg and ffprobe available."
                if report.ffmpeg
                else "Install FFmpeg to extract audio or selected frames.",
            ),
            (
                "Cached models",
                State.READY if report.models else State.INFO,
                f"{len(report.models)} model(s) cached. Models load when needed.",
            ),
        ],
    )


@runtime_app.command(name="install")
def runtime_install() -> None:
    """Explicitly install the private pinned wheel-only runtime; models load on demand."""
    require_lecture()
    from tum_mcp.lecture_processing.runtime import install

    typer.echo(install().model_dump_json(indent=2))


@app.command()
def prepare(
    project: Path,
    recording: Annotated[
        list[str], typer.Option(help="Explicit canonical recording URL; repeat to select more.")
    ],
    transcript: Annotated[
        Path | None, typer.Option(help="Original-time WebVTT for one selected recording.")
    ] = None,
    frame_at: Annotated[
        list[float] | None,
        typer.Option(
            help="Critical full frame at original seconds; repeat after transcript review."
        ),
    ] = None,
    language: Annotated[
        str, typer.Option(help="Known ISO language code, otherwise detect speech.")
    ] = "",
    previews: Annotated[
        bool,
        typer.Option(
            "--previews",
            help="Explicitly discover cheap seek previews for unresolved visual questions.",
        ),
    ] = False,
) -> None:
    """Prepare selected evidence in the bound course; authored notes remain a separate review."""
    require_lecture()
    from tum_mcp.lecture_processing.preparation import prepare as run

    if len(recording) > 1 and (transcript is not None or frame_at):
        raise CampusError(
            Code.SCOPE_DENIED,
            "Use one recording when importing captions or selecting critical frames.",
        )
    for url in dict.fromkeys(recording):
        typer.echo(
            run(
                project,
                url,
                transcript=transcript,
                frame_at=tuple(frame_at or ()),
                language=language,
                include_previews=previews,
            ).model_dump_json(indent=2)
        )


@app.command()
def inspect(project: Path) -> None:
    """Show cached receipts with their as-of date; does not fetch or start recognition."""
    require_lecture()
    root = project.expanduser().resolve()
    state = load_state(root)
    directory = private_path(root, "lectures")
    receipts = [
        read_receipt(root, folder.name).model_dump(mode="json")
        for folder in sorted(directory.glob("live-*"))
        if folder.is_dir() and (folder / "receipt.json").is_file()
    ]
    progress = {
        folder.name: value.model_dump(mode="json")
        for folder in sorted(directory.glob("live-*"))
        if folder.is_dir()
        and (value := read_progress(recording_dir(root, folder.name))) is not None
    }
    typer.echo(
        json.dumps(
            {
                "course": state.course.title,
                "mode": "offline_cached_as_of_receipts",
                "recordings": receipts,
                "progress": progress,
            },
            indent=2,
        )
    )


@app.command(name="transcript")
def read_transcript(
    project: Path,
    recording: Annotated[str, typer.Option(help="Prepared recording key from inspect.")],
    start: Annotated[float, typer.Option(min=0, max=28800)] = 0,
    end: Annotated[float, typer.Option(min=0, max=28800)] = 28800,
    limit: Annotated[int, typer.Option(min=1, max=200)] = 50,
    offset: Annotated[int, typer.Option(min=0, max=100000)] = 0,
    words: Annotated[
        bool, typer.Option(help="Include word timing/probability for precise alignment or repair.")
    ] = False,
) -> None:
    """Read bounded cached passages on the original recording clock."""
    require_lecture()
    root = project.expanduser().resolve()
    receipt = usable_receipt(root, recording)
    if start >= end:
        raise CampusError(Code.SCOPE_DENIED, "The evidence interval must have positive duration.")
    passages = PASSAGES.validate_json(evidence_bytes(root, recording, "transcript.json"))
    selected = [
        passage
        for passage in passages
        if passage.interval.start_s < end and start < passage.interval.end_s
    ]
    page = selected[offset : offset + limit]
    typer.echo(
        json.dumps(
            {
                "as_of": receipt.checked_at,
                "mode": "offline_cached",
                "passages": [
                    p.model_dump(
                        mode="json", exclude=set() if words else {"words"}, exclude_defaults=True
                    )
                    for p in page
                ],
                "uncertain_intervals": [
                    span.model_dump(mode="json")
                    for span in receipt.uncertain
                    if span.start_s < end and start < span.end_s
                ],
                "next_offset": offset + limit if len(selected) > offset + limit else None,
            },
            indent=2,
        )
    )


@app.command(name="frames")
def read_frames(
    project: Path,
    recording: Annotated[str, typer.Option()],
    start: Annotated[float, typer.Option(min=0, max=28800)] = 0,
    end: Annotated[float, typer.Option(min=0, max=28800)] = 28800,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    offset: Annotated[int, typer.Option(min=0, max=100000)] = 0,
) -> None:
    """Read cached preview candidates and measured frames; never acquires video."""
    require_lecture()
    root = project.expanduser().resolve()
    receipt = usable_receipt(root, recording)
    if start >= end:
        raise CampusError(Code.SCOPE_DENIED, "The evidence interval must have positive duration.")
    inventory = FrameInventory.model_validate_json(evidence_bytes(root, recording, "frames.json"))
    values = [
        (item.approximate_s, "approximate_preview", item) for item in inventory.candidates
    ] + [(item.captured_at_s, "measured_source_frame", item) for item in inventory.captured]
    selected = sorted(
        (value for value in values if start <= value[0] < end), key=lambda value: value[0]
    )
    page = []
    for timestamp, kind, item in selected[offset : offset + limit]:
        try:
            relative = item.path.relative_to(private_path(root, f"lectures/{recording}"))
        except ValueError:
            raise CampusError(
                Code.SCOPE_DENIED, "Cached frame path leaves this recording."
            ) from None
        path = confined(private_path(root, f"lectures/{recording}"), relative.as_posix())
        if (
            not path.is_file()
            or path.stat().st_size > 32 * 1024**2
            or digest(path.read_bytes()) != item.sha256
        ):
            raise CampusError(Code.STALE_RESULT, "Cached recording image changed or is missing.")
        page.append({"kind": kind, "timestamp_s": timestamp, **item.model_dump(mode="json")})
    typer.echo(
        json.dumps(
            {
                "as_of": receipt.checked_at,
                "mode": "offline_cached",
                "frames": page,
                "next_offset": offset + limit if len(selected) > offset + limit else None,
            },
            indent=2,
        )
    )


@app.command(name="export-snapshot")
def export(project: Path, output: Annotated[Path, typer.Option()]) -> None:
    """Export safe source records for ordinary study sync; excludes private evidence."""
    require_lecture()
    snapshot = export_snapshot(project.expanduser().resolve(), output.expanduser().resolve())
    typer.echo(
        json.dumps(
            {
                "output": str(output.resolve()),
                "selected_recordings": len(snapshot.resources),
                "coverage": "partial_additive",
            },
            indent=2,
        )
    )
