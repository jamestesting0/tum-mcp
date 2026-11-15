"""Lecture highlights: the timed stretches of a recording worth watching."""

import hashlib
import json
from itertools import pairwise
from typing import Annotated, Literal, assert_never, cast

from pydantic import AfterValidator, Field, model_validator

from tum_mcp.course.content.latex import validate_inline
from tum_mcp.course.content.study import (
    CodeBlock,
    DerivationBlock,
    DiagramBlock,
    FigureBlock,
    FormulaBlock,
    GridBlock,
    PlotBlock,
    SourceVersion,
    Step,
    TableBlock,
    Text,
    TreeBlock,
    UmlBlock,
    check_subgoals,
)
from tum_mcp.course.lecture.evidence import (
    Evidence,
    Interval,
    LectureCoverage,
    Recording,
    Thumbnail,
    merge_intervals,
)
from tum_mcp.course.project.models import Digest, Key, PageRange
from tum_mcp.settings import Frozen

# One sentence or one claim each: long fields drift from what the interval shows.
Title = Annotated[str, Field(min_length=1, max_length=160), AfterValidator(validate_inline)]
Line = Annotated[str, Field(min_length=1, max_length=400), AfterValidator(validate_inline)]
Point = Annotated[str, Field(min_length=1, max_length=300), AfterValidator(validate_inline)]
Summary = Annotated[str, Field(min_length=1, max_length=600), AfterValidator(validate_inline)]


class NoteImage(Thumbnail):
    """A recording frame that carries the note's point: the slide or board work it explains,
    cropped to that object and legible on a phone. Never the speaker or a title slide."""

    alt: Line


NoteTitle = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(validate_inline)]
Context = Annotated[str, Field(min_length=1, max_length=300), AfterValidator(validate_inline)]
# What a note shows instead of describing it. The note's own fields carry its prose, and a
# stepped run is a highlight or a Study lesson, so text-like blocks and walkthroughs stay out.
NoteBlock = Annotated[
    FormulaBlock
    | DerivationBlock
    | TableBlock
    | DiagramBlock
    | CodeBlock
    | PlotBlock
    | UmlBlock
    | TreeBlock
    | FigureBlock
    | GridBlock,
    Field(discriminator="kind"),
]
# Older files labelled every note; only these two change what a student does.
RETIRED_KINDS = frozenset({"clarification", "example", "intuition"})


class Chapter(Frozen):
    """One topic of the lecture, in recording order: its title in the course's terms, the time
    it was taught and the pages it was taught from. Each highlight lies inside one chapter;
    administration and breaks between chapters belong to none, and a note made there (an exam
    instruction, say) stands at its own time."""

    key: Key
    title: NoteTitle
    interval: Interval
    sources: tuple[Key, ...] = Field(default=(), max_length=5)
    pages: PageRange | None = None

    @model_validator(mode="after")
    def located(self) -> "Chapter":
        if self.pages is not None and not self.sources:
            raise ValueError("Chapter pages need the source they belong to.")
        return self


class NotePassage(Frozen):
    """The Study block that teaches the note's subject; Recall opens it beside the page."""

    unit: Key
    block: Key


def _plain(text: str) -> str:
    return " ".join(text.split()).casefold().rstrip(".")


class Note(Frozen):
    """One addition from the lecture that a student who skipped it can use alone: a condition,
    correction, instruction or the lecturer's own working. The context sets up the situation,
    the text gives the takeaway with its condition, steps hold the working and blocks show the
    object (a formula, graph or code) instead of describing it. Never narrate the recording."""

    key: Key
    # What the note concerns, in the course's terms.
    title: NoteTitle
    # The situation the remark responds to, so a student who missed the lecture sees why it
    # matters: what the slide states, a question asked, the usual approach it corrects.
    context: Context
    # The message itself: the caveat, rule, correction or instruction, with its conditions.
    text: Line
    # A label only where it changes what the student does: a correction of the materials or an
    # explicit exam instruction.
    kind: Literal["correction", "exam tip"] | None = None
    # The working, conditions or example the lecturer gave, one claim per point or step.
    points: tuple[Line, ...] = Field(default=(), max_length=4)
    steps: tuple[Line, ...] = Field(default=(), max_length=6)
    passage: NotePassage | None = None
    sources: tuple[Key, ...] = Field(default=(), max_length=5)
    pages: PageRange | None = None
    evidence: tuple[Key, ...] = Field(min_length=1, max_length=20)
    image: NoteImage | None = None
    blocks: tuple[NoteBlock, ...] = Field(default=(), max_length=3)

    @model_validator(mode="before")
    @classmethod
    def legacy(cls, value: object) -> object:
        # Older notes carry one `figure` and five kinds of label; they load with the same meaning.
        if not isinstance(value, dict):
            return value
        fields = dict(cast(dict[str, object], value))
        if (figure := fields.pop("figure", None)) is not None:
            blocks = cast("list[object] | tuple[object, ...]", fields.get("blocks", ()))
            fields["blocks"] = [figure, *blocks]
        if fields.get("kind") in RETIRED_KINDS:
            fields["kind"] = None
        return fields

    @model_validator(mode="after")
    def located(self) -> "Note":
        if self.pages is not None and not self.sources:
            raise ValueError("Note pages need the source they belong to.")
        if any(not set(block.sources) <= set(self.sources) for block in self.blocks):
            raise ValueError("A note block must cite the note's declared sources.")
        context, text = _plain(self.context), _plain(self.text)
        if context in text or text in context:
            raise ValueError("A note's context sets up its message; it does not repeat it.")
        return self


