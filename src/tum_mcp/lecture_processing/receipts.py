"""Restricted job receipts, bounded offline evidence reads and additive source export."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval, LectureCoverage, Recording, Seconds
from tum_mcp.lecture_processing.progress import read_progress
from tum_mcp.lecture_processing.transcript_models import Passage
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_models import Coverage, Digest, Resource, Snapshot
from tum_mcp.study_store import confined, digest, load_state, private_path


class InvalidReceipt(Frozen):
    status: Literal["invalid"] = "invalid"
    key: str = Field(pattern=r"^live-[1-9][0-9]*-[1-9][0-9]*$")
    course_id: int = Field(gt=0)
    recording_id: int = Field(gt=0)
    checked_at: str
    reason: str
    duration_s: Seconds | None

    @model_validator(mode="after")
    def consistent(self) -> "InvalidReceipt":
        if self.key != f"live-{self.course_id}-{self.recording_id}":
            raise ValueError("Invalid receipt identity must match its recording key.")
        return self


class PreparedReceipt(Frozen):
    status: Literal["partial", "prepared"]
    key: str = Field(pattern=r"^live-[1-9][0-9]*-[1-9][0-9]*$")
    recording: Recording
    title: str = Field(max_length=2000)
    checked_at: str
    validity: Validity
    source_revision: Digest
    metadata_revision: Digest
    imported_transcript_sha256: Digest | None = None
    processed: tuple[Interval, ...] = ()
    missing: tuple[Interval, ...] = ()
    uncertain: tuple[Interval, ...] = ()
    transcript_sha256: Digest
    frames_sha256: Digest
    bytes_downloaded: int = Field(ge=0)
    media_reused: int = Field(ge=0)
    chunks_reused: int = Field(ge=0)
    inference_s: float = Field(ge=0)
    issues: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> "PreparedReceipt":
        if self.key != self.recording.key or self.recording.duration_s != self.validity.duration_s:
            raise ValueError("Receipt identity/duration must match its recording.")
        if self.status == "prepared" and (self.missing or self.uncertain or self.issues):
            raise ValueError("Prepared evidence cannot conceal missing or uncertain coverage.")
        LectureCoverage(
            status="partial",
            eligible=self.validity.eligible,
            processed=self.processed,
            missing=self.missing,
            uncertain=self.uncertain,
            excluded=self.validity.excluded,
        )
        return self


Receipt = Annotated[InvalidReceipt | PreparedReceipt, Field(discriminator="status")]
RECEIPT = TypeAdapter(Receipt)
PASSAGES = TypeAdapter(tuple[Passage, ...])


def now() -> str:
    return datetime.now(UTC).isoformat()


def save_invalid(
    directory: Path, course_id: int, recording_id: int, valid: Validity
) -> InvalidReceipt:
    receipt = InvalidReceipt(
        key=directory.name,
        course_id=course_id,
        recording_id=recording_id,
        checked_at=now(),
        reason=valid.reason,
        duration_s=valid.duration_s,
    )
    private_write(confined(directory, "receipt.json"), receipt.model_dump_json(indent=2).encode())
    return receipt


def recording_dir(root: Path, key: str) -> Path:
    if re.fullmatch(r"live-[1-9][0-9]{0,15}-[1-9][0-9]{0,15}", key) is None:
        raise CampusError(Code.SCOPE_DENIED, "Use a prepared recording key from lecture inspect.")
    return private_path(root, f"lectures/{key}")


def read_receipt(root: Path, key: str) -> Receipt:
    path = recording_dir(root, key) / "receipt.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024**2:
        raise CampusError(
            Code.ACTION_REQUIRED, "Prepare this selected recording before reading evidence."
        )
    try:
        result = RECEIPT.validate_json(path.read_bytes())
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Lecture receipt is invalid; preserve and inspect it."
        ) from None
    if result.key != key:
        raise CampusError(Code.SCOPE_DENIED, "Recording receipt identity changed.")
    course_id = (
        result.course_id if isinstance(result, InvalidReceipt) else result.recording.course_id
    )
    if not any(
        binding.provider == "tum_live"
        and binding.course_id == str(course_id)
        and (
            isinstance(result, InvalidReceipt)
            or binding.course_slug == result.recording.course_slug
        )
        for binding in load_state(root).course.bindings
    ):
        raise CampusError(
            Code.SCOPE_DENIED, "Cached recording is outside the current course binding."
        )
    return result


def usable_receipt(root: Path, key: str) -> PreparedReceipt:
    receipt = read_receipt(root, key)
    if isinstance(receipt, InvalidReceipt):
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, f"Recording invalid: {receipt.reason}.")
    require_content(receipt.validity)
    progress = read_progress(recording_dir(root, key))
    if progress is not None and progress.metadata_revision != receipt.metadata_revision:
        raise CampusError(
            Code.STALE_RESULT,
            "Source metadata changed during interrupted preparation; "
            "resume before reading older evidence.",
        )
    return receipt


def evidence_bytes(root: Path, key: str, name: Literal["transcript.json", "frames.json"]) -> bytes:
    receipt = usable_receipt(root, key)
    path = private_path(root, f"lectures/{key}/{name}")
    if not path.is_file() or path.stat().st_size > 16 * 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Cached lecture evidence is missing or oversized.")
    payload = path.read_bytes()
    expected = receipt.transcript_sha256 if name == "transcript.json" else receipt.frames_sha256
    if digest(payload) != expected:
        raise CampusError(
            Code.STALE_RESULT, "Cached lecture evidence changed; prepare or reconcile it first."
        )
    return payload


def source_text(receipt: Receipt) -> str:
    if isinstance(receipt, InvalidReceipt):
        return (
            f"# Recording {receipt.recording_id}\n\nStatus: invalid ({receipt.reason}). "
            "No teaching evidence was prepared.\n"
        )
    recording = receipt.recording

    def spans(values: tuple[Interval, ...]) -> str:
        return ", ".join(f"{span.start_s:.6f}–{span.end_s:.6f}s" for span in values) or "none"

    return (
        f"# {receipt.title}\n\n"
        f"Recording: https://live.rbg.tum.de/w/{recording.course_slug}/{recording.recording_id}\n"
        f"Course ID: {recording.course_id}; recorded: {recording.recorded_on}.\n"
        f"Original duration: {recording.duration_s:.6f}s. "
        f"Source revision: {receipt.source_revision}.\n\n"
        f"Eligible: {spans(receipt.validity.eligible)}.\n"
        f"Excluded: {spans(receipt.validity.excluded)}.\n"
        f"Processed: {spans(receipt.processed)}.\nMissing: {spans(receipt.missing)}.\n"
        f"Uncertain: {spans(receipt.uncertain)}.\n"
        "Transcript and source frames are private preparation evidence; "
        "notes require semantic review.\n"
    )


def export_snapshot(root: Path, output: Path) -> Snapshot:
    state = load_state(root)
    base = private_path(root, "lectures")
    resources: list[Resource] = []
    for folder in sorted(base.glob("live-*")) if base.is_dir() else ():
        receipt = read_receipt(root, folder.name)
        if isinstance(receipt, PreparedReceipt):
            usable_receipt(root, folder.name)
        course_id = (
            receipt.course_id
            if isinstance(receipt, InvalidReceipt)
            else receipt.recording.course_id
        )
        matches = [
            binding
            for binding in state.course.bindings
            if binding.provider == "tum_live" and binding.course_id == str(course_id)
        ]
        if len(matches) != 1:
            raise CampusError(
                Code.SCOPE_DENIED, "Prepared recording is outside the current course bindings."
            )
        binding = matches[0]
        recording_id = (
            receipt.recording_id
            if isinstance(receipt, InvalidReceipt)
            else receipt.recording.recording_id
        )
        text = source_text(receipt)
        resources.append(
            Resource(
                key=receipt.key,
                binding=binding.key,
                kind="content",
                title=f"Lecture recording {recording_id}",
                url=f"https://live.rbg.tum.de/w/{binding.course_slug}/{recording_id}",
                locator=f"recording:{recording_id}",
                revision=digest(text.encode()),
                text=text,
            )
        )
    snapshot = Snapshot(
        schema_version=2,
        course=state.course,
        coverage=tuple(
            Coverage(
                binding=binding.key,
                status="partial",
                checked_at=now(),
                note="Only explicitly selected lecture recordings were checked; "
                "unrelated sources remain unverified.",
            )
            for binding in state.course.bindings
        ),
        resources=tuple(resources),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    private_write(output, snapshot.model_dump_json(indent=2).encode())
    return snapshot
