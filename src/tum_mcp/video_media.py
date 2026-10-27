"""Pure media rules: WebVTT captions/chapters, MP4 layout and validation of probe records."""

import re
from pathlib import Path
from typing import Literal

from tum_mcp.settings import Frozen
from tum_mcp.video_content import ChapterBound, Timing

Quality = Literal["draft", "final"]
QUALITY = {
    "draft": {"width": 854, "height": 480, "fps": 15},
    "final": {"width": 1920, "height": 1080, "fps": 30},
}
CAPTION_CHARACTERS = 84
TARGET_LUFS = -16.0
LOUDNESS_TOLERANCE = 1.0
MAX_TRUE_PEAK = -1.4
DURATION_TOLERANCE = 0.5
AV_TOLERANCE = 0.1


class Probe(Frozen):
    container: str
    video_codec: str
    profile: str | None = None
    pix_fmt: str | None = None
    width: int
    height: int
    fps: float
    video_duration: float
    audio_codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    audio_duration: float | None = None
    loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None


class CheckReport(Frozen):
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    quality: Quality
    narrated: bool

    @property
    def ok(self) -> bool:
        return not self.failed


def stamp(seconds: float) -> str:
    milliseconds = round(max(0.0, seconds) * 1000)
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    whole, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole:02d}.{millis:03d}"


def _segments(text: str) -> list[str]:
    words, parts, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > CAPTION_CHARACTERS:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _vtt_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def captions(timing: Timing) -> str:
    lines = ["WEBVTT", ""]
    number = 0
    for beat in timing.beats:
        for cue in beat.cues:
            parts = _segments(cue.text)
            total = sum(len(part) for part in parts)
            start = cue.start
            for index, part in enumerate(parts):
                end = (
                    cue.end
                    if index == len(parts) - 1
                    else round(start + (cue.end - cue.start) * len(part) / total, 3)
                )
                number += 1
                lines += [str(number), f"{stamp(start)} --> {stamp(end)}", _vtt_text(part), ""]
                start = end
    return "\n".join(lines)


def chapters(bounds: tuple[ChapterBound, ...]) -> str:
    lines = ["WEBVTT", ""]
    for bound in bounds:
        lines += [
            bound.key,
            f"{stamp(bound.start)} --> {stamp(bound.end)}",
            _vtt_text(bound.title),
            "",
        ]
    return "\n".join(lines)


_CUE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> (\d{2}):(\d{2}):(\d{2})\.(\d{3})$")


def parse_vtt(text: str) -> list[tuple[float, float, str]]:
    if not text.startswith("WEBVTT"):
        raise ValueError("missing WEBVTT header")
    cues: list[tuple[float, float, str]] = []
    for block in text.replace("\r\n", "\n").split("\n\n")[1:]:
        rows = [row for row in block.split("\n") if row]
        timing = next((row for row in rows if "-->" in row), None)
        if timing is None:
            continue
        match = _CUE.match(timing)
        if match is None:
            raise ValueError(f"invalid cue timing {timing!r}")
        g = [int(x) for x in match.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        body = " ".join(rows[rows.index(timing) + 1 :])
        cues.append((start, end, body))
    return cues


def faststart(path: Path) -> bool:
    """True when the MP4 movie header precedes media data, so playback starts at once."""
    offset = 0
    seen: dict[str, int] = {}
    size_total = path.stat().st_size
    with path.open("rb") as stream:
        while offset < size_total and len(seen) < 64:
            stream.seek(offset)
            header = stream.read(8)
            if len(header) < 8:
                break
            size = int.from_bytes(header[:4], "big")
            kind = header[4:8].decode("latin-1")
            if size == 1:
                size = int.from_bytes(stream.read(8), "big")
            elif size == 0:
                size = size_total - offset
            if size < 8:
                return False
            seen.setdefault(kind, offset)
            offset += size
    return "moov" in seen and "mdat" in seen and seen["moov"] < seen["mdat"]


def check_media(
    probe: Probe,
    *,
    quality: Quality,
    timing: Timing,
    track: Path,
    captions_text: str,
    chapters_text: str,
    poster: Path,
) -> CheckReport:
    passed: list[str] = []
    failed: list[str] = []

    def rule(name: str, ok: bool, detail: str = "") -> None:
        (passed if ok else failed).append(name if ok or not detail else f"{name}: {detail}")

    expected = QUALITY[quality]
    rule("container.mp4", probe.container in {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"}, probe.container)
    rule("video.h264", probe.video_codec == "h264", probe.video_codec)
    rule("video.yuv420p", probe.pix_fmt == "yuv420p", str(probe.pix_fmt))
    rule(
        "video.size",
        (probe.width, probe.height) == (expected["width"], expected["height"]),
        f"{probe.width}x{probe.height}",
    )
    rule("video.fps", abs(probe.fps - expected["fps"]) < 0.01, f"{probe.fps}")
    rule(
        "video.duration",
        abs(probe.video_duration - timing.total) <= DURATION_TOLERANCE,
        f"{probe.video_duration:.3f}s vs timing {timing.total:.3f}s",
    )
    rule("mp4.faststart", faststart(track))
    narrated = not timing.silent
    if narrated:
        rule("audio.aac", probe.audio_codec == "aac", str(probe.audio_codec))
        rule(
            "audio.format",
            probe.sample_rate == 48000 and probe.channels == 1,
            f"{probe.sample_rate} Hz, {probe.channels} ch",
        )
        rule(
            "audio.sync",
            probe.audio_duration is not None
            and abs(probe.audio_duration - probe.video_duration) <= AV_TOLERANCE,
            f"audio {probe.audio_duration}s vs video {probe.video_duration:.3f}s",
        )
        rule(
            "audio.loudness",
            probe.loudness_lufs is not None
            and abs(probe.loudness_lufs - TARGET_LUFS) <= LOUDNESS_TOLERANCE,
            f"{probe.loudness_lufs} LUFS",
        )
        rule(
            "audio.true_peak",
            probe.true_peak_dbtp is not None and probe.true_peak_dbtp <= MAX_TRUE_PEAK,
            f"{probe.true_peak_dbtp} dBTP",
        )
    else:
        rule("narration.present", False, "silent draft; narration is pending")
    for name, text, required in (
        ("captions", captions_text, narrated),
        ("chapters", chapters_text, True),
    ):
        try:
            cues = parse_vtt(text)
            ordered = all(a[0] <= a[1] for a in cues) and all(
                a[1] <= b[0] + 0.001 for a, b in zip(cues, cues[1:], strict=False)
            )
            inside = all(cue[1] <= probe.video_duration + 0.05 for cue in cues)
            rule(f"{name}.valid", bool(cues) or not required, "no cues")
            rule(f"{name}.ordered", ordered, "overlapping or reversed cues")
            rule(f"{name}.bounds", inside, "cue ends after the video")
        except ValueError as error:
            rule(f"{name}.valid", False, str(error))
    rule("poster.jpeg", poster.is_file() and poster.read_bytes()[:3] == b"\xff\xd8\xff")
    return CheckReport(
        passed=tuple(passed), failed=tuple(failed), quality=quality, narrated=narrated
    )
