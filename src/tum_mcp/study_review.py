"""The review scorecard: how a separate reading scored each Study unit, exercise and the course.

Scores are judgement, so the reviewing agent writes them. Code ties each review to the exact
content it read, so a changed unit or exercise needs a fresh review, and the course review
follows the course's structure. The report lists what is unreviewed, stale or below the bar.
"""

import datetime
import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, JsonValue, ValidationError, model_validator

from tum_mcp.audio_content import MediaFile
from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.settings import Frozen
from tum_mcp.study_content import StudyContent, Text
from tum_mcp.study_coverage import CoverageLedger
from tum_mcp.study_models import Digest, Key, StudyState
from tum_mcp.study_store import private_path

if TYPE_CHECKING:
    from tum_mcp.exam_content import ExamContent
    from tum_mcp.lecture_content import LectureContent
    from tum_mcp.study_media import MediaInventory

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
PASSES: dict[str, tuple[str, ...]] = {
    "logic": ("correctness", "coverage"),
    "text": ("clarity", "cohesion", "cognitive_load"),
    "visuals": ("representation",),
    "interaction": ("practice",),
    "intuition": ("intuition",),
    "structure": ("organization", "redundancy"),
}
# The cheatsheet is one item read in one pass, on the dimensions a revision reference has:
# no practice, intuition or teaching moves, and its own checks (rubric section Cheatsheet).
SHEET = "exam/sheet"
SHEET_PASSES: dict[str, tuple[str, ...]] = {
    "cheatsheet": (
        "correctness",
        "coverage",
        "clarity",
        "representation",
        "organization",
        "redundancy",
    ),
}


def item_passes(item: str) -> dict[str, tuple[str, ...]]:
    return SHEET_PASSES if item == SHEET else PASSES


def item_dimensions(item: str) -> tuple[str, ...]:
    return SHEET_PASSES["cheatsheet"] if item == SHEET else DIMENSIONS


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


class Finding(Frozen):
    """What a student meets that costs a point, named precisely enough to fix: the passage
    quoted word for word from the item, then the authoring side's verdict on it."""

    dimension: Dimension
    check: Check | None = None
    note: Text
    quote: Text | None = None
    fix: Text | None = None
    # The authoring session accepts a finding (and fixes it) or rejects it with its reason;
    # only accepted findings count against a score.
    status: Literal["accepted", "rejected"] = "accepted"
    reason: Text | None = None
    score: Literal[1, 2] = 2
    location: Text | None = None

    @model_validator(mode="after")
    def checked(self) -> "Finding":
        _own_check(self.dimension, self.check)
        if self.status == "rejected" and not self.reason:
            raise ValueError("A rejected finding says why the content is right as written.")
        return self


class CourseFinding(Frozen):
    """What costs the course a point, naming the units, exercises or links where it shows."""

    dimension: CourseDimension
    check: Check | None = None
    note: Text

    @model_validator(mode="after")
    def checked(self) -> "CourseFinding":
        _own_check(self.dimension, self.check)
        return self


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


class KeptPrompt(Frozen):
    """A report prompt left as it is, with the reason the content is right as written."""

    flag: Annotated[str, Field(pattern=r"^[a-z_]+$", max_length=60)]
    reason: Text


class ClosestCall(Frozen):
    quote: Text
    location: Text
    reason: Text