class Highlight(Frozen):
    """A stretch worth watching, from the question or setup that opens it to its conclusion
    and any later correction. The title names the particular question or example, `teaches`
    says what the student learns with its condition, points never repeat it, and each step
    names its own moment in the recording."""

    key: Key
    title: Title
    interval: Interval
    teaches: Line
    points: tuple[Point, ...] = Field(default=(), max_length=3)
    # Course materials (slides, script) this stretch relates to; pages belong to the first.
    sources: tuple[Key, ...] = Field(default=(), max_length=5)
    pages: PageRange | None = None
    evidence: tuple[Key, ...] = Field(min_length=2, max_length=20)
    thumbnail: Thumbnail
    # The explanation's own stages, each at its moment in the recording.
    steps: tuple[Step, ...] = Field(default=(), max_length=12)
    passage: NotePassage | None = None

    @model_validator(mode="after")
    def located(self) -> "Highlight":
        if self.pages is not None and not self.sources:
            raise ValueError("Highlight pages need the source they belong to.")
        if len(self.steps) == 1:
            raise ValueError("A highlight with steps has at least two; one stage is the whole.")
        check_subgoals(self.steps)
        times = [step.at for step in self.steps]
        if any(at is None or not self.interval.start_s <= at < self.interval.end_s for at in times):
            raise ValueError("Each highlight step has a time inside the highlight.")
        if times != sorted(set(times)):
            raise ValueError("Highlight steps follow the recording, each at its own time.")
        return self


def _note_visuals(note: Note) -> dict[str, object]:
    """A note's blocks for its semantic revision; a migrated lone figure hashes as before."""
    if len(note.blocks) == 1 and isinstance(note.blocks[0], FigureBlock):
        return {"figure": note.blocks[0].model_dump(mode="json")}
    if not note.blocks:
        return {"figure": None}
    return {"figure": None, "blocks": [block.model_dump(mode="json") for block in note.blocks]}


