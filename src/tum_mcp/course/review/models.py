"""Shared review vocabulary: dimensions, visual and media scores, report flags and passages."""

import datetime
import hashlib
import re
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, JsonValue, model_validator

from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.study import StudyContent, Text
from tum_mcp.course.ledger.coverage import CoverageLedger
from tum_mcp.course.media.audio import MediaFile
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.settings import Frozen

if TYPE_CHECKING:
    from tum_mcp.course.content.exam import ExamContent

Dimension = Literal[
    "correctness",
    "clarity",
    "cohesion",
    "cognitive_load",
    "representation",
    "practice",
    "coverage",
    "intuition",
    "organization",
    "redundancy",
]
DIMENSIONS: tuple[Dimension, ...] = (
    "correctness",
    "clarity",
    "cohesion",
    "cognitive_load",
    "representation",
    "practice",
    "coverage",
    "intuition",
    "organization",
    "redundancy",
)
CourseDimension = Literal["organization", "redundancy", "integration"]
# The rubric's reading passes; each reads the item for its own dimensions.
Pass = Literal["logic", "text", "visuals", "interaction", "intuition", "structure", "cheatsheet"]
# The cheatsheet is one item read in one pass, on the dimensions a revision reference has:
# no practice, intuition or teaching moves, and its own checks (rubric section Cheatsheet).
SHEET = "exam/sheet"


# A rubric check such as redundancy.text_restates_picture; its prefix is the finding's dimension.
Check = Annotated[str, Field(pattern=r"^[a-z_]+\.[a-z_]+$", max_length=80)]
Criterion = Literal["fidelity", "form", "layout", "legibility", "focus", "convention"]
CRITERIA: tuple[Criterion, ...] = (
    "fidelity",
    "form",
    "layout",
    "legibility",
    "focus",
    "convention",
)
# 1 blocks learning, 2 works with friction, 3 easy to learn from.
Score = Literal[1, 2, 3]
ItemKey = Annotated[
    str,
    Field(
        pattern=(
            r"^(study/[a-z0-9-]+|exercises/[a-z0-9-]+/[a-z0-9-]+|exam/pattern/[a-z0-9-]+"
            r"|exam/sheet)$"
        )
    ),
]
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
# The visual's address on the render check's contact sheets, such as block:3 or step:trace:0.
VisualKey = Annotated[
    str,
    Field(
        pattern=(
            r"^(block|statement|solution|transfer|"
            r"(question|step|compare|explore):[a-z0-9][a-z0-9_.-]*):[0-9]+$"
        )
    ),
]


def _own_check(dimension: str, check: str | None) -> None:
    if check and check.split(".")[0] != dimension:
        raise ValueError(f"Check {check} belongs to another dimension than {dimension}.")


class VisualReview(Frozen):
    """One drawn visual, scored from the contact sheets on each criterion of the visual rubric."""

    visual: VisualKey
    scores: dict[Criterion, Score]
    note: Text | None = None

    @model_validator(mode="after")
    def explained(self) -> "VisualReview":
        if set(self.scores) != set(CRITERIA):
            raise ValueError("Score every visual criterion: " + ", ".join(CRITERIA) + ".")
        if min(self.scores.values()) < 3 and not self.note:
            raise ValueError(f"{self.visual} scores below 3, so its note names what is wrong.")
        return self


def _found(scores: dict[str, int], findings: tuple["MediaFinding", ...]) -> None:
    found = {finding.dimension for finding in findings}
    if scored_high := [name for name, score in scores.items() if score == 3 and name in found]:
        raise ValueError(
            "A dimension with an accepted finding scores below 3: " + ", ".join(scored_high) + "."
        )
    if missing := [name for name, score in scores.items() if score < 3 and name not in found]:
        raise ValueError("A score below 3 names its finding: " + ", ".join(missing) + ".")