class ItemReview(Frozen):
    item: ItemKey
    revision: Revision
    reviewed_at: datetime.date
    scores: dict[Dimension, Score]
    findings: tuple[Finding, ...] = Field(default=(), max_length=30)
    visuals: tuple[VisualReview, ...] = Field(default=(), max_length=80)
    # The passage that earns each 3, quoted from the item; the report lists 3s without one.
    evidence: dict[Dimension, Text] = Field(default_factory=dict)
    kept: Text | None = None
    # Each report prompt open on the item at review time that is kept, with its reason; a
    # fixed prompt leaves the report instead.
    prompts: tuple[KeptPrompt, ...] = Field(default=(), max_length=40)
    # The rubric passes that read the item, and whether each ran in a session that did not
    # write the content ("fresh") or in the authoring session ("same").
    passes: dict[Pass, Literal["fresh", "same"]] = Field(default_factory=dict)
    closest_calls: dict[Check, ClosestCall] = Field(default_factory=dict)

    @model_validator(mode="after")
    def explained(self) -> "ItemReview":
        # A review saved before a dimension existed still loads; the report lists what it lacks.
        _found(self.scores, tuple(f for f in self.findings if f.status == "accepted"))
        for dimension, score in self.scores.items():
            derived = min(
                (
                    finding.score
                    for finding in self.findings
                    if finding.status == "accepted" and finding.dimension == dimension
                ),
                default=3,
            )
            if score != derived:
                raise ValueError(f"{dimension} scores {derived} from its verified findings.")
        if len({visual.visual for visual in self.visuals}) != len(self.visuals):
            raise ValueError("Score each visual once.")
        weakest = min((min(visual.scores.values()) for visual in self.visuals), default=3)
        if self.scores.get("representation", 1) > weakest:
            raise ValueError("Representation scores no higher than the item's weakest visual.")
        return self


class CourseReview(Frozen):
    """The course as a whole: order and categories, repetition, and links between workspaces."""

    revision: Revision
    knowledge_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    reviewed_at: datetime.date
    # Integration also covers media linked to a single prepared workspace.
    scores: dict[CourseDimension, Score]
    findings: tuple[CourseFinding, ...] = Field(default=(), max_length=40)
    kept: Text | None = None

    @model_validator(mode="after")
    def explained(self) -> "CourseReview":
        _found(self.scores, self.findings)
        return self


def _found(
    scores: dict[str, int], findings: tuple["Finding | CourseFinding | MediaFinding", ...]
) -> None:
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
    Field(pattern=r"^c\d{2}/b\d{2,3}/[a-z0-9][a-z0-9_.-]{0,99}$"),
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