class Lecture(Frozen):
    """One recorded lecture. The title names its topic, never the date; the summary says what
    the lecture teaches, never the recording or the notes. Chapters follow its topics in
    recording order."""

    key: Key
    title: Text
    recording: Recording
    summary: Summary
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=100)
    checked_at: Annotated[str, Field(min_length=1, max_length=100)]
    coverage: LectureCoverage
    chapters: tuple[Chapter, ...] = Field(default=(), max_length=60)
    notes: tuple[Note, ...] = Field(default=(), max_length=100)
    highlights: tuple[Highlight, ...] = Field(default=(), max_length=40)

    @property
    def entries(self) -> tuple[Note | Highlight, ...]:
        return self.notes + self.highlights

    @property
    def images(self) -> tuple[Thumbnail, ...]:
        return tuple(note.image for note in self.notes if note.image is not None) + tuple(
            highlight.thumbnail for highlight in self.highlights
        )

    @property
    def semantic_revision(self) -> Digest:
        """Hash authored teaching and timing; source freshness is checked independently."""
        payload = {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "notes": [
                {
                    "key": note.key,
                    "title": note.title,
                    "context": note.context,
                    "text": note.text,
                    **_note_visuals(note),
                    "image": (
                        {"sha256": note.image.sha256, "alt": note.image.alt}
                        if note.image is not None
                        else None
                    ),
                }
                for note in self.notes
            ],
            "highlights": [
                {
                    "key": highlight.key,
                    "title": highlight.title,
                    "interval": highlight.interval.model_dump(mode="json"),
                    "teaches": highlight.teaches,
                    "points": highlight.points,
                    "steps": [step.model_dump(mode="json") for step in highlight.steps],
                    "passage": (
                        highlight.passage.model_dump(mode="json") if highlight.passage else None
                    ),
                }
                for highlight in self.highlights
            ],
            # Added only when present, so a lecture without chapters keeps its revision.
            **(
                {
                    "chapters": [
                        chapter.model_dump(mode="json", exclude={"sources", "pages"})
                        for chapter in self.chapters
                    ]
                }
                if self.chapters
                else {}
            ),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @model_validator(mode="after")
    def integrity(self) -> "Lecture":
        for collection in ((*self.entries, *self.chapters), self.sources):
            if len({item.key for item in collection}) != len(collection):
                raise ValueError("Lecture chapter, note, highlight and source keys must be unique.")
        source_ids = {item.key for item in self.sources}
        if any(not set(item.sources) <= source_ids for item in (*self.entries, *self.chapters)):
            raise ValueError("Lecture entry or chapter cites an undeclared source.")
        for first, second in pairwise(self.chapters):
            if first.interval.end_s > second.interval.start_s:
                raise ValueError("Chapters must be in recording order and must not overlap.")
        if self.chapters and self.chapters[-1].interval.end_s > self.recording.duration_s:
            raise ValueError("Each chapter must lie inside the recording.")
        if self.chapters and any(
            not any(_within(highlight.interval, chapter.interval) for chapter in self.chapters)
            for highlight in self.highlights
        ):
            raise ValueError("Each highlight must lie inside one chapter.")
        for first, second in zip(self.highlights, self.highlights[1:], strict=False):
            if first.interval.end_s > second.interval.start_s:
                raise ValueError("Highlights must be in recording order and must not overlap.")
        processed = merge_intervals(self.coverage.processed)
        for highlight in self.highlights:
            if not any(
                span.start_s <= highlight.interval.start_s < highlight.interval.end_s <= span.end_s
                for span in processed
            ):
                raise ValueError("Each highlight must lie inside processed recording time.")
        combined = merge_intervals(self.coverage.eligible + self.coverage.excluded)
        if combined != (Interval(start_s=0, end_s=self.recording.duration_s),):
            raise ValueError("Eligible and excluded intervals must partition the actual recording.")
        return self


def _within(inner: Interval, outer: Interval) -> bool:
    return outer.start_s <= inner.start_s < inner.end_s <= outer.end_s


class LectureContent(Frozen):
    schema_version: Literal[3] = 3
    course_key: Key
    lectures: tuple[Lecture, ...] = Field(min_length=1, max_length=300)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=30000)

    @model_validator(mode="after")
    def references(self) -> "LectureContent":
        if len({item.key for item in self.lectures}) != len(self.lectures):
            raise ValueError("Lecture keys must be unique.")
        evidence = {item.key: item for item in self.evidence}
        if len(evidence) != len(self.evidence):
            raise ValueError("Evidence keys must be unique.")
        used: set[str] = set()
        for lecture in self.lectures:
            sources = {item.key: item.sha256 for item in lecture.sources}
            processed = merge_intervals(lecture.coverage.processed)
            for entry in lecture.entries:
                selected = set(entry.evidence)
                if not selected <= evidence.keys():
                    raise ValueError("Lecture entry references unknown evidence.")
                speech = [evidence[key] for key in selected if evidence[key].kind != "frame"]
                if not speech:
                    raise ValueError("Each lecture entry needs transcript evidence.")
                match entry:
                    case Highlight():
                        if any(not _within(item.interval, entry.interval) for item in speech):
                            raise ValueError(
                                "Each highlight needs transcript evidence inside its own interval."
                            )
                        image = entry.thumbnail
                        spans = (entry.interval,)
                    case Note():
                        image = entry.image
                        spans = tuple(item.interval for item in speech)
                    case unreachable:
                        assert_never(unreachable)
                if image is not None:
                    frame = evidence.get(image.evidence)
                    if (
                        image.evidence not in selected
                        or frame is None
                        or frame.kind != "frame"
                        or not frame.interval.start_s <= image.captured_at_s <= frame.interval.end_s
                        or not any(
                            span.start_s <= image.captured_at_s <= span.end_s for span in spans
                        )
                    ):
                        raise ValueError(
                            "A lecture image needs declared frame evidence inside its entry."
                        )
                for key in selected:
                    item = evidence[key]
                    if sources.get(item.source_key) != item.source_sha256:
                        raise ValueError("Evidence must match a declared source version.")
                    if item.recording_id != lecture.recording.recording_id or not any(
                        _within(item.interval, span) for span in processed
                    ):
                        raise ValueError(
                            "Evidence must belong to processed time of this recording."
                        )
                    if lecture.coverage.status == "complete" and (
                        not item.reviewed or item.uncertainty
                    ):
                        raise ValueError(
                            "Complete highlights require reviewed, resolved cited evidence."
                        )
                    used.add(key)
        if used != evidence.keys():
            raise ValueError("Remove unused evidence from the authored highlights document.")
        return self
