import hashlib
import io
import shutil
import subprocess
from pathlib import Path

import httpx2
import pytest
from PIL import Image, ImageDraw
from pydantic import SecretStr

from tum_mcp.errors import CampusError
from tum_mcp.lecture_evidence import Crop, Interval
from tum_mcp.lecture_processing.media import MediaCache, acquire
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import MediaGrant
from tum_mcp.lecture_processing.playlists import load_manifest
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate
from tum_mcp.lecture_processing.visuals import (
    app_frame,
    capture_frame,
    changed_fraction,
    raster,
    sprite_frame,
)


@pytest.mark.parametrize("columns", [14, 17])
def test_sprite_contract_reads_correct_cell_without_inventing_a_capture_time(columns: int) -> None:
    with Image.new("RGB", (columns * 160, 180), "white") as sheet:
        ImageDraw.Draw(sheet).rectangle((160, 90, 319, 179), fill="red")
        buffer = io.BytesIO()
        sheet.save(buffer, format="PNG")
    with sprite_frame(buffer.getvalue(), columns + 1) as cell:
        assert cell.size == (160, 90) and cell.getpixel((80, 45)) == (255, 0, 0)
    with pytest.raises(CampusError):
        sprite_frame(buffer.getvalue(), 100)


@pytest.mark.parametrize("payload", [b"<svg/>", b"not an image", b"\x89PNG\r\ntruncated"])
def test_malformed_or_active_raster_content_is_rejected(payload: bytes) -> None:
    with pytest.raises(CampusError):
        raster(payload)


def test_incremental_writing_is_compared_with_last_retained_board_state() -> None:
    with Image.new("RGB", (160, 90), "white") as original, original.copy() as current:
        previous = original.copy()
        try:
            for index in range(20):
                ImageDraw.Draw(current).rectangle((index * 2, 10, index * 2 + 1, 10), fill="black")
                assert changed_fraction(previous, current) < 0.0025
                previous.close()
                previous = current.copy()
            assert changed_fraction(original, current) > 0.0025
        finally:
            previous.close()


@pytest.fixture(params=("mpegts", "fmp4"))
def generated_vod(tmp_path: Path, request) -> Path:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("Local FFmpeg/ffprobe optional capability is absent.")
    root = tmp_path / "source"
    root.mkdir()
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for color in ("blue", "red", "green"):
        argv += ["-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=10:d=2"]
    argv += [
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=16000:duration=6",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-g",
        "20",
        "-c:a",
        "aac",
        "-ar",
        "16000",
        "-f",
        "hls",
        "-hls_time",
        "2",
        "-hls_list_size",
        "0",
        "-hls_playlist_type",
        "vod",
    ]
    if request.param == "fmp4":
        argv += [
            "-hls_segment_type",
            "fmp4",
            "-hls_fmp4_init_filename",
            "init.mp4",
            "-hls_segment_filename",
            str(root / "part%03d.m4s"),
        ]
    else:
        argv += ["-hls_segment_filename", str(root / "part%03d.ts")]
    argv += [str(root / "main.m3u8")]
    # Only fixed lavfi sources and owned paths are used; this generates synthetic input.
    subprocess.run(argv, check=True, capture_output=True, timeout=30)  # noqa: S603
    return root


def test_native_frame_uses_decoded_pts_not_requested_off_grid_time(
    generated_vod: Path, tmp_path: Path
) -> None:
    grant = MediaGrant(
        playlist=SecretStr("https://media.example.invalid/recording/main.m3u8?jwt=synthetic")
    )
    requests = []

    def respond(request):
        requests.append(request.url.path)
        body = (generated_vod / request.url.path.split("/")[-1]).read_bytes()
        return httpx2.Response(200, content=body)

    with MediaHTTP(grant, TransferBudget(), httpx2.MockTransport(respond)) as client:
        manifest = load_manifest(client)
        validity = evaluate(RecordingTiming(duration_s=manifest.duration_s))
        acquired = acquire(manifest, MediaCache(tmp_path / "cache", client), validity)
    segment = next(
        item for item in acquired if item.segment.span.start_s <= 3.55 < item.segment.span.end_s
    )
    frame = capture_frame(segment, 3.55, tmp_path / "frames")
    assert frame.captured_at_s == pytest.approx(3.6, abs=0.00001)
    assert frame.captured_at_s != 3.55
    assert frame.sha256 == hashlib.sha256(frame.path.read_bytes()).hexdigest()
    derivative = app_frame(
        frame,
        tmp_path / "app-frames",
        Crop(
            x=0,
            y=0,
            width=160,
            height=180,
            original_width=320,
            original_height=180,
            original_sha256=frame.sha256,
        ),
    )
    assert derivative.captured_at_s == frame.captured_at_s
    assert derivative.original_sha256 == frame.sha256
    assert (derivative.width, derivative.height) == (160, 180)
    with raster(frame.path.read_bytes()) as image:
        red, green, blue = image.getpixel((160, 90))
        assert red > 200 and green < 40 and blue < 40
    assert len(requests) == len(manifest.segments) + 1 + int(segment.initialization is not None)
    with pytest.raises(CampusError, match="excluded"):
        capture_frame(
            segment.model_copy(update={"retained": (Interval(start_s=3.5, end_s=3.57),)}),
            3.55,
            tmp_path / "excluded-frames",
        )
    segment.path.write_bytes(segment.path.read_bytes()[:64])
    with pytest.raises(CampusError, match="changed"):
        capture_frame(segment, 3.55, tmp_path / "corrupt-frames")