class ReviewScorecard(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    reviews: tuple[ItemReview, ...] = Field(max_length=1000)
    course: CourseReview | None = None
    media: tuple[MediaReview, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def distinct(self) -> "ReviewScorecard":
        if len({review.item for review in self.reviews}) != len(self.reviews):
            raise ValueError("Review each item once.")
        if len({review.item for review in self.media}) != len(self.media):
            raise ValueError("Review each media item once.")
        return self


def scorecard_path(root: Path) -> Path:
    return private_path(root, "review.json")


def read_scorecard(root: Path) -> ReviewScorecard | None:
    path = scorecard_path(root)
    if not path.exists():
        return None
    try:
        return ReviewScorecard.model_validate_json(path.read_bytes())
    except ValidationError as error:
        problems = [
            ".".join(map(str, item["loc"])) + ": " + item["msg"]
            for item in error.errors(include_input=False)
        ]
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Invalid review scorecard: " + "; ".join(problems[:5]) + ". See study schema review.",
        ) from None


# Flags that always mean a defect, and the dimension that cannot score 3 while one is open.
INVARIANT_FLAGS: dict[str, Dimension] = {
    "arithmetic": "correctness",
    "forward_term": "organization",
    "plain_math": "cognitive_load",
    "dense_paragraph": "cognitive_load",
    "described_object": "representation",
    "prose_calculation": "representation",
    "compressed_working": "representation",
    "meta_reference": "clarity",
    "statement_framing": "clarity",
    "summary_repeats_objective": "redundancy",
    # The cheatsheet: typed mathematics, and sources read for it without exam requirements.
    "sheet_plain_math": "representation",
    "sheet_dense_paragraph": "clarity",
    "unrecorded_sources": "coverage",
}


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


def rubric_checks(item: str = "") -> dict[str, tuple[str, ...]]:
    """Every check the bundled rubric lists for an item, by dimension: the item rubric, or the
    Cheatsheet section for the cheatsheet."""
    from importlib.resources import files

    rubric = files("tum_mcp").joinpath("bundled/skills/review-course/references/rubric.md")
    checks: dict[str, list[str]] = {}
    text = rubric.read_text()
    item_rubric = (
        text.split("\n## Cheatsheet\n")[1].split("\n## ")[0]
        if item == SHEET
        else text.split("## Course organization")[0]
    )
    for dimension, name in re.findall(r"^- `([a-z_]+)\.([a-z_]+)`", item_rubric, re.M):
        checks.setdefault(dimension, []).append(f"{dimension}.{name}")
    return {dimension: tuple(names) for dimension, names in checks.items()}


FLAG_CHECKS = {
    "arithmetic": "correctness.recomputed",
    "forward_term": "organization.dependency_order",
    "plain_math": "cognitive_load.math_set",
    "dense_paragraph": "cognitive_load.short_prose",
    "described_object": "representation.shown_not_described",
    "prose_calculation": "representation.working_shown",
    "compressed_working": "representation.working_shown",
    "meta_reference": "clarity.no_meta",
    "statement_framing": "clarity.no_meta",
    "unexplained_symbol": "clarity.symbols_recall",
    "echoed_meaning": "redundancy.said_once",
    "sheet_plain_math": "representation.sheet_form",
    "slash_quotient": "representation.sheet_form",
    "line_repeats_formula": "redundancy.sheet_expansion",
    "sheet_dense_paragraph": "clarity.sheet_concise",
    "prose_legend": "clarity.sheet_meanings",
    "unrecorded_sources": "coverage.sheet_inventory",
}


def deterministic_checks(flags: Sequence[dict[str, JsonValue]]) -> dict[str, str]:
    # Detectors establish failures, not a clean bill for semantic checks they only partly cover.
    return {
        FLAG_CHECKS[str(flag["flag"])]: (
            "fail" if str(flag["flag"]) in INVARIANT_FLAGS else "prompt"
        )
        for flag in flags
        if str(flag["flag"]) in FLAG_CHECKS
    }


def review_pack(
    item: str,
    name: str,
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: "ExamContent | None",
    flags: Sequence[dict[str, JsonValue]],
    ledger: CoverageLedger | None = None,
) -> dict[str, JsonValue]:
    """What one pass needs to read one item: its checks with their wording, the item's text by
    path, and the report prompts already decided for it."""
    from importlib.resources import files

    models = item_models(content, exercises, exam, ledger)
    if item not in models:
        raise CampusError(Code.ACTION_REQUIRED, f"No reviewed item {item}; see the report.")
    if name not in item_passes(item):
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"{item} is read in the passes " + ", ".join(item_passes(item)) + ".",
        )
    rubric = files("tum_mcp").joinpath("bundled/skills/review-course/references/rubric.md")
    wording = {
        check: " ".join(text.split()).removeprefix(": ")
        for check, text in re.findall(
            r"^- `([a-z_]+\.[a-z_]+)`((?: \([^)]*\))?: .+?)(?=\n- `|\n\n|\Z)",
            rubric.read_text(),
            re.M | re.S,
        )
    }
    dimensions = item_passes(item)[name]
    relevant = [
        flag for flag in flags if item in _flagged_items(str(flag["item"]), content, exercises)
    ]
    determined = deterministic_checks(relevant)
    return {
        "item": item,
        "revision": revision(models[item]),
        "pass": name,
        "dimensions": list(dimensions),
        "checks": [
            {
                "check": check,
                "text": wording.get(check, ""),
                "verdict": determined.get(check, "review"),
            }
            for dimension in dimensions
            for check in rubric_checks(item).get(dimension, ())
        ],
        "report": [
            {
                "flag": flag["flag"],
                "detail": flag["detail"],
                "decision": "fix" if str(flag["flag"]) in INVARIANT_FLAGS else "fix or keep",
            }
            for flag in relevant
        ],
        "passages": [
            {"path": path, "text": text}
            for path, text in item_passages(models[item].model_dump(mode="json"))
        ],
    }


