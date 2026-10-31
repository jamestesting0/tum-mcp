"""Offline review of note evidence and highlight boundaries against the cached transcript."""

from pathlib import Path

from pydantic import JsonValue

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_content import LectureContent
from tum_mcp.lecture_evidence import merge_intervals
from tum_mcp.lecture_processing.receipts import PASSAGES, evidence_bytes, usable_receipt
from tum_mcp.lecture_processing.transcript_models import Passage

EDGE_S = 0.5
WINDOW_S = 20.0
TEXT_LIMIT = 400


def _speech(passages: tuple[Passage, ...] | list[Passage], start: float, end: float) -> str:
    text = " ".join(
        passage.text.strip()
        for passage in passages
        if passage.interval.start_s < end and start < passage.interval.end_s
    )
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def check_highlights(
    root: Path, content: LectureContent, lecture_key: str | None = None
) -> dict[str, JsonValue]:
    lectures = [item for item in content.lectures if lecture_key in (None, item.key)]
    if not lectures:
        raise CampusError(Code.SCOPE_DENIED, "No authored lecture has this key.")
    reports: list[JsonValue] = []
    evidence = {item.key: item for item in content.evidence}
    errors = 0
    for lecture in lectures:
        if lecture.recording.synthetic:
            reports.append({"key": lecture.key, "transcript": "synthetic"})
            continue
        try:
            receipt = usable_receipt(root, lecture.recording.key)
            passages = PASSAGES.validate_json(
                evidence_bytes(root, lecture.recording.key, "transcript.json")
            )
        except CampusError:
            reports.append({"key": lecture.key, "transcript": "unavailable"})
            errors += 1
            continue
        items: list[JsonValue] = []
        for highlight in lecture.highlights:
            start, end = highlight.interval.start_s, highlight.interval.end_s
            issues: list[JsonValue] = []
            if not any(abs(item.interval.start_s - start) <= EDGE_S for item in passages):
                issues.append("start_off_passage")
            if not any(abs(item.interval.end_s - end) <= EDGE_S for item in passages):
                issues.append("end_off_passage")
            errors += len(issues)
            if any(span.start_s < end and start < span.end_s for span in receipt.uncertain):
                issues.append("uncertain_speech")
            items.append(
                {
                    "key": highlight.key,
                    "start_s": start,
                    "end_s": end,
                    "duration_s": round(end - start, 3),
                    "opening": _speech(passages, start, min(end, start + WINDOW_S)),
                    "closing": _speech(passages, max(start, end - WINDOW_S), end),
                    "issues": issues,
                }
            )
        note_items: list[JsonValue] = []
        for note in lecture.notes:
            spans = tuple(
                evidence[key].interval for key in note.evidence if evidence[key].kind != "frame"
            )
            speech = " ".join(_speech(passages, span.start_s, span.end_s) for span in spans)
            issues = []
            if not speech:
                issues.append("speech_unavailable")
                errors += 1
            if any(
                unclear.start_s < span.end_s and span.start_s < unclear.end_s
                for unclear in receipt.uncertain
                for span in spans
            ):
                issues.append("uncertain_speech")
            note_items.append({"key": note.key, "speech": speech[:TEXT_LIMIT], "issues": issues})
        total = sum(item.interval.end_s - item.interval.start_s for item in lecture.highlights)
        processed = sum(span.end_s - span.start_s for span in merge_intervals(receipt.processed))
        reports.append(
            {
                "key": lecture.key,
                "recording": lecture.recording.key,
                "as_of": receipt.checked_at,
                "transcript": "checked",
                "highlights": len(lecture.highlights),
                "notes": len(lecture.notes),
                "note_items": note_items,
                "highlight_s": round(total, 1),
                "processed_s": round(processed, 1),
                "share": round(total / processed, 2) if processed else 0,
                "items": items,
            }
        )
    return {"mode": "offline_cached", "lectures": reports, "errors": errors}
