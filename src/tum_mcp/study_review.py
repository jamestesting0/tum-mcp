"""The review scorecard: how a separate reading scored each Study unit, exercise and the course.

Scores are judgement, so the reviewing agent writes them. Code ties each review to the exact
content it read, so a changed unit or exercise needs a fresh review, and the course review
follows the course's structure. The report lists what is unreviewed, stale or below the bar.
"""

import datetime
import hashlib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, JsonValue, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.settings import Frozen
from tum_mcp.study_content import StudyContent, Text
from tum_mcp.study_coverage import CoverageLedger
from tum_mcp.study_models import Key, StudyState
from tum_mcp.study_store import private_path

if TYPE_CHECKING:
    from tum_mcp.exam_content import ExamContent
    from tum_mcp.lecture_content import LectureContent

Dimension = Literal[
    "correctness",
    "clarity",
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
    "cognitive_load",
    "representation",
    "practice",
    "coverage",
    "intuition",
    "organization",
    "redundancy",
)
CourseDimension = Literal["organization", "redundancy", "integration"]
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
ItemKey = Annotated[str, Field(pattern=r"^(study/[a-z0-9-]+|exercises/[a-z0-9-]+/[a-z0-9-]+)$")]
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
    """What a student meets that costs a point, named precisely enough to fix."""

    dimension: Dimension
    check: Check | None = None
    note: Text

    @model_validator(mode="after")
    def checked(self) -> "Finding":
        _own_check(self.dimension, self.check)
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


class ItemReview(Frozen):
    item: ItemKey
    revision: Revision
    reviewed_at: datetime.date
    scores: dict[Dimension, Score]
    findings: tuple[Finding, ...] = Field(default=(), max_length=30)
    visuals: tuple[VisualReview, ...] = Field(default=(), max_length=80)
    kept: Text | None = None

    @model_validator(mode="after")
    def explained(self) -> "ItemReview":
        # A review saved before a dimension existed still loads; the report lists what it lacks.
        _found(self.scores, self.findings)
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
    # Integration is scored only when the report lists two or more workspaces.
    scores: dict[CourseDimension, Score]
    findings: tuple[CourseFinding, ...] = Field(default=(), max_length=40)
    kept: Text | None = None

    @model_validator(mode="after")
    def explained(self) -> "CourseReview":
        _found(self.scores, self.findings)
        return self


def _found(scores: dict[str, int], findings: tuple[Finding | CourseFinding, ...]) -> None:
    found = {finding.dimension for finding in findings}
    if missing := [name for name, score in scores.items() if score < 3 and name not in found]:
        raise ValueError("A score below 3 names its finding: " + ", ".join(missing) + ".")


class ReviewScorecard(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    reviews: tuple[ItemReview, ...] = Field(max_length=1000)
    course: CourseReview | None = None

    @model_validator(mode="after")
    def distinct(self) -> "ReviewScorecard":
        if len({review.item for review in self.reviews}) != len(self.reviews):
            raise ValueError("Review each item once.")
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


def revision(item: BaseModel) -> str:
    return hashlib.sha256(item.model_dump_json().encode()).hexdigest()[:16]


def reviewable(
    content: StudyContent | None, exercises: ExerciseContent | None
) -> dict[str, tuple[str, str]]:
    """Every unit and exercise a student works through, with its title and current revision."""
    items = {
        f"study/{unit.key}": (unit.title, revision(unit))
        for unit in (content.units if content else ())
    }
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            items[f"exercises/{group.key}/{exercise.key}"] = (exercise.title, revision(exercise))
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
) -> dict[str, JsonValue]:
    """What still needs a review or a fix before the content is easy to learn from."""
    from tum_mcp.study_visuals import visual_ids

    if scorecard and scorecard.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "The review scorecard belongs to another course.")
    current = reviewable(content, exercises)
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
        if min(review.scores.values()) < 3
    ]
    blocking = [item for item in below if "kept" not in item or 1 in item["scores"].values()]
    fresh = [review for review in scored if review.revision == current[review.item][1]]
    unscored_dimensions = [
        {"item": review.item, "dimensions": missing}
        for review in fresh
        if (missing := [name for name in DIMENSIONS if name not in review.scores])
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
        )
        if current
        else (None, False)
    )
    checks = Counter(
        finding.check
        for finding in (
            *(finding for item in fresh for finding in item.findings),
            *(review.findings if review and course and course["status"] == "fresh" else ()),
        )
        if finding.check
    )
    return {
        "scorecard": scorecard is not None,
        "passed": not (
            unreviewed or stale or unscored or unscored_dimensions or blocking or course_blocks
        ),
        "unreviewed": unreviewed,
        "stale": stale,
        "unscored_visuals": unscored,
        "unscored_dimensions": unscored_dimensions,
        "below_bar": below,
        "course": course,
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
) -> tuple[dict[str, JsonValue], bool]:
    """The course review's state, and whether it still keeps the review from passing."""
    from tum_mcp.study_structure import structure_revision, workspaces

    spaces = workspaces(content, exercises, exam, lectures)
    dimensions = ["organization", "redundancy", *(["integration"] if len(spaces) > 1 else [])]
    current = structure_revision(content, exercises, exam, lectures, ledger=ledger)
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
