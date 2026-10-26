"""Private CPython 3.13 worker. No campus access; JSON over stdin/stdout only."""

import hashlib
import importlib
import json
import os
import sys
import wave
from contextlib import redirect_stdout
from pathlib import Path


def decoding_options(backend: str = "mlx") -> dict[str, float | bool]:
    """Shared inference identity; importing this module loads no model libraries."""
    return ({"beam_size": 1, "vad_filter": False} if backend == "cpu" else {}) | {
        "word_timestamps": True,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "hallucination_silence_threshold": 2.0,
    }


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


def pinned_model(repo: str, revision: str, backend: str) -> dict:
    from huggingface_hub import snapshot_download

    weights = "model.bin" if backend == "cpu" else "weights.npz"
    supporting = ("tokenizer.json", "vocabulary.txt") if backend == "cpu" else ()
    path = Path(
        snapshot_download(
            repo_id=repo,
            revision=revision,
            allow_patterns=["config.json", weights, *supporting],
            token=False,
        )
    )
    if path.name != revision:
        raise ValueError("Unverified model snapshot")
    return {
        "path": str(path),
        "revision": revision,
        "config_sha256": sha256(path / "config.json"),
        "weights_sha256": sha256(path / weights),
        "supporting_sha256": {name: sha256(path / name) for name in supporting},
    }


def recognize(request: dict) -> dict:
    import numpy as np

    model = Path(request["model"])
    backend = request.get("backend", "mlx")
    weights = "model.bin" if backend == "cpu" else "weights.npz"
    supporting = json.loads(request.get("supporting_sha256", "{}"))
    required = {"tokenizer.json", "vocabulary.txt"} if backend == "cpu" else set()
    if set(supporting) != required:
        raise ValueError("Missing or unexpected pinned supporting assets")
    if (
        sha256(model / "config.json") != request["config_sha256"]
        or sha256(model / weights) != request["weights_sha256"]
        or any(sha256(model / name) != supporting[name] for name in required)
    ):
        raise ValueError("Pinned model content changed")
    pcm = samples(Path(request["audio"]))
    channel = request["channel"]
    if not 0 <= channel < pcm.shape[1]:
        raise ValueError("Audio channel outside input")
    audio = pcm[:, channel].astype(np.float32) / 32768
    options = {"language": request["language"]} if request.get("language") else {}
    if backend == "cpu":
        return recognize_cpu(model, audio, options)
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=str(model),
        verbose=None,
        **decoding_options(),
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


def recognize_cpu(model: Path, audio, options: dict) -> dict:
    from faster_whisper import WhisperModel

    decoder = WhisperModel(
        str(model),
        device="cpu",
        compute_type="int8",
        local_files_only=True,
        cpu_threads=min(4, os.cpu_count() or 1),
        num_workers=1,
    )
    segments, info = decoder.transcribe(audio, **decoding_options("cpu"), **options)
    return {
        "language": info.language,
        "segments": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "avg_logprob": s.avg_logprob,
                "no_speech_prob": s.no_speech_prob,
                "compression_ratio": s.compression_ratio,
                "words": [
                    {"start": w.start, "end": w.end, "word": w.word, "probability": w.probability}
                    for w in (s.words or ())
                ],
            }
            for s in segments
        ],
    }


def health(backend: str) -> dict:
    import webrtcvad

    webrtcvad.Vad(2)
    if backend == "cpu":
        import ctranslate2

        importlib.import_module("faster_whisper")
        if "int8" not in ctranslate2.get_supported_compute_types("cpu"):
            raise ValueError("CPU int8 inference unavailable")
    else:
        import mlx.core as mx

        importlib.import_module("mlx_whisper")
        if not mx.metal.is_available():
            raise ValueError("Metal unavailable")
    return {"ready": True}


def main() -> None:
    request = json.loads(sys.stdin.buffer.read(16385))
    with redirect_stdout(sys.stderr):
        match request["action"]:
            case "health":
                result = health(request["backend"])
            case "model":
                result = pinned_model(request["repo"], request["revision"], request["backend"])
            case "analyze":
                result = analyze(Path(request["audio"]))
            case "transcribe":
                result = recognize(request)
            case _:
                raise ValueError("Unsupported worker action")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
