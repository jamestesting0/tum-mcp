"""Private CPython 3.13 worker. No campus access; JSON over stdin/stdout only."""

import hashlib
import json
import sys
import wave
from contextlib import redirect_stdout
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def samples(path: Path):
    import numpy as np

    if not path.is_absolute() or path.is_symlink() or path.stat().st_size > 320 * 1024**2:
        raise ValueError("Unusable private PCM path")
    with wave.open(str(path), "rb") as source:
        if (
            source.getframerate() != 16000
            or source.getsampwidth() != 2
            or not 1 <= source.getnchannels() <= 8
            or source.getnframes() > 610 * 16000
        ):
            raise ValueError("Expected bounded 16 kHz signed PCM")
        channels = source.getnchannels()
        data = source.readframes(source.getnframes())
    return np.frombuffer(data, dtype="<i2").reshape(-1, channels)


def analyze(path: Path) -> dict:
    import numpy as np
    import webrtcvad

    pcm = samples(path)
    result = []
    for channel in range(pcm.shape[1]):
        values = pcm[:, channel].copy()
        vad = webrtcvad.Vad(2)
        windows = []
        for start in range(0, len(values), 30 * 16000):
            block = values[start : start + 30 * 16000]
            voiced = sum(
                vad.is_speech(block[i : i + 480].tobytes(), 16000)
                for i in range(0, len(block) - 479, 480)
            )
            windows.append(
                {
                    "start_s": start / 16000,
                    "end_s": (start + len(block)) / 16000,
                    "speech_s": voiced * 0.03,
                }
            )
        floats = values.astype(np.float32) / 32768
        result.append(
            {
                "channel": channel,
                "rms": float(np.sqrt(np.mean(floats * floats))) if len(values) else 0,
                "clipped_fraction": float(np.mean(np.abs(values.astype(np.int32)) >= 32760))
                if len(values)
                else 0,
                "windows": windows,
            }
        )
    return {"duration_s": len(pcm) / 16000, "channels": result}


def pinned_model(repo: str, revision: str) -> dict:
    from huggingface_hub import snapshot_download

    path = Path(
        snapshot_download(
            repo_id=repo, revision=revision, allow_patterns=["config.json", "weights.npz"]
        )
    )
    if path.name != revision:
        raise ValueError("Unverified model snapshot")
    return {
        "path": str(path),
        "revision": revision,
        "config_sha256": sha256(path / "config.json"),
        "weights_sha256": sha256(path / "weights.npz"),
    }


def recognize(request: dict) -> dict:
    import mlx_whisper
    import numpy as np

    model = Path(request["model"])
    if (
        sha256(model / "config.json") != request["config_sha256"]
        or sha256(model / "weights.npz") != request["weights_sha256"]
    ):
        raise ValueError("Pinned model content changed")
    pcm = samples(Path(request["audio"]))
    channel = request["channel"]
    if not 0 <= channel < pcm.shape[1]:
        raise ValueError("Audio channel outside input")
    audio = pcm[:, channel].astype(np.float32) / 32768
    options = {"language": request["language"]} if request.get("language") else {}
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=str(model),
        word_timestamps=True,
        temperature=0.0,
        condition_on_previous_text=False,
        verbose=None,
        hallucination_silence_threshold=2.0,
        **options,
    )
    return {
        "language": result["language"],
        "segments": [
            {
                key: segment[key]
                for key in (
                    "start",
                    "end",
                    "text",
                    "avg_logprob",
                    "no_speech_prob",
                    "compression_ratio",
                    "words",
                )
            }
            for segment in result["segments"]
        ],
    }


def main() -> None:
    request = json.loads(sys.stdin.buffer.read(16385))
    with redirect_stdout(sys.stderr):
        match request["action"]:
            case "model":
                result = pinned_model(request["repo"], request["revision"])
            case "analyze":
                result = analyze(Path(request["audio"]))
            case "transcribe":
                result = recognize(request)
            case _:
                raise ValueError("Unsupported worker action")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
