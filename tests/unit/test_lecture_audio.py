import wave
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr
from test_lecture_visuals import generated_vod as generated_vod
from test_lecture_visuals import vod

from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.audio import render_audio
from tum_mcp.lecture_processing.media import MediaCache, acquire
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import MediaGrant
from tum_mcp.lecture_processing.playlists import load_manifest
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate


def render(source: Path, tmp_path: Path, span: Interval) -> Path:
    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=(source / request.url.path.lstrip("/")).read_bytes())

    grant = MediaGrant(playlist=SecretStr("https://media.example/main.m3u8"))
    with MediaHTTP(
        grant,
        TransferBudget(),
        transport=httpx2.MockTransport(respond),
    ) as client:
        manifest = load_manifest(client)
        validity = evaluate(RecordingTiming(duration_s=manifest.duration_s))
        acquired = acquire(manifest, MediaCache(tmp_path / "cache", client), validity)
        return render_audio(acquired, span, tmp_path / "working")


def test_pcm_matches_off_grid_original_time_across_segments(
    generated_vod: Path, tmp_path: Path
) -> None:
    output = render(generated_vod, tmp_path, Interval(start_s=2.33, end_s=4.77))
    with wave.open(str(output)) as audio:
        assert audio.getnframes() == round(2.44 * 16000)
        assert audio.getframerate() == 16000


@pytest.mark.parametrize("segments", ["mpegts", "fmp4"])
@pytest.mark.parametrize("rate", [44100, 48000])
def test_lecture_sample_rates_resample_to_the_exact_off_grid_length(
    tmp_path: Path, segments: str, rate: int
) -> None:
    # Lecture AAC at 44.1 or 48 kHz whose packet timestamps drift slightly ahead of their
    # samples (TUM-Live: about 0.25 ms per 30 s) leaves a timestamp-trimmed window a few
    # samples short. That jitter must be padded, not reported as uncovered audio.
    source = vod(tmp_path, segments, rate, jitter=True)
    for start, end in [(0.37, 3.41), (2.0731, 5.1093)]:
        output = render(source, tmp_path / f"{start}", Interval(start_s=start, end_s=end))
        with wave.open(str(output)) as audio:
            assert audio.getnframes() == round(end * 16000) - round(start * 16000)
