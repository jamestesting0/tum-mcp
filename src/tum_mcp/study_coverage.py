"""The coverage ledger: what each course source asks students to learn and what is prepared.

Agents record it while preparing; code checks its references and reports what is missing, so a
whole-course request is judged against the sources' own outcomes, not against unit counts.
"""

import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.settings import Frozen
from tum_mcp.study_content import Label, StudyContent, Text
from tum_mcp.study_models import Key, StudyState
from tum_mcp.study_store import private_path

Locator = Annotated[str, Field(min_length=1, max_length=200)]


class SourceStatus(Frozen):
    """What the evidence says about a source; unknown stays unknown, never inferred."""

    availability: Literal["released", "announced", "provisional", "unavailable", "unknown"] = (
        "unknown"
    )
    taught: Literal["yes", "no", "unknown"] = "unknown"
    semester: Label | None = None
    evidence: Text | None = None
    checked_at: datetime.date


class Outcome(Frozen):
    """One learning outcome the source states, and where Study teaches and practises it."""

    key: Key
    text: Text
    locator: Locator
    status: Literal["covered", "partial", "gap", "out_of_scope"]
    units: tuple[Key, ...] = Field(default=(), max_length=10)
    note: Text | None = None

    @model_validator(mode="after")
    def taught(self) -> "Outcome":
        if self.status in {"covered", "partial"} and not self.units:
            raise ValueError("A covered or partial outcome names the units that teach it.")
        if self.status in {"gap", "out_of_scope"} and not self.note:
            raise ValueError("A gap or out-of-scope outcome says why.")
        return self


class Item(Frozen):
    """One problem of an exercise sheet or exam, and whether it is prepared."""

    label: Label
    status: Literal["prepared", "pending", "not_inspected", "unavailable", "out_of_scope"]
    exercise: Key | None = None
    note: Text | None = None

    @model_validator(mode="after")
    def prepared(self) -> "Item":
        if (self.status == "prepared") != (self.exercise is not None):
            raise ValueError("A prepared item names its exercise; other items name none.")
        return self


class SourceCoverage(Frozen):
    source: Key
    status: SourceStatus
    outcomes: tuple[Outcome, ...] = Field(default=(), max_length=60)
    items: tuple[Item, ...] = Field(default=(), max_length=100)


class CoverageLedger(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    sources: tuple[SourceCoverage, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def distinct(self) -> "CoverageLedger":
        if len({item.source for item in self.sources}) != len(self.sources):
            raise ValueError("Record each source once.")
        return self


def ledger_path(root: Path) -> Path:
    return private_path(root, "coverage.json")


def read_ledger(root: Path) -> CoverageLedger | None:
    path = ledger_path(root)
    if not path.exists():
        return None
    try:
        return CoverageLedger.model_validate_json(path.read_bytes())
    except ValidationError as error:
        locations = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)]
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Invalid coverage ledger at: " + ", ".join(locations[:5]) + ". See study schema "
            "coverage.",
        ) from None


def check_ledger(
    ledger: CoverageLedger,
    state: StudyState,
    content: StudyContent | None,
    exercises: ExerciseContent | None,
) -> None:
    """References must resolve, so the report can trust what the ledger says is prepared."""
    if ledger.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "The coverage ledger belongs to another course.")
    resources = {item.resource.key for item in state.resources}
    units = {unit.key for unit in content.units} if content else set()
    prepared = {e.key for group in exercises.sets for e in group.exercises} if exercises else set()
    for entry in ledger.sources:
        if entry.source not in resources:
            raise CampusError(
                Code.INVALID_RESPONSE, f"The coverage ledger names unknown source {entry.source}."
            )
        for outcome in entry.outcomes:
            if missing := set(outcome.units) - units:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Outcome {outcome.key} names units Study does not have: {sorted(missing)}.",
                )
        for item in entry.items:
            if item.exercise and item.exercise not in prepared:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Item {item.label} names exercise {item.exercise}, which is not prepared.",
                )


def pending_exercises(
    ledger: CoverageLedger | None, state: StudyState, exercises: ExerciseContent | None
) -> list[JsonValue]:
    """Unprepared problems for learners: under the set that uses their sheet, else on their own."""
    if ledger is None:
        return []
    titles = {item.resource.key: item.resource.title for item in state.resources}
    owner = {
        source.key: group.key
        for group in (exercises.sets if exercises else ())
        for exercise in group.exercises
        for source in exercise.sources
    }
    result: list[JsonValue] = []
    for entry in ledger.sources:
        labels = [item.label for item in entry.items if item.status in {"pending", "not_inspected"}]
        if labels:
            result.append(
                {"set": owner.get(entry.source), "source": titles[entry.source], "labels": labels}
            )
    return result


def coverage_report(
    state: StudyState,
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    ledger: CoverageLedger | None,
) -> dict[str, JsonValue]:
    """What is not yet inspected, taught or prepared, so completion is judged against sources."""
    recorded = {entry.source: entry for entry in ledger.sources} if ledger else {}
    current = [item for item in state.resources if item.status == "current"]
    taught = {unit.key for unit in content.units} if content else set()
    uninspected = [
        {"source": item.resource.key, "title": item.resource.title, "kind": item.resource.kind}
        for item in current
        if item.resource.kind in {"content", "exercise"} and item.resource.key not in recorded
    ]
    outcomes = [
        {
            "source": entry.source,
            "outcome": outcome.key,
            "text": outcome.text,
            "status": outcome.status,
            "locator": outcome.locator,
            **({"note": outcome.note} if outcome.note else {}),
        }
        for entry in recorded.values()
        for outcome in entry.outcomes
        if outcome.status in {"gap", "partial"}
    ]
    sources_without_outcomes = [
        key
        for key, entry in recorded.items()
        if not entry.outcomes
        and not entry.items
        and any(item.resource.key == key and item.resource.kind == "content" for item in current)
    ]
    items = [
        {"source": entry.source, "label": item.label, "status": item.status}
        for entry in recorded.values()
        for item in entry.items
        if item.status in {"pending", "not_inspected", "unavailable"}
    ]
    other_semester = [
        {"source": key, "semester": entry.status.semester}
        for key, entry in recorded.items()
        if entry.status.semester and entry.status.semester != state.course.semester
    ]
    unlinked_units = sorted(
        taught - {key for e in recorded.values() for o in e.outcomes for key in o.units}
    )
    complete = not (uninspected or outcomes or sources_without_outcomes or items)
    return {
        "ledger": ledger is not None,
        "complete": complete,
        "not_inspected": uninspected,
        "outcome_gaps": outcomes,
        "sources_without_outcomes": sources_without_outcomes,
        "unprepared_items": items,
        "other_semester": other_semester,
        "units_without_outcomes": unlinked_units,
        "status_unknown": sorted(
            key for key, entry in recorded.items() if entry.status.availability == "unknown"
        ),
    }