MediaDimension = Literal[
    "correctness",
    "clarity",
    "cognitive_load",
    "coverage",
    "intuition",
    "organization",
    "redundancy",
    "delivery",
    "representation",
    "synchronization",
]
AUDIO_DIMENSIONS: tuple[MediaDimension, ...] = (
    "correctness",
    "clarity",
    "cognitive_load",
    "coverage",
    "intuition",
    "organization",
    "redundancy",
    "delivery",
)
VIDEO_DIMENSIONS: tuple[MediaDimension, ...] = (
    *AUDIO_DIMENSIONS,
    "representation",
    "synchronization",
)
MediaKey = Annotated[
    str,
    Field(pattern=r"^(audio/[a-z0-9][a-z0-9_.-]{0,99}|video/\d{2,3}_[a-z0-9]+(?:-[a-z0-9]+)*)$"),
]
MediaVisualKey = Annotated[
    str,
    Field(pattern=r"^c\d{2}/b\d{2,3}(?:/[a-z0-9][a-z0-9_.-]{0,99})?$"),
]


class MediaInterval(Frozen):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded(self) -> "MediaInterval":
        if self.end <= self.start:
            raise ValueError("An inspected interval must have positive duration.")
        return self


class MediaEvidence(MediaFile):
    kind: Literal["script", "signal", "listening", "frames", "playback"]
    artifact_sha256: Digest
    intervals: tuple[MediaInterval, ...] = Field(default=(), max_length=1000)
    audio_perceived: bool = False
    guidance_sha256: Digest | None = None

    @model_validator(mode="after")
    def private(self) -> "MediaEvidence":
        if not self.path.startswith(
            (
                ".tum-mcp/media-review/",
                "audio/.build/",
                "videos/.build/",
                "videos/reviews/",
            )
        ):
            raise ValueError("Media evidence stays in private/build review roots.")
        if self.kind in {"listening", "playback"} and not self.intervals:
            raise ValueError("Perception evidence names the actual inspected intervals.")
        if self.kind not in {"listening", "playback"} and self.intervals:
            raise ValueError("Only perception evidence carries inspected intervals.")
        if self.audio_perceived and self.kind != "playback":
            raise ValueError("Only playback may also declare that its audio was perceived.")
        if self.kind == "script" and self.guidance_sha256 is None:
            raise ValueError("Script evidence records the current authoring guidance hash.")
        return self


class MediaFinding(Frozen):
    dimension: MediaDimension
    check: Check
    note: Text
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    chapter: Key | None = None
    beat: Key | None = None
    source_locator: Annotated[str, Field(min_length=1, max_length=300)] | None = None

    @model_validator(mode="after")
    def precise(self) -> "MediaFinding":
        _own_check(self.dimension, self.check)
        if (self.start is None) != (self.end is None):
            raise ValueError("A finding interval needs both start and end.")
        if self.start is not None and self.end <= self.start:
            raise ValueError("A finding interval must have positive duration.")
        if self.start is None and not (self.chapter or self.beat or self.source_locator):
            raise ValueError("Locate a media finding by interval, chapter/beat or source concept.")
        return self


class MediaVisualReview(VisualReview):
    visual: MediaVisualKey


class MediaReview(Frozen):
    item: MediaKey
    revision: Revision
    reviewed_at: datetime.date
    scores: dict[MediaDimension, Score]
    findings: tuple[MediaFinding, ...] = Field(default=(), max_length=100)
    visuals: tuple[MediaVisualReview, ...] = Field(default=(), max_length=780)
    evidence: tuple[MediaEvidence, ...] = Field(default=(), max_length=200)
    kept: Text | None = None

    @model_validator(mode="after")
    def explained(self) -> "MediaReview":
        _found(self.scores, self.findings)
        if any(self.scores.get(f.dimension) == 3 for f in self.findings):
            raise ValueError("A media finding names a dimension scored below 3 or still unscored.")
        if self.item.startswith("audio/") and (
            self.visuals
            or set(self.scores) - set(AUDIO_DIMENSIONS)
            or any(f.dimension not in AUDIO_DIMENSIONS for f in self.findings)
            or any(f.beat for f in self.findings)
            or any(e.kind in {"frames", "playback"} for e in self.evidence)
        ):
            raise ValueError("Audio reviews use audio dimensions, chapters and listening evidence.")
        if len({v.visual for v in self.visuals}) != len(self.visuals):
            raise ValueError("Score each media visual once.")
        weakest = min((min(v.scores.values()) for v in self.visuals), default=3)
        if self.scores.get("representation", 1) > weakest:
            raise ValueError("Representation scores no higher than the weakest video visual.")
        return self


