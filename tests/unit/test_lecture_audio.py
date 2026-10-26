import wave
from pathlib import Path

import httpx2
from pydantic import SecretStr
from test_lecture_visuals import generated_vod as generated_vod

from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.audio import render_audio
from tum_mcp.lecture_processing.media import MediaCache, acquire
from tum_mcp.lecture_processing.media_budget import TransferBudget
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import MediaGrant
from tum_mcp.lecture_processing.playlists import load_manifest
from tum_mcp.lecture_processing.validity import RecordingTiming, evaluate


def test_pcm_matches_off_grid_original_time_across_segments(
    generated_vod: Path, tmp_path: Path
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, content=(generated_vod / request.url.path.lstrip("/")).read_bytes()
        )

    grant = MediaGrant(playlist=SecretStr("https://media.example/main.m3u8"))
    with MediaHTTP(
        grant,
        TransferBudget(),
        transport=httpx2.MockTransport(respond),
    ) as client:
        manifest = load_manifest(client)
        validity = evaluate(RecordingTiming(duration_s=manifest.duration_s))
        acquired = acquire(manifest, MediaCache(tmp_path / "cache", client), validity)
        output = render_audio(acquired, Interval(start_s=2.33, end_s=4.77), tmp_path / "working")
    with wave.open(str(output)) as audio:
        assert audio.getnframes() == round(2.44 * 16000)
        assert audio.getframerate() == 16000
