"""Cheap row-major seek previews and explicitly selected, measured source frames."""

import hashlib
from pathlib import Path

from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.media import AcquiredSegment
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.lecture_processing.visuals import SourceFrame, capture_frame, raster, sprite_frame
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_store import confined, digest


class Preview(Frozen):
    approximate_s: float = Field(ge=0)
    index: int = Field(ge=0)
    path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FrameInventory(Frozen):
    candidates: tuple[Preview, ...] = Field(default=(), max_length=3000)
    captured: tuple[SourceFrame, ...] = Field(default=(), max_length=3000)


def previews(
    payload: bytes, interval_s: int, validity: Validity, directory: Path
) -> tuple[Preview, ...]:
    require_content(validity)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with raster(payload) as sheet:
        if sheet.width % 160 or sheet.height % 90:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED,
                "Preview grid geometry is unknown; request a measured full frame.",
            )
        count = sheet.width // 160 * (sheet.height // 90)
    if count > 3000:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Preview grid exceeds its cell bound.")
    result: list[Preview] = []
    for index in range(count):
        seconds = index * interval_s
        if not any(span.start_s <= seconds < span.end_s for span in validity.eligible):
            continue
        with sprite_frame(payload, index) as image:
            import io

            output = io.BytesIO()
            image.save(output, format="PNG")
        body = output.getvalue()
        sha = digest(body)
        path = confined(directory, f"{sha}.png")
        if not path.is_file() or digest(path.read_bytes()) != sha:
            private_write(path, body)
        result.append(Preview(approximate_s=seconds, index=index, path=path, sha256=sha))
    return tuple(result)


def selected_frame(segment: AcquiredSegment, seconds: float, directory: Path) -> SourceFrame:
    fingerprint = hashlib.sha256(
        f"{segment.sha256}:{segment.initialization_sha256}:{segment.segment.span}:{seconds:.9f}".encode()
    ).hexdigest()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt = confined(directory, f"frame-{fingerprint}.json")
    if receipt.is_file() and receipt.stat().st_size <= 16384:
        try:
            previous = SourceFrame.model_validate_json(receipt.read_bytes())
            path = confined(directory, previous.path.name)
            if (
                path == previous.path
                and path.is_file()
                and digest(path.read_bytes()) == previous.sha256
                and any(
                    span.start_s <= previous.captured_at_s < span.end_s for span in segment.retained
                )
            ):
                return previous
        except ValidationError:
            raise CampusError(
                Code.INVALID_RESPONSE, "Source frame checkpoint is malformed."
            ) from None
    frame = capture_frame(segment, seconds, directory)
    private_write(receipt, frame.model_dump_json().encode())
    return frame