# Flags that always mean a defect, and the dimension that cannot score 3 while one is open.
INVARIANT_FLAGS: dict[str, Dimension] = {
    "arithmetic": "correctness",
    "citation_page": "correctness",
    "answer_key": "correctness",
    "forward_term": "organization",
    # Each item links every existing workspace or records why none fits (Recall everywhere).
    "undecided_link": "cohesion",
    "plain_math": "cognitive_load",
    "dense_paragraph": "cognitive_load",
    # A rendered section with more than two authored paragraphs in a row (user decision).
    "prose_run": "representation",
    "generic_table": "representation",
    # A graph given as an edge list: a drawing with weighted edges teaches it (user decision).
    "graph_as_table": "representation",
    "all_of_above": "practice",
    "described_object": "representation",
    "prose_calculation": "representation",
    "compressed_working": "representation",
    "static_trace": "representation",
    "static_walkthrough": "representation",
    "dropped_node_value": "representation",
    "never_shown_nodes": "representation",
    "source_states_missing": "correctness",
    "source_phases_missing": "organization",
    "unworked_result": "representation",
    "text_only_question": "representation",
    "bare_workflow": "representation",
    "unlinked_map": "organization",
    "math_word": "representation",
    "meta_reference": "clarity",
    "repeated_title": "clarity",
    "statement_framing": "clarity",
    "summary_repeats_objective": "redundancy",
    "redundant_workflow_detail": "redundancy",
    # The cheatsheet: typed mathematics, and sources read for it without exam requirements.
    "sheet_plain_math": "representation",
    "sheet_dense_paragraph": "clarity",
    "method_without_steps": "coverage",
    "unguided_practice": "intuition",
    "unrecorded_sources": "coverage",
    # A listed past paper students cannot practise.
    "unreplayable_paper": "coverage",
}
# Advisory flags a checker must rule on before the gate passes: a finding on the check named
# here, or why the flag does not apply. A flag no one rules on is how a weak lesson passed.
RULED_FLAGS: dict[str, str] = {
    "repeated_step_reason": "intuition.reasons",
    "merged_step_operations": "representation.process_shown",
    "repeated_example": "redundancy.said_once",
    "duplicate_stage": "redundancy.said_once",
    "untitled_opening": "organization.outline",
    "trace_as_table": "representation.shape_fits",
    "text_only_question": "representation.picture_carries_data",
    "inline_list": "representation.shape_fits",
    "inline_steps": "representation.shape_fits",
    "definition_refined": "correctness.source_match",
    "no_visual": "representation.shape_fits",
    "unstepped_table": "representation.shape_fits",
    "slide_image": "representation.shape_fits",
    "thin_unit": "coverage.ledger_outcomes",
    "repeated_feedback": "practice.plausible_options",
    "long_section": "representation.shape_fits",
    "example_in_prose": "representation.shape_fits",
    "key_longest": "practice.plausible_options",
    "stem_key_overlap": "practice.plausible_options",
    "negative_stem": "clarity.one_reading",
    "exemplar_copy": "correctness.source_match",
}
# Invariant flags about the whole course rather than the item they are filed under: a scoped
# draft cannot clear them, so an item lint reports them and the review gate holds on them.
COURSE_WIDE_FLAGS = frozenset({"unrecorded_sources"})


