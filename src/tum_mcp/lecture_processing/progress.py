"""Private crash-visible progress and total recording-cache space checks."""

from pathlib import Path

from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.preparation_audio import AudioResult
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_store import ReadObserver, confined


class Progress(Frozen):
    metadata_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage: str = Field(max_length=40)
    processed: tuple[Interval, ...] = ()
    uncertain: tuple[Interval, ...] = ()
    chunks_reused: int = Field(default=0, ge=0)


def disk_guard(root: Path, reserve: int = 0) -> None:
    size = 0
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Symbolic private lecture paths are disabled."
            )
        if path.is_file():
            size += path.stat().st_size
    if size + reserve > 10 * 1024**3:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Private recording cache reached 10 GiB; checkpoint preserved.",
        )


def write_progress(
    directory: Path, revision: str, stage: str, audio: AudioResult | None = None
) -> None:
    progress = Progress(
        metadata_revision=revision,
        stage=stage,
        processed=audio.processed if audio else (),
        uncertain=audio.uncertain if audio else (),
        chunks_reused=audio.reused if audio else 0,
    )
    private_write(confined(directory, "progress.json"), progress.model_dump_json().encode())


def read_progress(directory: Path, *, read_observer: ReadObserver | None = None) -> Progress | None:
    path = confined(directory, "progress.json")
    if not path.is_file():
        if read_observer is not None:
            read_observer(path, None)
        return None
    if path.stat().st_size > 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Lecture progress exceeds its bound.")
    try:
        body = path.read_bytes()
        if read_observer is not None:
            read_observer(path, body)
        return Progress.model_validate_json(body)
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Lecture progress is malformed.") from None
