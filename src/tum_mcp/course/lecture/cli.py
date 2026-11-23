"""Explicit lecture preparation and bounded offline evidence inspection."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue, ValidationError

from tum_mcp.course.lecture.evidence import Crop, merge_intervals
from tum_mcp.course.lecture.scope import RecordingRow, accounting, cached_recordings
from tum_mcp.course.project.models import StudyState
from tum_mcp.course.project.store import digest, load_state, private_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import require_lecture
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.progress import read_progress
from tum_mcp.lecture_processing.receipts import (
    PASSAGES,
    evidence_bytes,
    export_snapshot,
    recording_dir,
    source_text,
    usable_receipt,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
runtime_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(
    runtime_app, name="runtime", help="Check or install local speech recognition for lectures."
)


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
    from tum_mcp.commands.ui import State, heading, status_rows, terminal_console

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
def inspect(
    project: Path,
    through: Annotated[
        datetime | None,
        typer.Option(formats=["%Y-%m-%d"], help="Last requested teaching date (YYYY-MM-DD)."),
    ] = None,
    batch: Annotated[
        str | None, typer.Option(help="Reconcile recordings with this course batch.")
    ] = None,
) -> None:
    """Show cached receipts with their as-of date; does not fetch or start recognition."""
    require_lecture()
    root = project.expanduser().resolve()
    state = load_state(root)
    directory = private_path(root, "lectures")
    receipts = cached_recordings(root, state)
    cutoff = through.date() if through else None
    selected = None
    if batch:
        from tum_mcp.course.checks.batch import checker_batch

        result = checker_batch(root, set(), batch)
        if result is None:
            raise CampusError(Code.ACTION_REQUIRED, f"No batch request for {batch}.")
        _, selected = result
        if selected.lecture_scope:
            if cutoff and cutoff != selected.lecture_scope.through:
                raise CampusError(
                    Code.ACTION_REQUIRED, "Use the verified cutoff in the lecture batch."
                )
            cutoff = selected.lecture_scope.through
        if not cutoff:
            raise CampusError(
                Code.ACTION_REQUIRED, "Supply --through for a batch without a lecture cutoff."
            )
    summary = {}
    if cutoff:
        rows, problems = accounting(
            root,
            receipts,
            cutoff,
            selected.items if selected else (),
            selected.lecture_scope if selected else None,
        )
        summary = {
            **_meeting_scope(root, state, rows, cutoff),
            "accounting": [row.model_dump(mode="json") for row in rows],
            "problems": problems,
        }
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
                "recordings": [receipt.model_dump(mode="json") for receipt in receipts],
                "progress": progress,
                **summary,
            },
            indent=2,
        )
    )


def _meeting_scope(
    root: Path, state: StudyState, recordings: list[RecordingRow], through: date
) -> dict[str, JsonValue]:
    from tum_mcp.course.project.schedule import read_schedule

    schedule = read_schedule(root, state)
    dates = {row.recorded_on for row in recordings if row.recorded_on is not None}
    sessions = schedule.sessions if schedule else ()
    days = sorted(dates | {session.on for session in sessions if session.basis != "release"})
    rows: list[JsonValue] = []
    for day in days:
        matching = [row for row in recordings if row.recorded_on == day]
        keys = [row.recording for row in matching if row.evidence in {"prepared", "partial"}]
        unavailable = [
            {"recording": row.recording, "reason": row.reason}
            for row in matching
            if row.evidence in {"invalid", "unavailable"}
        ]
        rows.append(
            {
                "date": day.isoformat(),
                "sources": [
                    str(key)
                    for key in sorted(
                        {
                            key
                            for session in sessions
                            if session.on == day
                            for key in session.sources
                        }
                    )
                ],
                "recordings": keys,
                "unavailable": unavailable,
                "disposition": (
                    "out_of_scope"
                    if day > through
                    else "available"
                    if keys
                    else "unavailable"
                    if unavailable
                    else "missing"
                ),
            }
        )
    return {"meetings": rows}


@app.command(name="selection-progress")
def read_selection_progress(
    project: Path,
    recording: Annotated[str, typer.Option(help="Prepared recording key from inspect.")],
    finalize: Annotated[
        bool, typer.Option(help="Promote the complete map after checking the authored Lecture.")
    ] = False,
) -> None:
    """Recover the first unread eligible interval from current local evidence."""
    from tum_mcp.course.lecture.selection import finalize_selection, selection_progress

    require_lecture()
    root = project.expanduser().resolve()
    receipt = usable_receipt(root, recording)
    if finalize:
        finalize_selection(root, receipt)
        typer.echo(f"Saved the current selection for {receipt.key}.")
    else:
        typer.echo(selection_progress(root, receipt).model_dump_json(indent=2))


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
        (item.approximate_s, "approximate_preview", "previews", item)
        for item in inventory.candidates
    ] + [
        (item.captured_at_s, "measured_source_frame", "frames", item) for item in inventory.captured
    ]
    selected = sorted(
        (value for value in values if start <= value[0] < end), key=lambda value: value[0]
    )
    page = []
    for timestamp, kind, directory, item in selected[offset : offset + limit]:
        path = private_path(root, f"lectures/{recording}/{directory}/{item.sha256}.png")
        if (
            not path.is_file()
            or path.stat().st_size > 32 * 1024**2
            or digest(path.read_bytes()) != item.sha256
        ):
            raise CampusError(Code.STALE_RESULT, "Cached recording image changed or is missing.")
        data = item.model_copy(update={"path": path}).model_dump(mode="json")
        page.append({"kind": kind, "timestamp_s": timestamp, **data})
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


@app.command(name="thumbnail")
def stage_thumbnail(
    project: Path,
    recording: Annotated[str, typer.Option(help="Prepared recording key from inspect.")],
    at: Annotated[
        float,
        typer.Option(min=0, max=28800, help="Requested --frame-at time of a captured frame."),
    ],
    crop: Annotated[
        str, typer.Option(help="Optional X,Y,WIDTH,HEIGHT in original frame pixels.")
    ] = "",
) -> None:
    """Stage a captured frame as a highlight thumbnail; prints thumbnail and frame evidence."""
    require_lecture()
    from tum_mcp.lecture_processing.visuals import app_frame

    root = project.expanduser().resolve()
    receipt = usable_receipt(root, recording)
    inventory = FrameInventory.model_validate_json(evidence_bytes(root, recording, "frames.json"))
    near = [item for item in inventory.captured if abs(item.captured_at_s - at) <= 0.5]
    frame = next(
        (item for item in inventory.captured if item.requested_at_s == at),
        min(near, key=lambda item: abs(item.captured_at_s - at), default=None),
    )
    if frame is None:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Capture this time first with lecture prepare PROJECT --recording URL "
            f"--frame-at {at:g}.",
        )
    path = private_path(root, f"lectures/{recording}/frames/{frame.sha256}.png")
    if (
        not path.is_file()
        or path.stat().st_size > 64 * 1024**2
        or digest(path.read_bytes()) != frame.sha256
    ):
        raise CampusError(Code.STALE_RESULT, "Prepared original frame is missing or changed.")
    span = next(
        (
            item
            for item in merge_intervals(receipt.processed)
            if item.start_s <= frame.captured_at_s < item.end_s
        ),
        None,
    )
    if span is None:
        raise CampusError(Code.SCOPE_DENIED, "This frame lies outside processed recording time.")
    region = None
    if crop:
        try:
            x, y, width, height = (int(value) for value in crop.split(","))
            region = Crop(
                x=x,
                y=y,
                width=width,
                height=height,
                original_width=frame.width,
                original_height=frame.height,
                original_sha256=frame.sha256,
            )
        except (ValueError, ValidationError):
            raise CampusError(
                Code.SCOPE_DENIED, "Use --crop X,Y,WIDTH,HEIGHT inside the original frame."
            ) from None
    staged = app_frame(
        frame.model_copy(update={"path": path}), private_path(root, "lecture-assets"), region
    )
    moment = frame.captured_at_s
    typer.echo(
        json.dumps(
            {
                "thumbnail": {
                    "evidence": "",
                    "sha256": staged.sha256,
                    "asset": f"lecture-assets/{staged.sha256}.png",
                    "width": staged.width,
                    "height": staged.height,
                    "captured_at_s": moment,
                    "crop": region.model_dump(mode="json") if region else None,
                },
                "evidence": {
                    "key": "",
                    "source_key": receipt.key,
                    "source_sha256": digest(source_text(receipt).encode()),
                    "kind": "frame",
                    "recording_id": receipt.recording.recording_id,
                    "interval": {
                        "start_s": max(span.start_s, moment - 0.1),
                        "end_s": min(span.end_s, moment + 0.1),
                    },
                    "reviewed": False,
                },
            },
            indent=2,
        )
    )


@app.command(name="check")
def check(
    project: Path,
    lecture: Annotated[str | None, typer.Option(help="Only this authored lecture key.")] = None,
) -> None:
    """Check note speech and highlight boundaries against cached transcripts."""
    require_lecture()
    from tum_mcp.course.lecture.check import check_highlights
    from tum_mcp.course.lecture.data import read_lectures

    root = project.expanduser().resolve()
    content = read_lectures(root)
    if content is None:
        raise CampusError(Code.ACTION_REQUIRED, "Author app/lectures/lectures.json first.")
    report = check_highlights(root, content, lecture)
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    if report["errors"]:
        raise typer.Exit(1)


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
