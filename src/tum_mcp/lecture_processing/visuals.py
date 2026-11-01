"""Verified source rasters, actual decoded frame times and cheap candidate comparison."""

import hashlib
import io
import math
import re
import tempfile
import warnings
from pathlib import Path

from PIL import Image, ImageChops, UnidentifiedImageError
from pydantic import FiniteFloat

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import THUMBNAIL_EDGE, Crop, Seconds
from tum_mcp.lecture_processing.decoding import local_input, probe, run_decoder
from tum_mcp.lecture_processing.media import AcquiredSegment
from tum_mcp.lecture_processing.timeline import MapPiece, Timeline
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_models import Digest
from tum_mcp.study_store import confined


class SourceFrame(Frozen):
    path: Path
    sha256: Digest
    original_sha256: Digest
    width: int
    height: int
    captured_at_s: Seconds
    decoded_pts_s: FiniteFloat
    requested_at_s: Seconds | None = None
    crop: Crop | None = None


def raster(payload: bytes) -> Image.Image:
    """Decode a bounded nonanimated JPEG/PNG/WebP; never trust an extension."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload), formats=("JPEG", "PNG", "WEBP")) as opened:
                if opened.width * opened.height > 16_000_000 or getattr(opened, "n_frames", 1) != 1:
                    raise CampusError(
                        Code.INVALID_RESPONSE, "Recording raster exceeds its pixel/frame bound."
                    )
                opened.load()
                return opened.convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise CampusError(
            Code.INVALID_RESPONSE, "Recording raster is malformed or unsafe."
        ) from None


def capture_frame(segment: AcquiredSegment, target_s: float, directory: Path) -> SourceFrame:
    """Decode full segment integrity, then retain the selected frame's measured PTS."""
    if not math.isfinite(target_s) or not any(
        span.start_s <= target_s < span.end_s for span in segment.retained
    ):
        raise CampusError(Code.SCOPE_DENIED, "Requested frame is outside retained original time.")
    if directory.is_symlink() or directory.is_junction():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Source frame folder cannot be symbolic.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with local_input(segment) as source:
        info = probe(source)
        video = next((item for item in info.streams if item.codec_type == "video"), None)
        if (
            video is None
            or video.width is None
            or video.height is None
            or video.width * video.height > 16_000_000
            or video.start_time is None
        ):
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Video lacks bounded dimensions or verified PTS."
            )
        if info.format.duration is not None and info.format.duration < (
            segment.segment.span.end_s - segment.segment.span.start_s - 0.25
        ):
            raise CampusError(
                Code.INVALID_RESPONSE, "Truncated segment does not cover its declared interval."
            )
        run_decoder(
            (
                "ffmpeg",
                "-hide_banner",
                "-v",
                "error",
                "-xerror",
                "-err_detect",
                "explode",
                *source.argv,
                "-map",
                "0:v:0",
                "-an",
                "-f",
                "null",
                "-",
            )
        )
        target_pts = video.start_time + target_s - segment.segment.span.start_s
        with tempfile.TemporaryDirectory(dir=directory, prefix="capture-") as temporary:
            output = Path(temporary) / "frame.png"
            decoded = run_decoder(
                (
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    "-xerror",
                    "-copyts",
                    *source.argv,
                    "-an",
                    "-vf",
                    f"select='gte(t,{target_pts:.9f})',showinfo",
                    "-frames:v",
                    "1",
                    "-fps_mode",
                    "vfr",
                    "-c:v",
                    "png",
                    "-y",
                    str(output),
                )
            )
            matches = re.findall(rb"\bpts_time:([-+0-9.eE]+)", decoded.stderr)
            if not matches or not output.is_file():
                raise CampusError(
                    Code.INVALID_RESPONSE, "No measured frame was decoded at the requested time."
                )
            pts = float(matches[0])
            timeline = Timeline(
                pieces=(
                    MapPiece(
                        local_start_s=video.start_time,
                        original=segment.segment.span,
                    ),
                )
            )
            captured = timeline.to_original(pts)
            if not any(span.start_s <= captured < span.end_s for span in segment.retained):
                raise CampusError(
                    Code.INVALID_RESPONSE, "Decoded frame falls in an excluded interval."
                )
            payload = output.read_bytes()
    with raster(payload) as image:
        width, height = image.size
    digest = hashlib.sha256(payload).hexdigest()
    destination = confined(directory, f"{digest}.png")
    private_write(destination, payload)
    return SourceFrame(
        path=destination,
        sha256=digest,
        original_sha256=digest,
        width=width,
        height=height,
        captured_at_s=captured,
        decoded_pts_s=pts,
        requested_at_s=target_s,
    )


def changed_fraction(previous: Image.Image, current: Image.Image) -> float:
    """Compare with last retained state so incremental board writing accumulates."""
    with (
        previous.convert("L").resize((160, 90)) as first,
        current.convert("L").resize((160, 90)) as second,
    ):
        with ImageChops.difference(first, second) as difference:
            histogram = difference.histogram()
    return sum(histogram[12:]) / (160 * 90)


def sprite_frame(payload: bytes, index: int) -> Image.Image:
    """Provider 160x90 cells, row-major; validate the actual sheet geometry."""
    with raster(payload) as sheet:
        columns = sheet.width // 160
        if not columns or sheet.width % 160 or sheet.height % 90:
            raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Sprite has unsupported cell geometry.")
        x, y = (index % columns) * 160, (index // columns) * 90
        if index < 0 or x + 160 > sheet.width or y + 90 > sheet.height:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED, "Sprite index exceeds the provider sheet."
            )
        return sheet.crop((x, y, x + 160, y + 90))


def app_frame(frame: SourceFrame, directory: Path, crop: Crop | None = None) -> SourceFrame:
    """Create a bounded lossless derivative; original time and provenance cannot change."""
    if frame.path.is_symlink() or frame.path.is_junction():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Symbolic source frames are disabled.")
    payload = frame.path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != frame.sha256:
        raise CampusError(Code.INVALID_RESPONSE, "Source frame changed before derivation.")
    if directory.is_symlink() or directory.is_junction():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Thumbnail folder cannot be symbolic.")
    with raster(payload) as original:
        if crop is not None and (
            frame.sha256 != frame.original_sha256
            or crop.original_sha256 != frame.sha256
            or (crop.original_width, crop.original_height) != original.size
        ):
            raise CampusError(
                Code.INVALID_RESPONSE, "Crop does not identify this original source frame."
            )
        selected = (
            original.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height))
            if crop
            else original.copy()
        )
        with selected:
            selected.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE), Image.Resampling.LANCZOS)
            width, height = selected.size
            buffer = io.BytesIO()
            selected.save(buffer, format="PNG")
            encoded = buffer.getvalue()
    digest = hashlib.sha256(encoded).hexdigest()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = confined(directory, f"{digest}.png")
    private_write(destination, encoded)
    return frame.model_copy(
        update={
            "path": destination,
            "sha256": digest,
            "width": width,
            "height": height,
            "crop": crop or frame.crop,
        }
    )