def _flagged_items(
    item: str, content: StudyContent | None, exercises: ExerciseContent | None
) -> list[str]:
    """The review items a quality flag points into: a unit or exercise key, a block or step
    under it, or the JSON path of an arithmetic error."""
    if item.startswith(("study/", "exam/pattern/")) or item == SHEET:
        return [item]
    if item.startswith("concept:"):
        return [SHEET]
    if found := re.match(r"study:units\[(\d+)\]", item):
        return [f"study/{content.units[int(found[1])].key}"] if content else []
    if found := re.match(r"exercises:sets\[(\d+)\]\.exercises\[(\d+)\]", item):
        group = exercises.sets[int(found[1])] if exercises else None
        return [f"exercises/{group.key}/{group.exercises[int(found[2])].key}"] if group else []
    key = re.split(r"[#/]", item, maxsplit=1)[0]
    units = [f"study/{unit.key}" for unit in (content.units if content else ()) if unit.key == key]
    return units + [
        f"exercises/{group.key}/{exercise.key}"
        for group in (exercises.sets if exercises else ())
        for exercise in group.exercises
        if exercise.key == key
    ]


def revision(item: BaseModel) -> str:
    return hashlib.sha256(item.model_dump_json().encode()).hexdigest()[:16]


class Sheet(Frozen):
    """The cheatsheet as one reviewed item: its entries, the workflows they show and the
    requirements they are judged against, so any of them changing makes the review stale."""

    topics: list[JsonValue]
    concepts: list[JsonValue]
    links: list[JsonValue]
    workflows: list[JsonValue]
    requirements: list[JsonValue]


def sheet_model(exam: "ExamContent", ledger: CoverageLedger | None) -> Sheet:
    shown = {concept.workflow_from for concept in exam.concepts if concept.workflow_from}
    return Sheet(
        topics=[item.model_dump(mode="json") for item in exam.topics],
        concepts=[item.model_dump(mode="json", exclude_none=True) for item in exam.concepts],
        links=[item.model_dump(mode="json", exclude_none=True) for item in exam.links],
        workflows=[
            {
                "pattern": pattern.key,
                "title": pattern.title,
                "workflow": [
                    step.model_dump(mode="json", exclude_none=True) for step in pattern.workflow
                ],
            }
            for pattern in exam.patterns
            if pattern.key in shown
        ],
        requirements=[
            {"source": entry.source, **item.model_dump(mode="json", exclude_none=True)}
            for entry in (ledger.sources if ledger else ())
            for item in entry.exam
        ],
    )


# Fields that carry no text a student reads, or markup a quote cannot come from.
_UNREAD = {
    "key",
    "sources",
    "source_versions",
    "pages",
    "svg",
    "mathml",
    "image",
    "revision",
    "anchor",
    "unit",
    "topic",
    "basis",
    "tier",
    "workflow_from",
}


def item_passages(value: JsonValue, path: str = "") -> list[tuple[str, str]]:
    """The text a student reads in an item, as (path, text) pairs in reading order."""
    if isinstance(value, dict):
        return [
            pair
            for key, item in value.items()
            if key not in _UNREAD
            for pair in item_passages(item, f"{path}.{key}" if path else key)
        ]
    if isinstance(value, list):
        return [
            pair for i, item in enumerate(value) for pair in item_passages(item, f"{path}[{i}]")
        ]
    return [(path, value)] if isinstance(value, str) and value.strip() else []


def _plain(text: str) -> str:
    return " ".join(text.replace("\\(", " ").replace("\\)", " ").split())


def quoted(quote: str, passages: list[tuple[str, str]]) -> bool:
    """Whether a quote occurs word for word in the item (spacing and inline-math delimiters
    aside)."""
    wanted = _plain(quote).strip(" .\"'“”‘’…")
    return bool(wanted) and any(wanted in _plain(text) for _, text in passages)
