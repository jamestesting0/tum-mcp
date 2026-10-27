"""Explicit, public-model smoke test of the real isolated recognizer on each OS."""

import json
import os
import platform
import subprocess
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing import runtime
from tum_mcp.lecture_processing.runtime_process import worker_path
from tum_mcp.lecture_processing.runtime_spec import mac_major
from tum_mcp.lecture_processing.transcription import analyze, passages, recognize

ENGINES = ["cpu"]
if platform.system() == "Darwin" and platform.machine() == "arm64" and mac_major() >= 15:
    ENGINES.append("mlx")


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_LECTURE_ASR_INTEGRATION") != "1",
    reason="Optional recognizer/model download requires explicit ASR integration selection",
)
@pytest.mark.parametrize("engine", ENGINES)
def test_real_pinned_recognition_and_original_clock(
    engine: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "runtime-data"))
    monkeypatch.setenv("TUM_MCP_LECTURE_ENGINE", engine)
    assert runtime.install().installed
    audio = Path(__file__).parents[1] / "fixtures/lecture/search.wav"
    quality = analyze(audio.resolve())
    assert quality.selected.channel == 0 and not quality.uncertain
    try:
        result = recognize(audio.resolve(), 0, language="en")
    except CampusError:
        # Only this authored synthetic fixture may expose bounded worker diagnostics.
        asset = runtime.model("base")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "HOME",
                "PATH",
                "SYSTEMROOT",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "HOMEDRIVE",
                "HOMEPATH",
                "TMPDIR",
                "TEMP",
                "TMP",
                "LANG",
                "LC_ALL",
                "HF_HUB_CACHE",
            }
        }
        payload = {
            "action": "transcribe",
            "backend": engine,
            "audio": str(audio.resolve()),
            "channel": 0,
            "language": "en",
            "model": str(asset.path),
            "config_sha256": asset.config_sha256,
            "weights_sha256": asset.weights_sha256,
            "supporting_sha256": json.dumps(asset.supporting_sha256),
        }
        diagnostic = subprocess.run(  # noqa: S603 - fixed worker and synthetic/public model inputs
            [str(runtime.python_path()), "-I", "-X", "faulthandler", str(worker_path())],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=60,
            env=environment,
        )
        pytest.fail(
            f"Synthetic worker failed: code={diagnostic.returncode}, "
            f"stderr={diagnostic.stderr.decode('utf-8', errors='replace')[-4000:]}",
            pytrace=False,
        )
    text = " ".join(s.text.casefold() for s in result.segments)
    assert all(word in text for word in ("search", "graph", "vertices"))
    assert result.language == "en" and all(s.words for s in result.segments)
    projected = passages(result, Interval(start_s=120, end_s=120 + quality.duration_s))
    assert projected and all(120 <= p.interval.start_s < p.interval.end_s <= 127 for p in projected)
    assert all(w.start >= 120 for p in projected for w in p.words)
    assert runtime.status().models == ("base",)
    # A changed local config must fail before inference, without changing the cached model.
    asset = runtime.model("base")
    with pytest.raises(CampusError, match="runtime failed"):
        runtime.call_worker(
            "transcribe",
            audio=str(audio.resolve()),
            channel=0,
            model=str(asset.path),
            config_sha256="0" * 64,
            weights_sha256=asset.weights_sha256,
            supporting_sha256=json.dumps(asset.supporting_sha256),
        )