def item_models(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: "ExamContent | None" = None,
    ledger: CoverageLedger | None = None,
) -> dict[str, BaseModel]:
    """Every reviewed item's content, by item key."""
    items: dict[str, BaseModel] = {
        f"study/{unit.key}": unit for unit in (content.units if content else ())
    }
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            items[f"exercises/{group.key}/{exercise.key}"] = exercise
    for pattern in exam.patterns if exam else ():
        items[f"exam/pattern/{pattern.key}"] = pattern
    if exam and exam.concepts:
        items[SHEET] = sheet_model(exam, ledger)
    return items


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


def reviewable(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: "ExamContent | None" = None,
    ledger: CoverageLedger | None = None,
) -> dict[str, tuple[str, str]]:
    """Every unit, exercise and Exam pattern a student works through, with its title and
    current revision."""
    items = {
        f"study/{unit.key}": (unit.title, revision(unit))
        for unit in (content.units if content else ())
    }
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            items[f"exercises/{group.key}/{exercise.key}"] = (exercise.title, revision(exercise))
    for pattern in exam.patterns if exam else ():
        items[f"exam/pattern/{pattern.key}"] = (pattern.title, revision(pattern))
    if exam and exam.concepts:
        items[SHEET] = ("Cheatsheet", revision(sheet_model(exam, ledger)))
    return items


