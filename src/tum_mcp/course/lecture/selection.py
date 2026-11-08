"""The author's complete recording selection and its independent review evidence."""

from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.course.content.study import SourceVersion, Text
from tum_mcp.course.lecture.content import Highlight, Lecture
from tum_mcp.course.lecture.evidence import Evidence, Interval, distinct_intervals, merge_intervals
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.course.project.store import confined, load_state, private_path, read_bytes
from tum_mcp.course.project.store import digest as file_digest
from tum_mcp.course.review.items import ReviewItem, blocks_of, digest
from tum_mcp.lecture_processing.receipts import PASSAGES, evidence_bytes, usable_receipt
from tum_mcp.settings import Frozen


class Decision(Frozen):
    interval: Interval
    disposition: Literal["note", "highlight", "omit"]
    entry: Key | None = None
    reason: Text
    material: Key | None = None
    pages: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def target(self) -> "Decision":
        if (self.disposition == "omit") != (self.entry is None):
            raise ValueError("Notes and highlights name their entry; omissions have no entry.")
        return self


class Selection(Frozen):
    recording: Key
    transcript_sha256: Digest
    materials: tuple[SourceVersion, ...] = ()
    comparison_limits: tuple[Text, ...] = ()
    decisions: tuple[Decision, ...] = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def ordered(self) -> "Selection":
        distinct_intervals(tuple(decision.interval for decision in self.decisions))
        return self


def read_selection(root: Path, lecture: Lecture) -> Selection | None:
    body = read_bytes(private_path(root, f"lecture-review/{lecture.recording.key}.json"))
    return Selection.model_validate_json(body) if body is not None else None


def selection_problems(root: Path, lecture: Lecture, evidence: tuple[Evidence, ...]) -> list[str]:
    if lecture.recording.synthetic:
        return []
    try:
        selection = read_selection(root, lecture)
    except ValidationError:
        return ["The recording selection map is invalid. Use study schema lecture-selection."]
    if selection is None:
        return ["Record the full selection map before review, including omitted teaching."]
    receipt = usable_receipt(root, lecture.recording.key)
    # Comparison limits and unclear speech in omitted time are disclosed to the reviewer;
    # only a retained note or highlight that relies on unclear speech blocks the draft.
    problems: list[str] = []
    if (
        selection.recording != receipt.key
        or selection.transcript_sha256 != receipt.transcript_sha256
    ):
        problems.append("The selection map does not match the prepared transcript.")
    if merge_intervals(tuple(d.interval for d in selection.decisions)) != merge_intervals(
        receipt.validity.eligible
    ):
        problems.append("Selection decisions must partition all eligible recording time.")
    entries = {
        **{entry.key: "note" for entry in lecture.notes},
        **{entry.key: "highlight" for entry in lecture.highlights},
    }
    chosen = {decision.entry for decision in selection.decisions if decision.entry}
    if chosen != entries.keys() or any(
        decision.entry and entries.get(decision.entry) != decision.disposition
        for decision in selection.decisions
    ):
        problems.append("Every selected note and highlight must match its decision.")
    retained = merge_intervals(
        tuple(d.interval for d in selection.decisions if d.disposition != "omit")
    )
    problems.extend(
        f"Retained time {kept.start_s:g}-{kept.end_s:g} s overlaps missing or uncertain speech "
        f"at {gap.start_s:g}-{gap.end_s:g} s; omit that part with its reason."
        for kept in retained
        for gap in merge_intervals((*receipt.missing, *receipt.uncertain))
        if kept.start_s < gap.end_s and gap.start_s < kept.end_s
    )
    speech = {item.key: item.interval for item in evidence if item.kind != "frame"}
    for entry in lecture.entries:
        spans = tuple(speech[key] for key in entry.evidence if key in speech)
        if isinstance(entry, Highlight):
            spans = (*spans, entry.interval)
        if any(
            not any(kept.start_s <= span.start_s < span.end_s <= kept.end_s for kept in retained)
            for span in spans
        ):
            problems.append(f"{entry.key}: cited speech or clip includes time marked omitted.")
    resources = {source.resource.key: source for source in load_state(root).resources}
    compared = {source.key for source in selection.materials}
    for source in selection.materials:
        stored = resources.get(source.key)
        if (
            stored is None
            or stored.sha256 != source.sha256
            or stored.status != "current"
            or stored.path is None
            or (body := read_bytes(confined(root, stored.path))) is None
            or file_digest(body) != source.sha256
        ):
            problems.append(f"{source.key}: compared material is missing or stale.")
    if any(
        decision.material and decision.material not in compared for decision in selection.decisions
    ):
        problems.append("Each comparison must name one of the checked materials.")
    return problems


def selection_item(root: Path, lecture: Lecture) -> ReviewItem:
    try:
        selection = read_selection(root, lecture)
        selection_value: JsonValue = (
            selection.model_dump(mode="json") if selection else "Selection map missing."
        )
    except ValidationError:
        selection = None
        selection_value = "Selection map invalid."
    value = {
        "title": lecture.title,
        "summary": lecture.summary,
        "coverage": lecture.coverage.model_dump(mode="json"),
        "notes": [entry.model_dump(mode="json") for entry in lecture.notes],
        "highlights": [entry.model_dump(mode="json") for entry in lecture.highlights],
        "sources": [
            source.model_dump(mode="json")
            for source in dict.fromkeys(
                (*lecture.sources, *(selection.materials if selection else ()))
            )
        ],
        "selection": selection_value,
    }
    evidence: dict[str, JsonValue] = {"mode": "synthetic"}
    if not lecture.recording.synthetic:
        receipt = usable_receipt(root, lecture.recording.key)
        passages = PASSAGES.validate_json(evidence_bytes(root, receipt.key, "transcript.json"))
        evidence = {
            "recording": receipt.key,
            "as_of": receipt.checked_at,
            "transcript_sha256": receipt.transcript_sha256,
            "passages": [
                passage.model_dump(mode="json", exclude={"words"}, exclude_defaults=True)
                for passage in passages
            ],
        }
    return ReviewItem(
        f"lecture/{lecture.key}",
        "lecture-selection",
        lecture.title,
        value,
        blocks_of(value) | {"@recording-evidence": digest(evidence)},
        evidence=evidence,
    )
