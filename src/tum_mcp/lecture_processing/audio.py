"""Decode bounded retained PCM against each period's measured presentation clock."""

import math
import shutil
import tempfile
import wave
from pathlib import Path

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.audio_input import joined_input, periods
from tum_mcp.lecture_processing.decoding import probe, run_decoder
from tum_mcp.lecture_processing.media import AcquiredSegment
from tum_mcp.study_store import confined

# Encoders leave tiny gaps between AAC packet timestamps (TUM-Live: about 0.25 ms per 30 s),
# so a timestamp-trimmed window decodes a few samples short; those are padded with silence.
# One missing AAC frame is at least 21 ms (341 samples at 16 kHz) and still fails here.
TIMESTAMP_JITTER = 160


def render_audio(segments: tuple[AcquiredSegment, ...], span: Interval, directory: Path) -> Path:
    if span.end_s - span.start_s > 610:
        raise CampusError(Code.SCOPE_DENIED, "Audio decoding is bounded to one recognition chunk.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = confined(directory, "audio.wav")
    if shutil.disk_usage(directory).free < 1024**3:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Insufficient private working space for one audio chunk."
        )
    channels: int | None = None
    cursor = span.start_s
    with tempfile.TemporaryDirectory(prefix="pcm-", dir=directory) as folder:
        candidate = Path(folder) / "audio.wav"
        with wave.open(str(candidate), "wb") as destination:
            destination.setsampwidth(2)
            destination.setframerate(16000)
            for group in periods(segments):
                first, last = group[0], group[-1]
                start, end = (
                    max(span.start_s, first.segment.span.start_s),
                    min(span.end_s, last.segment.span.end_s),
                )
                if start >= end:
                    continue
                if not math.isclose(start, cursor, abs_tol=1e-7) or any(
                    not any(
                        part.start_s
                        <= max(start, item.segment.span.start_s)
                        < min(end, item.segment.span.end_s)
                        <= part.end_s
                        for part in item.retained
                    )
                    for item in group
                    if item.segment.span.start_s < end and start < item.segment.span.end_s
                ):
                    raise CampusError(
                        Code.INVALID_RESPONSE,
                        "Audio chunk crosses an excluded or unavailable interval.",
                    )
                with joined_input(group, directory) as source:
                    info = probe(source)
                    audio = next(
                        (stream for stream in info.streams if stream.codec_type == "audio"), None
                    )
                    video = next(
                        (stream for stream in info.streams if stream.codec_type == "video"), None
                    )
                    origin = video.start_time if video else info.format.start_time
                    if (
                        audio is None
                        or audio.channels is None
                        or not 1 <= audio.channels <= 8
                        or origin is None
                    ):
                        raise CampusError(
                            Code.CAPABILITY_UNSUPPORTED,
                            "Audio requires bounded channels and a verified presentation clock.",
                        )
                    if channels is None:
                        channels = audio.channels
                        destination.setnchannels(channels)
                    if channels != audio.channels:
                        raise CampusError(
                            Code.CAPABILITY_UNSUPPORTED,
                            "Channel layout changed inside a recognition chunk.",
                        )
                    begin = origin + start - first.segment.span.start_s
                    finish = origin + end - first.segment.span.start_s
                    pcm = Path(folder) / "period.wav"
                    run_decoder(
                        (
                            "ffmpeg",
                            "-hide_banner",
                            "-v",
                            "error",
                            "-xerror",
                            "-err_detect",
                            "explode",
                            "-copyts",
                            *source.argv,
                            "-map",
                            "0:a:0",
                            "-vn",
                            "-af",
                            f"atrim=start={begin:.9f}:end={finish:.9f},asetpts=PTS-STARTPTS",
                            "-ar",
                            "16000",
                            "-c:a",
                            "pcm_s16le",
                            "-y",
                            str(pcm),
                        )
                    )
                with wave.open(str(pcm), "rb") as decoded:
                    expected = round((end - span.start_s) * 16000) - round(
                        (start - span.start_s) * 16000
                    )
                    count = decoded.getnframes()
                    if abs(count - expected) > TIMESTAMP_JITTER:
                        raise CampusError(
                            Code.INVALID_RESPONSE,
                            "Decoded audio does not cover its declared original-time interval.",
                        )
                    payload = decoded.readframes(min(count, expected))
                    destination.writeframesraw(
                        payload + b"\0" * (max(0, expected - count) * channels * 2)
                    )
                cursor = end
            if channels is None or not math.isclose(cursor, span.end_s, abs_tol=1e-7):
                raise CampusError(
                    Code.INVALID_RESPONSE, "Audio chunk is incomplete; existing evidence preserved."
                )
        candidate.replace(output)
        output.chmod(0o600)
    return output
