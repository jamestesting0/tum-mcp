"""The author's complete recording selection and its independent review evidence."""

from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.course.content.study import SourceVersion, Text
from tum_mcp.course.lecture.content import Highlight, Lecture
from tum_mcp.course.lecture.evidence import Evidence, Interval, distinct_intervals, merge_intervals
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.course.project.store import (
    Write,
    apply,
    confined,
    load_state,
    private_name,
    private_path,
    read_bytes,
)
from tum_mcp.course.project.store import digest as file_digest
from tum_mcp.course.review.items import ReviewItem, blocks_of, digest
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.receipts import (
    PASSAGES,
    PreparedReceipt,
    evidence_bytes,
    usable_receipt,
)
from tum_mcp.settings import Frozen


class Decision(Frozen):
    """One stretch of eligible recording time and what became of it: a note, a highlight or an
    omission. The reason names what the cited pages already explain, what the recording adds
    and what the student gains; a topic name alone is not a reason. A decision never
    crosses a chapter boundary."""

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


class WorkingSelection(Frozen):
    recording: Key
    transcript_sha256: Digest
    materials: tuple[SourceVersion, ...] = ()
    comparison_limits: tuple[Text, ...] = ()
    decisions: tuple[Decision, ...] = Field(default=(), max_length=3000)

    @model_validator(mode="after")
    def ordered(self) -> "WorkingSelection":
        distinct_intervals(tuple(decision.interval for decision in self.decisions))
        return self


class Selection(WorkingSelection):
    decisions: tuple[Decision, ...] = Field(min_length=1, max_length=3000)


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
    return _selection_problems(root, lecture, evidence, selection, receipt)


def _selection_problems(
    root: Path,
    lecture: Lecture,
    evidence: tuple[Evidence, ...],
    selection: Selection,
    receipt: PreparedReceipt,
) -> list[str]:
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
    # A decision stays within one topic, so an omission's reason speaks for one chapter.
    boundaries = sorted(
        {
            edge
            for chapter in lecture.chapters
            for edge in (chapter.interval.start_s, chapter.interval.end_s)
        }
    )
    problems.extend(
        f"Decision {decision.interval.start_s:g}-{decision.interval.end_s:g} s crosses the "
        f"chapter boundary at {edge:g} s; split it there."
        for decision in selection.decisions
        for edge in boundaries
        if decision.interval.start_s < edge < decision.interval.end_s
    )
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
    compared = {source.key for source in selection.materials}
    problems.extend(
        f"{key}: compared material is missing or stale."
        for key in sorted(_stale_materials(root, selection.materials))
    )
    if any(
        decision.material and decision.material not in compared for decision in selection.decisions
    ):
        problems.append("Each comparison must name one of the checked materials.")
    return problems


def _stale_materials(root: Path, materials: tuple[SourceVersion, ...]) -> set[str]:
    resources = {source.resource.key: source for source in load_state(root).resources}
    return {
        source.key
        for source in materials
        if (stored := resources.get(source.key)) is None
        or stored.sha256 != source.sha256
        or stored.status != "current"
        or stored.path is None
        or (body := read_bytes(confined(root, stored.path))) is None
        or file_digest(body) != source.sha256
    }


class SelectionProgress(Frozen):
    recording: Key
    transcript_sha256: Digest
    next_interval: Interval | None
    decisions: tuple[Decision, ...] = ()
    materials: tuple[SourceVersion, ...] = ()
    comparison_limits: tuple[Text, ...] = ()
    problems: tuple[str, ...] = ()
    ready_to_finalize: bool = False


def _first_gap(eligible: tuple[Interval, ...], decisions: tuple[Decision, ...]) -> Interval | None:
    for span in eligible:
        cursor = span.start_s
        for decision in decisions:
            if decision.interval.end_s <= cursor or decision.interval.start_s >= span.end_s:
                continue
            if decision.interval.start_s > cursor:
                return Interval(start_s=cursor, end_s=decision.interval.start_s)
            cursor = decision.interval.end_s
        if cursor < span.end_s:
            return Interval(start_s=cursor, end_s=span.end_s)
    return None


def selection_progress(root: Path, receipt: PreparedReceipt) -> SelectionProgress:
    path = private_path(root, f"work/lecture-selection/{receipt.key}.json")
    body = read_bytes(path)
    checkpoint = WorkingSelection(
        recording=receipt.key, transcript_sha256=receipt.transcript_sha256
    )
    problems: list[str] = []
    if body is not None:
        try:
            saved = WorkingSelection.model_validate_json(body)
        except ValidationError:
            problems.append(
                "The working selection is invalid. Use study schema lecture-selection-work."
            )
        else:
            if (
                saved.recording != receipt.key
                or saved.transcript_sha256 != receipt.transcript_sha256
            ):
                problems.append("The working selection belongs to another transcript; start again.")
            else:
                checkpoint = saved
    stale = _stale_materials(root, checkpoint.materials)
    problems.extend(
        f"{key}: repeat the comparison against current material." for key in sorted(stale)
    )
    usable = {source.key for source in checkpoint.materials} - stale
    eligible = merge_intervals(receipt.validity.eligible)
    decisions: list[Decision] = []
    for decision in checkpoint.decisions:
        if not any(
            span.start_s <= decision.interval.start_s < decision.interval.end_s <= span.end_s
            for span in eligible
        ):
            problems.append(
                f"Decision at {decision.interval.start_s:g} s is outside eligible time."
            )
        elif decision.material is None or decision.material in usable:
            decisions.append(decision)
    kept = tuple(sorted(decisions, key=lambda decision: decision.interval.start_s))
    next_interval = _first_gap(eligible, kept)
    return SelectionProgress(
        recording=receipt.key,
        transcript_sha256=receipt.transcript_sha256,
        next_interval=next_interval,
        decisions=kept,
        materials=tuple(source for source in checkpoint.materials if source.key in usable),
        comparison_limits=checkpoint.comparison_limits,
        problems=tuple(problems),
        ready_to_finalize=bool(kept) and next_interval is None and not problems,
    )


def finalize_selection(root: Path, receipt: PreparedReceipt) -> None:
    from tum_mcp.course.lecture.data import read_lectures

    progress = selection_progress(root, receipt)
    if not progress.ready_to_finalize:
        detail = progress.problems[0] if progress.problems else "Finish every eligible interval."
        raise CampusError(Code.ACTION_REQUIRED, detail)
    content = read_lectures(root)
    matches = (
        [item for item in content.lectures if item.recording.key == receipt.key] if content else []
    )
    if len(matches) != 1 or content is None or matches[0].recording != receipt.recording:
        raise CampusError(Code.ACTION_REQUIRED, "Write one lecture for the prepared recording.")
    selection = Selection(
        recording=receipt.key,
        transcript_sha256=receipt.transcript_sha256,
        materials=progress.materials,
        comparison_limits=progress.comparison_limits,
        decisions=progress.decisions,
    )
    problems = _selection_problems(root, matches[0], content.evidence, selection, receipt)
    if problems:
        raise CampusError(Code.ACTION_REQUIRED, problems[0])
    target = f"lecture-review/{receipt.key}.json"
    apply(
        root,
        (
            Write(
                private_name(root, target),
                read_bytes(private_path(root, target)),
                selection.model_dump_json(indent=2).encode() + b"\n",
            ),
        ),
    )


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
        # Only when present, so an unchanged older lecture keeps its reviewed revision.
        **(
            {"chapters": [chapter.model_dump(mode="json") for chapter in lecture.chapters]}
            if lecture.chapters
            else {}
        ),
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
