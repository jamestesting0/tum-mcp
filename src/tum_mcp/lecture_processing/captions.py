"""Bounded imported/provider WebVTT; never treats silence exclusions as speech."""

import html
import re

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.transcript_models import Passage
from tum_mcp.lecture_processing.validity import Validity, require_content

STAMP = r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})"
INLINE = re.compile(
    r"</?(?:c(?:\.[^\s>]+)?|v(?:\s[^>]+)?|lang(?:\s[^>]+)?|b|i|u|ruby|rt)>|<(?:\d{2}:)?\d{2}:\d{2}\.\d{3}>"
)


def seconds(value: str) -> float:
    match = re.fullmatch(STAMP, value)
    if match is None:
        raise CampusError(Code.INVALID_RESPONSE, "Caption timestamp is malformed.")
    hour, minute, second, millisecond = match.groups()
    if int(minute) >= 60 or int(second) >= 60:
        raise CampusError(Code.INVALID_RESPONSE, "Caption timestamp component is out of range.")
    return int(hour or 0) * 3600 + int(minute) * 60 + int(second) + int(millisecond) / 1000


def webvtt(payload: bytes, validity: Validity) -> tuple[Passage, ...]:
    require_content(validity)
    if len(payload) > 10 * 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Timed captions exceed the 10 MiB bound.")
    try:
        content = payload.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeError:
        raise CampusError(Code.INVALID_RESPONSE, "Timed captions must use UTF-8 WebVTT.") from None
    if not re.match(r"\AWEBVTT(?:[ \t\n]|$)", content) or "X-TIMESTAMP-MAP" in content:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Expected original-time WebVTT without an unverified clock transform.",
        )
    output: list[Passage] = []
    previous = -1.0
    for block in re.split(r"\n\s*\n", content)[1:]:
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        index = next((i for i, line in enumerate(lines[:2]) if " --> " in line), None)
        if index is None:
            raise CampusError(Code.INVALID_RESPONSE, "A caption cue lacks a timed interval.")
        left, right = lines[index].split(" --> ", 1)
        start, end = seconds(left), seconds(right.split()[0])
        if (
            start < previous
            or not start < end
            or validity.duration_s is None
            or end > validity.duration_s
        ):
            raise CampusError(
                Code.INVALID_RESPONSE, "Caption order or duration disagrees with the recording."
            )
        previous = start
        text = html.unescape(INLINE.sub("", "\n".join(lines[index + 1 :]))).strip()
        if not text:
            continue
        for span in validity.eligible:
            a, b = max(start, span.start_s), min(end, span.end_s)
            if a < b:
                output.append(
                    Passage(
                        interval=Interval(start_s=a, end_s=b),
                        text=text,
                        origin="subtitle",
                        uncertainty="caption_crosses_excluded_time"
                        if a != start or b != end
                        else "",
                    )
                )
        if len(output) > 100000:
            raise CampusError(Code.INVALID_RESPONSE, "Timed captions contain too many cues.")
    return tuple(output)
