"""The review scorecard: how a separate reading scored each Study unit and exercise.

Scores are judgement, so the reviewing agent writes them. Code ties each review to the exact
content it read, so a changed unit or exercise needs a fresh review, and the report lists
what is unreviewed, stale or below the bar.
"""

import datetime
import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, JsonValue, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.settings import Frozen
from tum_mcp.study_content import StudyContent, Text
from tum_mcp.study_models import Key, StudyState
from tum_mcp.study_store import private_path

Dimension = Literal[
    "correctness", "clarity", "cognitive_load", "representation", "practice", "coverage"
]
DIMENSIONS: tuple[Dimension, ...] = (
    "correctness",
    "clarity",
    "cognitive_load",
    "representation",
    "practice",
    "coverage",
)
# 1 blocks learning, 2 works with friction, 3 easy to learn from.
Score = Literal[1, 2, 3]
ItemKey = Annotated[str, Field(pattern=r"^(study/[a-z0-9-]+|exercises/[a-z0-9-]+/[a-z0-9-]+)$")]
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


class Finding(Frozen):
    """What a student meets that costs a point, named precisely enough to fix."""

    dimension: Dimension
    note: Text


class ItemReview(Frozen):
    item: ItemKey
    revision: Revision
    reviewed_at: datetime.date
    scores: dict[Dimension, Score]
    findings: tuple[Finding, ...] = Field(default=(), max_length=30)
    kept: Text | None = None

    @model_validator(mode="after")
    def explained(self) -> "ItemReview":
        if set(self.scores) != set(DIMENSIONS):
            raise ValueError("Score every dimension: " + ", ".join(DIMENSIONS) + ".")
        found = {finding.dimension for finding in self.findings}
        if missing := [
            name for name, score in self.scores.items() if score < 3 and name not in found
        ]:
            raise ValueError("A score below 3 names its finding: " + ", ".join(missing) + ".")
        return self


class ReviewScorecard(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    reviews: tuple[ItemReview, ...] = Field(max_length=1000)

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
) -> dict[str, JsonValue]:
    """What still needs a review or a fix before the content is easy to learn from."""
    if scorecard and scorecard.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "The review scorecard belongs to another course.")
    current = reviewable(content, exercises)
    reviews = {review.item: review for review in scorecard.reviews} if scorecard else {}
    unreviewed = [
        {"item": key, "title": title, "revision": value}
        for key, (title, value) in current.items()
        if key not in reviews
    ]
    stale = [
        {"item": key, "title": current[key][0], "revision": current[key][1]}
        for key, review in reviews.items()
        if key in current and review.revision != current[key][1]
    ]
    scored = [review for key, review in reviews.items() if key in current]
    below = [
        {
            "item": review.item,
            "scores": {name: score for name, score in review.scores.items() if score < 3},
            "findings": [finding.model_dump(mode="json") for finding in review.findings],
            **({"kept": review.kept} if review.kept else {}),
        }
        for review in scored
        if min(review.scores.values()) < 3
    ]
    blocking = [item for item in below if "kept" not in item or 1 in item["scores"].values()]
    return {
        "scorecard": scorecard is not None,
        "passed": not (unreviewed or stale or blocking),
        "unreviewed": unreviewed,
        "stale": stale,
        "below_bar": below,
        "removed": sorted(set(reviews) - set(current)),
        "averages": {
            name: round(sum(review.scores[name] for review in scored) / len(scored), 2)
            for name in DIMENSIONS
        }
        if scored
        else {},
    }