def review_report(
    state: StudyState,
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    scorecard: ReviewScorecard | None,
    exam: "ExamContent | None" = None,
    lectures: "LectureContent | None" = None,
    *,
    ledger: CoverageLedger | None = None,
    knowledge_revision: str | None = None,
    media_inventory: "MediaInventory | None" = None,
    root: Path | None = None,
    flags: Sequence[dict[str, JsonValue]] = (),
) -> dict[str, JsonValue]:
    """What still needs a review or a fix before the content is easy to learn from."""
    from tum_mcp.study_media import MediaInventory
    from tum_mcp.study_media_report import media_report
    from tum_mcp.study_visuals import visual_ids

    if scorecard and scorecard.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "The review scorecard belongs to another course.")
    media_inventory = media_inventory if media_inventory is not None else MediaInventory()
    media = media_report(root, media_inventory, scorecard.media if scorecard else ())
    current = reviewable(content, exercises, exam, ledger)
    drawn = visual_ids(content, exercises)
    reviews = {review.item: review for review in scorecard.reviews} if scorecard else {}
    unreviewed = [
        {"item": key, "title": title, "revision": value, "visuals": drawn.get(key, [])}
        for key, (title, value) in current.items()
        if key not in reviews
    ]
    stale = [
        {
            "item": key,
            "title": current[key][0],
            "revision": current[key][1],
            "visuals": drawn.get(key, []),
        }
        for key, review in reviews.items()
        if key in current and review.revision != current[key][1]
    ]
    scored = [review for key, review in reviews.items() if key in current]
    unscored = [
        {"item": review.item, "visuals": missing}
        for review in scored
        if review.revision == current[review.item][1]
        and (
            missing := [
                key
                for key in drawn.get(review.item, [])
                if key not in {visual.visual for visual in review.visuals}
            ]
        )
    ]
    below = [
        {
            "item": review.item,
            "scores": {name: score for name, score in review.scores.items() if score < 3},
            "findings": [finding.model_dump(mode="json") for finding in review.findings],
            **(
                {"visuals": low}
                if (
                    low := [
                        visual.model_dump(mode="json")
                        for visual in review.visuals
                        if min(visual.scores.values()) < 3
                    ]
                )
                else {}
            ),
            **({"kept": review.kept} if review.kept else {}),
        }
        for review in scored
        # An empty partial review has no low score; it is listed under unscored_dimensions.
        if min(review.scores.values(), default=3) < 3
    ]
    blocking = [item for item in below if "kept" not in item or 1 in item["scores"].values()]
    fresh = [review for review in scored if review.revision == current[review.item][1]]
    unscored_dimensions = [
        {"item": review.item, "dimensions": missing}
        for review in fresh
        if (missing := [name for name in item_dimensions(review.item) if name not in review.scores])
    ]
    unevidenced = [
        {"item": review.item, "dimensions": missing}
        for review in fresh
        if (
            missing := [
                name
                for name, score in review.scores.items()
                if score == 3 and name not in review.evidence
            ]
        )
    ]
    by_item = {review.item: review for review in fresh}
    conflicts = [
        {"item": key, "flag": flag["flag"], "dimension": dimension, "detail": flag["detail"]}
        for flag in flags
        if (dimension := INVARIANT_FLAGS.get(str(flag["flag"])))
        for key in _flagged_items(str(flag["item"]), content, exercises)
        if key in by_item and by_item[key].scores.get(dimension) == 3
    ]
    # Every accepted finding quotes its passage, and every 3 quotes its closest call, word for
    # word from the item; each item is read by every pass.
    passages = {
        key: item_passages(model.model_dump(mode="json"))
        for key, model in item_models(content, exercises, exam, ledger).items()
        if key in by_item
    }
    unquoted = [
        {"item": item.item, "quotes": missing}
        for item in fresh
        if (
            missing := [
                *(
                    f"{finding.check or finding.dimension}: {finding.quote or '(no quote)'}"
                    for finding in item.findings
                    if finding.status == "accepted"
                    and not (finding.quote and quoted(finding.quote, passages[item.item]))
                ),
                *(
                    f"evidence {name}: {text}"
                    for name, text in item.evidence.items()
                    if item.scores.get(name) == 3 and not quoted(text, passages[item.item])
                ),
            ]
        )
    ]
    missing_passes = [
        {"item": item.item, "passes": missing}
        for item in fresh
        if (missing := [name for name in item_passes(item.item) if name not in item.passes])
    ]
    rubrics = {"": rubric_checks(), SHEET: rubric_checks(SHEET)}
    missing_checks = []
    for item in fresh:
        rubric = rubrics[SHEET if item.item == SHEET else ""]
        calls = item.closest_calls
        failed = {finding.check for finding in item.findings if finding.status == "accepted"}
        required = {check for checks in rubric.values() for check in checks} - failed
        missing = sorted(required - calls.keys())
        invalid = [
            check
            for check, call in calls.items()
            if check not in {check for checks in rubric.values() for check in checks}
            or not quoted(
                call.quote,
                [(path, text) for path, text in passages[item.item] if path == call.location],
            )
        ]
        incomplete = [
            finding.check or finding.dimension
            for finding in item.findings
            if not finding.check
            or finding.check not in rubric.get(finding.dimension, ())
            or not finding.fix
            or not finding.location
            or not finding.quote
            or not quoted(
                finding.quote,
                [(path, text) for path, text in passages[item.item] if path == finding.location],
            )
        ]
        if missing or invalid or incomplete:
            missing_checks.append(
                {"item": item.item, "missing": missing, "invalid": invalid, "findings": incomplete}
            )
    checks_passed = {
        item.item: {
            dimension: f"{len(passed)}/{len(rubric[dimension])}"
            for rubric in [rubrics[SHEET if item.item == SHEET else ""]]
            for dimension in DIMENSIONS
            if dimension in item.scores and dimension in rubric
            for failed in [
                {
                    finding.check
                    for finding in item.findings
                    if finding.status == "accepted"
                    and finding.dimension == dimension
                    and finding.check
                }
            ]
            for passed in [
                {
                    check
                    for check, call in item.closest_calls.items()
                    if check in rubric[dimension]
                    and quoted(
                        call.quote,
                        [
                            (path, text)
                            for path, text in passages[item.item]
                            if path == call.location
                        ],
                    )
                }
                - failed
            ]
        }
        for item in fresh
    }
    # A prompt is fixed (it leaves the report) or kept with a reason; never silently open.
    open_prompts = [
        {"item": key, "flag": flag["flag"], "detail": flag["detail"]}
        for flag in flags
        if str(flag["flag"]) not in INVARIANT_FLAGS
        for key in _flagged_items(str(flag["item"]), content, exercises)
        if key in by_item and str(flag["flag"]) not in {p.flag for p in by_item[key].prompts}
    ]
    review = scorecard.course if scorecard else None
    course, course_blocks = (
        _course_report(
            content,
            exercises,
            exam,
            lectures,
            review,
            ledger=ledger,
            knowledge_revision=knowledge_revision,
            media=media_inventory.structure,
        )
        if current
        else (None, False)
    )
    checks = Counter(
        finding.check
        for finding in (
            *(
                finding
                for item in fresh
                for finding in item.findings
                if finding.status == "accepted"
            ),
            *(review.findings if review and course and course["status"] == "fresh" else ()),
        )
        if finding.check
    )
    return {
        "scorecard": scorecard is not None,
        "passed": not (
            unreviewed
            or stale
            or unscored
            or unscored_dimensions
            or unevidenced
            or conflicts
            or open_prompts
            or unquoted
            or missing_passes
            or missing_checks
            or blocking
            or course_blocks
            or not media["passed"]
        ),
        "unreviewed": unreviewed,
        "stale": stale,
        "unscored_visuals": unscored,
        "unscored_dimensions": unscored_dimensions,
        "unevidenced": unevidenced,
        "flag_conflicts": conflicts,
        "open_prompts": open_prompts,
        "unquoted": unquoted,
        "missing_passes": missing_passes,
        "missing_checks": missing_checks,
        "scores": {item.item: dict(item.scores) for item in fresh},
        "checks_passed": checks_passed,
        "below_bar": below,
        "course": course,
        "media": media,
        "removed": sorted(set(reviews) - set(current)),
        "averages": {
            name: round(sum(values) / len(values), 2)
            for name in DIMENSIONS
            if (values := [item.scores[name] for item in scored if name in item.scores])
        },
        "failed_checks": dict(checks.most_common()),
    }


