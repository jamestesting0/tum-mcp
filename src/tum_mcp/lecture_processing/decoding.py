"""Local-file-only decoder boundary and measurable segment timing."""

import hashlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.media import AcquiredSegment
from tum_mcp.settings import Frozen


class DecoderOutput(Frozen):
    stdout: bytes = Field(repr=False, exclude=True)
    stderr: bytes = Field(repr=False, exclude=True)


def run_decoder(argv: tuple[str, ...], timeout: int = 180) -> DecoderOutput:
    """Discard raw diagnostics on failure; never passes a signed URL to a process."""
    if (
        not argv
        or argv[0] not in {"ffmpeg", "ffprobe"}
        or any(arg.startswith(("http:", "https:", "rtsp:")) for arg in argv)
    ):
        raise CampusError(Code.SCOPE_DENIED, "Decoder accepts only private local files.")
    try:
        # Callers construct fixed decoder arguments and confined local paths; no shell.
        result = subprocess.run(  # noqa: S603
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Local decoder is unavailable or exceeded its time bound."
        ) from None
    if result.returncode or len(result.stdout) + len(result.stderr) > 4 * 1024 * 1024:
        raise CampusError(
            Code.INVALID_RESPONSE, "Local media decode failed validation; raw diagnostics omitted."
        )
    return DecoderOutput(stdout=result.stdout, stderr=result.stderr)


class LocalInput(Frozen):
    path: Path
    format: Literal["mpegts", "mov"]

    @property
    def argv(self) -> tuple[str, ...]:
        return ("-protocol_whitelist", "file,pipe", "-f", self.format, "-i", str(self.path))


def verify_segment(segment: AcquiredSegment) -> None:
    for path, expected in (
        (segment.path, segment.sha256),
        (segment.initialization, segment.initialization_sha256),
    ):
        if path is not None:
            if path.is_symlink() or path.is_junction():
                raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic media paths are disabled.")
            with path.open("rb") as payload:
                actual = hashlib.file_digest(payload, "sha256").hexdigest()
            if expected != actual:
                raise CampusError(Code.INVALID_RESPONSE, "Cached media changed before decoding.")


@contextmanager
def local_input(segment: AcquiredSegment) -> Iterator[LocalInput]:
    verify_segment(segment)
    if segment.initialization is None:
        yield LocalInput(path=segment.path, format="mpegts")
        return
    with tempfile.TemporaryDirectory(dir=segment.path.parent, prefix="decode-") as directory:
        temporary = Path(directory) / "input.mp4"
        with temporary.open("wb") as output:
            for path in (segment.initialization, segment.path):
                with path.open("rb") as source:
                    shutil.copyfileobj(source, output)
        yield LocalInput(path=temporary, format="mov")


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class ProbeStream(Wire):
    codec_type: str
    width: int | None = None
    height: int | None = None
    start_time: FiniteFloat | None = None
    duration: FiniteFloat | None = None
    channels: int | None = None


class ProbeFormat(Wire):
    start_time: FiniteFloat | None = None
    duration: FiniteFloat | None = None


class Probe(Wire):
    streams: tuple[ProbeStream, ...] = Field(max_length=32)
    format: ProbeFormat


def probe(source: LocalInput) -> Probe:
    payload = run_decoder(
        (
            "ffprobe",
            "-v",
            "error",
            *source.argv,
            "-show_entries",
            "stream=codec_type,width,height,start_time,duration,channels:format=start_time,duration",
            "-of",
            "json",
        )
    ).stdout
    try:
        return Probe.model_validate_json(payload)
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Decoder timing metadata is unsupported."
        ) from None
