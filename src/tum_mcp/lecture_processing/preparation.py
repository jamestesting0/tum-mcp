"""Explicit selected-recording lifecycle. Invalidity precedes every content path."""

import json
import math
from pathlib import Path

from filelock import FileLock, Timeout

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval, Recording, merge_intervals
from tum_mcp.lecture_processing import runtime
from tum_mcp.lecture_processing.acquisition import Acquisition
from tum_mcp.lecture_processing.cached_selection import previous_selection
from tum_mcp.lecture_processing.media import MediaCache
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import Manifest
from tum_mcp.lecture_processing.playlists import load_manifest, media_grant
from tum_mcp.lecture_processing.preparation_audio import AudioResult, prepare_audio
from tum_mcp.lecture_processing.prepare_source import (
    missing,
    provider,
    read_captions,
    revision,
    select,
    validity,
)
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory, previews, selected_frame
from tum_mcp.lecture_processing.progress import disk_guard, write_progress
from tum_mcp.lecture_processing.receipts import (
    PreparedReceipt,
    Receipt,
    now,
    recording_dir,
    save_invalid,
)
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.moodle.config import private_write
from tum_mcp.study_store import confined, digest
from tum_mcp.tum_live.client import TumLive
from tum_mcp.tum_live.wire import Watch


def prepare(
    root: Path,
    url: str,
    *,
    transcript: Path | None = None,
    frame_at: tuple[float, ...] = (),
    language: str = "",
) -> Receipt:
    root = root.expanduser().resolve()
    binding, slug, recording_id = select(root, url)
    key = f"live-{binding.course_id}-{recording_id}"
    directory = recording_dir(root, key)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with FileLock(str(confined(directory, "prepare.lock")), timeout=0):
            service = provider(binding)
            watch = service.watch(slug, recording_id)
            if str(watch.course.id) != binding.course_id:
                raise CampusError(
                    Code.SCOPE_DENIED,
                    "Selected recording differs from the bound numeric course ID.",
                )
            valid = validity(watch)
            if valid.status == "invalid":
                return save_invalid(directory, watch.course.id, recording_id, valid)
            budget = TransferBudget()
            with MediaHTTP(media_grant(watch), budget) as client:
                manifest = load_manifest(client)
                valid = validity(watch, manifest.duration_s)
                if valid.status == "invalid":
                    return save_invalid(directory, watch.course.id, recording_id, valid)
                require_content(valid)
                return _evidence(
                    directory,
                    service,
                    watch,
                    manifest,
                    valid,
                    client,
                    transcript,
                    frame_at,
                    language,
                )
    except Timeout:
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Another process is preparing this recording; its checkpoint is preserved.",
        ) from None