def _course_report(
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    exam: "ExamContent | None",
    lectures: "LectureContent | None",
    review: CourseReview | None,
    *,
    ledger: CoverageLedger | None = None,
    knowledge_revision: str | None = None,
    media: list[dict[str, JsonValue]] | None = None,
) -> tuple[dict[str, JsonValue], bool]:
    """The course review's state, and whether it still keeps the review from passing."""
    from tum_mcp.study_structure import structure_revision, workspaces

    spaces = workspaces(content, exercises, exam, lectures)
    media_sources = {
        target.split("/", 1)[0] for entry in (media or ()) for target in entry.get("targets", ())
    }
    integrated = (
        len(spaces) > 1
        or ("study" in media_sources and content is not None)
        or ("exercises" in media_sources and exercises is not None)
    )
    dimensions = ["organization", "redundancy", *(["integration"] if integrated else [])]
    current = structure_revision(content, exercises, exam, lectures, ledger=ledger, media=media)
    status = "unreviewed" if review is None else "stale" if review.revision != current else "fresh"
    if review is not None and knowledge_revision is not None:
        if review.knowledge_revision != knowledge_revision:
            status = "stale"
    report: dict[str, JsonValue] = {
        "status": status,
        "revision": current,
        "workspaces": list(spaces),
        "dimensions": list(dimensions),
    }
    if knowledge_revision is not None:
        report["knowledge_revision"] = knowledge_revision
    if review is None or status != "fresh":
        return report, True
    report["scores"] = {name: review.scores[name] for name in dimensions if name in review.scores}
    if missing := [name for name in dimensions if name not in review.scores]:
        report["unscored"] = list(missing)
    low = {name: score for name, score in review.scores.items() if name in dimensions and score < 3}
    if low:
        report["below_bar"] = {
            "scores": dict(low),
            "findings": [finding.model_dump(mode="json") for finding in review.findings],
            **({"kept": review.kept} if review.kept else {}),
        }
    return report, bool(missing or (low and (not review.kept or 1 in low.values())))