def _evidence(
    directory: Path,
    service: TumLive,
    watch: Watch,
    manifest: Manifest,
    valid: Validity,
    client: MediaHTTP,
    imported: Path | None,
    frame_at: tuple[float, ...],
    language: str,
) -> PreparedReceipt:
    issues: list[str] = []
    for seconds in frame_at:
        if not math.isfinite(seconds) or not any(
            span.start_s <= seconds < span.end_s for span in valid.eligible
        ):
            raise CampusError(
                Code.SCOPE_DENIED, "Selected frame is outside eligible original recording time."
            )
    source_revision = revision(watch, valid, manifest)
    imported, frame_at = previous_selection(directory, valid, source_revision, imported, frame_at)
    write_progress(directory, source_revision, "evidence")
    cache = MediaCache(confined(directory, "media"), client, limit=9 * 1024**3)
    acquisition = Acquisition(manifest, cache, valid)
    try:
        captions = read_captions(service, watch, valid, imported, language)
    except CampusError:
        if imported is not None:
            raise
        captions = ()
        issues.append("provider_captions_unusable")
    audio = AudioResult()
    if captions:
        processed = merge_intervals(tuple(passage.interval for passage in captions))
        uncertain = merge_intervals(
            tuple(passage.interval for passage in captions if passage.uncertainty)
        )
    else:
        capability = runtime.status()
        if capability.installed and capability.ffmpeg:
            audio = prepare_audio(
                valid,
                confined(directory, "audio"),
                source_revision,
                acquisition.span,
                language=language,
                progress=lambda value: write_progress(directory, source_revision, "audio", value),
            )
        else:
            issues.append(capability.reason if not capability.installed else "ffmpeg_unavailable")
        processed, uncertain = audio.processed, audio.uncertain
    inventory = FrameInventory()
    view = next((view for view in watch.views if view.playlist_url == client.grant.playlist), None)
    if view is not None and view.sprite is not None:
        try:
            disk_guard(directory, reserve=256 * 1024**2)
            payload = service.file(watch, view.sprite.file_id, duration_s=manifest.duration_s)
            client.budget.charge(len(payload))
            inventory = FrameInventory(
                candidates=previews(
                    payload, view.sprite.interval_s, valid, confined(directory, "previews")
                )
            )
        except CampusError:
            issues.append("seek_previews_unavailable")
    media_revision = acquisition.content_revision
    captured = []
    if frame_at:
        high = load_manifest(client, full_resolution=True)
        if abs(high.duration_s - manifest.duration_s) > 0.05:
            raise CampusError(
                Code.INVALID_RESPONSE, "Video variants disagree on their original-time clock."
            )
        acquisition = Acquisition(high, cache, valid)
        for seconds in sorted(set(frame_at)):
            try:
                disk_guard(directory, reserve=128 * 1024**2)
                candidates = acquisition.span(
                    Interval(start_s=seconds, end_s=min(seconds + 0.001, high.duration_s))
                )
                item = next(
                    segment
                    for segment in candidates
                    if segment.segment.span.start_s <= seconds < segment.segment.span.end_s
                )
                captured.append(selected_frame(item, seconds, confined(directory, "frames")))
            except CampusError:
                issues.append(f"selected_frame_unresolved_at_{seconds:g}s")
    inventory = inventory.model_copy(update={"captured": tuple(captured)})
    transcript_bytes = (
        b"["
        + b",".join(passage.model_dump_json().encode() for passage in (captions or audio.passages))
        + b"]"
    )
    frames_bytes = inventory.model_dump_json(indent=2).encode()
    missing_spans = missing(valid.eligible, processed)
    receipt = PreparedReceipt(
        status="prepared"
        if not missing_spans and not uncertain and not issues and not audio.issues
        else "partial",
        key=directory.name,
        recording=Recording(
            course_slug=watch.course.slug,
            course_id=watch.course.id,
            recording_id=watch.stream.id,
            recorded_on=watch.stream.start.date(),
            duration_s=manifest.duration_s,
        ),
        title=watch.stream.display_name
        or watch.stream.name
        or f"Lecture {watch.stream.start.date()}",
        checked_at=now(),
        validity=valid,
        source_revision=digest(
            json.dumps(
                [
                    source_revision,
                    media_revision,
                    digest(transcript_bytes),
                    [(frame.sha256, frame.captured_at_s) for frame in captured],
                    runtime.profile() if not captions else "captions",
                ],
                sort_keys=True,
            ).encode()
        ),
        metadata_revision=source_revision,
        imported_transcript_sha256=digest(imported.read_bytes()) if imported is not None else None,
        processed=processed,
        missing=missing_spans,
        uncertain=uncertain,
        transcript_sha256=digest(transcript_bytes),
        frames_sha256=digest(frames_bytes),
        bytes_downloaded=client.budget.used,
        media_reused=cache.reused,
        chunks_reused=audio.reused,
        inference_s=audio.inference_s,
        issues=tuple(sorted(set(issues + list(audio.issues)))),
    )
    private_write(confined(directory, "transcript.json"), transcript_bytes)
    if imported is not None:
        private_write(confined(directory, "imported.vtt"), imported.read_bytes())
    private_write(confined(directory, "frames.json"), frames_bytes)
    private_write(confined(directory, "receipt.json"), receipt.model_dump_json(indent=2).encode())
    write_progress(directory, source_revision, "prepared", audio)
    return receipt
