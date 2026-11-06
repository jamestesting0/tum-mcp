"""The coverage ledger: what each course source asks students to learn and what is prepared.

Agents record it while preparing; code checks its references and reports what is missing, so a
whole-course request is judged against the sources' own outcomes, not against unit counts.
"""

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, assert_never

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.course.content.exercises import Exercise, ExerciseContent
from tum_mcp.course.content.study import Label, StudyContent, Text
from tum_mcp.course.project.models import Key, StudyState
from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

if TYPE_CHECKING:
    from tum_mcp.course.content.exam import ExamContent

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


class EnrichmentClassification(Frozen):
    basis: Literal["source_optional", "reviewed_enrichment"]
    reason: Text


class ExploreRef(Frozen):
    unit: Key
    item: Key


Recorded = Literal["gap", "out_of_scope"]
# What a ledger entry shows: prepared when its links resolve, pending when nothing links it,
# else the reason it was recorded with. Code derives it; the agent never types "prepared".
State = Literal["prepared", "pending", "gap", "out_of_scope", "not_inspected", "unavailable"]


class Outcome(Frozen):
    """One learning outcome the source states, and the units that teach and practise it."""

    key: Key
    text: Text
    locator: Locator
    units: tuple[Key, ...] = Field(default=(), max_length=10)
    status: Recorded | None = None
    note: Text | None = None
    role: Literal["core", "enrichment"] = Field(
        default="core", exclude_if=lambda value: value == "core"
    )
    classification: EnrichmentClassification | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    explore: tuple[ExploreRef, ...] = Field(
        default=(), max_length=10, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def taught(self) -> "Outcome":
        match self.role:
            case "core":
                if self.explore or self.classification is not None:
                    raise ValueError(
                        "Core outcomes use unit references, not Explore classification."
                    )
            case "enrichment":
                if self.classification is None or self.units:
                    raise ValueError(
                        "Enrichment needs a classification and no core unit references."
                    )
                if len(set(self.explore)) != len(self.explore):
                    raise ValueError("Explore references must be distinct.")
            case unreachable:
                assert_never(unreachable)
        if self.status is not None and (self.units or self.explore):
            raise ValueError("An outcome that links its teaching is prepared; drop its status.")
        if self.status is not None and not self.note:
            raise ValueError("A gap or out-of-scope outcome says why.")
        return self


class Item(Frozen):
    """One problem part of a sheet or exam, linked to the exercise that prepares it."""

    label: Label
    exercise: Key | None = None
    # The exercise's part this item is, when the exercise has parts; none links them all.
    part: Label | None = None
    status: Literal["not_inspected", "unavailable", "out_of_scope"] | None = None
    role: Literal["core", "bonus"] = Field(default="core", exclude_if=lambda v: v == "core")
    note: Text | None = None

    @model_validator(mode="after")
    def linked(self) -> "Item":
        if self.exercise is not None and self.status is not None:
            raise ValueError("A linked item is prepared; drop its status.")
        if self.part is not None and self.exercise is None:
            raise ValueError("A part belongs to the exercise the item links.")
        if self.status in {"unavailable", "out_of_scope"} and not self.note:
            raise ValueError("An unavailable or out-of-scope item says why.")
        return self


class ExamRequirement(Frozen):
    """One thing the source makes exam-relevant, and the cheatsheet entries that hold it.
    Separate from outcomes: Study teaching something is not the sheet holding it."""

    key: Key
    text: Text
    locator: Locator
    concepts: tuple[Key, ...] = Field(default=(), max_length=10)
    status: Recorded | None = None
    note: Text | None = None

    @model_validator(mode="after")
    def held(self) -> "ExamRequirement":
        if self.status is not None and self.concepts:
            raise ValueError("A requirement that names its entries is prepared; drop its status.")
        if self.status is not None and not self.note:
            raise ValueError("A gap or out-of-scope requirement says why.")
        return self


def outcome_state(outcome: Outcome) -> State:
    if outcome.units or outcome.explore:
        return "prepared"
    return outcome.status or "pending"


def item_state(item: Item) -> State:
    if item.exercise is not None:
        return "prepared"
    return item.status or "pending"


def requirement_state(requirement: ExamRequirement) -> State:
    return "prepared" if requirement.concepts else requirement.status or "pending"


class SourceCoverage(Frozen):
    source: Key
    status: SourceStatus
    outcomes: tuple[Outcome, ...] = Field(default=(), max_length=60)
    items: tuple[Item, ...] = Field(default=(), max_length=100)
    exam: tuple[ExamRequirement, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def enrichment_keys(self) -> "SourceCoverage":
        for outcome in self.outcomes:
            if (
                outcome.role == "enrichment"
                and sum(other.key == outcome.key for other in self.outcomes) != 1
            ):
                raise ValueError("Enrichment outcome keys must be distinct within a source.")
        return self


class CoverageLedger(Frozen):
    schema_version: Literal[2] = 2
    course_key: Key
    sources: tuple[SourceCoverage, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def distinct(self) -> "CoverageLedger":
        if len({item.source for item in self.sources}) != len(self.sources):
            raise ValueError("Record each source once.")
        keys = [item.key for entry in self.sources for item in entry.exam]
        if len(set(keys)) != len(keys):
            raise ValueError("Exam requirement keys must be distinct.")
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
    exam: "ExamContent | None" = None,
) -> None:
    """Links must resolve both ways, so every derived state the app shows is true."""
    entries = {concept.key for concept in exam.concepts} if exam else set()
    for requirement in (item for entry in ledger.sources for item in entry.exam):
        if missing := set(requirement.concepts) - entries:
            raise CampusError(
                Code.INVALID_RESPONSE,
                f"Exam requirement {requirement.key} names entries the cheatsheet does not "
                f"have: {sorted(missing)}.",
            )
    if ledger.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "The coverage ledger belongs to another course.")
    resources = {item.resource.key for item in state.resources}
    units = {unit.key for unit in content.units} if content else set()
    explore = (
        {(unit.key, item.key): item for unit in content.units for item in unit.explore}
        if content
        else {}
    )
    classified: set[tuple[str, str]] = set()
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
            for reference in outcome.explore:
                target = (reference.unit, reference.item)
                material = explore.get(target)
                if material is None or entry.source not in {s.key for s in material.sources}:
                    raise CampusError(
                        Code.INVALID_RESPONSE,
                        f"Enrichment {outcome.key} must reference an existing Explore item "
                        "citing its source.",
                    )
                classified.add(target)
    if missing := set(explore) - classified:
        raise CampusError(
            Code.INVALID_RESPONSE,
            f"Explore items need an enrichment outcome that links them: {sorted(missing)}.",
        )
    _check_items(ledger, exercises)


def _numbers(exercise: "Exercise") -> set[str]:
    """The labels a sheet would give this problem: "Problem 2.5" is 2.5, plus its parts."""
    tail = exercise.label.split()[-1] if exercise.label.split() else exercise.label
    return {tail, *exercise.parts}


def _check_items(ledger: CoverageLedger, exercises: ExerciseContent | None) -> None:
    """Every prepared problem part is recorded exactly once, and no record hides one."""
    originals = {
        exercise.key: exercise
        for group in (exercises.sets if exercises else ())
        for exercise in group.exercises
        if exercise.kind == "original"
    }
    sheets = {group.sheet: group for group in (exercises.sets if exercises else ()) if group.sheet}
    covered: dict[str, list[str | None]] = {}
    for entry in ledger.sources:
        for item in entry.items:
            if item.exercise is None:
                group = sheets.get(entry.source)
                match = next(
                    (
                        exercise
                        for exercise in (group.exercises if group else ())
                        if exercise.kind == "original" and item.label in _numbers(exercise)
                    ),
                    None,
                )
                if match is not None:
                    raise CampusError(
                        Code.INVALID_RESPONSE,
                        f"Item {item.label} is prepared as {match.key}; link it with "
                        f'"exercise": "{match.key}" instead of recording it as {item_state(item)}.',
                    )
                continue
            exercise = originals.get(item.exercise)
            if exercise is None:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Item {item.label} names exercise {item.exercise}, which is not prepared.",
                )
            if item.part is not None and item.part not in exercise.parts:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"Item {item.label} names part {item.part}, which {exercise.key} lacks.",
                )
            covered.setdefault(exercise.key, []).append(item.part)
    for key, parts in covered.items():
        named = [part for part in parts if part is not None]
        if (None in parts and len(parts) > 1) or len(set(named)) != len(named):
            raise CampusError(
                Code.INVALID_RESPONSE, f"Exercise {key} is recorded more than once in the ledger."
            )
    for group in sheets.values():
        recorded = any(entry.source == group.sheet and entry.items for entry in ledger.sources)
        for exercise in group.exercises:
            if not recorded or exercise.kind != "original":
                continue
            parts = covered.get(exercise.key)
            if parts is None:
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"{exercise.key} is prepared but no ledger item for {group.sheet} links it.",
                )
            if None not in parts and set(parts) != set(exercise.parts):
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    f"{exercise.key} has parts no ledger item records: "
                    f"{sorted(set(exercise.parts) - set(parts))}.",
                )


def pending_exercises(
    ledger: CoverageLedger | None, state: StudyState, exercises: ExerciseContent | None
) -> list[JsonValue]:
    """Core problems not prepared yet, under the set whose sheet they come from."""
    if ledger is None:
        return []
    titles = {item.resource.key: item.resource.title for item in state.resources}
    owner = {
        group.sheet: group.key for group in (exercises.sets if exercises else ()) if group.sheet
    }
    result: list[JsonValue] = []
    for entry in ledger.sources:
        labels = [
            item.label
            for item in entry.items
            if item.role == "core" and item_state(item) in {"pending", "not_inspected"}
        ]
        if labels:
            result.append(
                {
                    "set": owner.get(entry.source),
                    "source": titles[entry.source],
                    "labels": labels,
                    **({"provisional": True} if entry.status.availability == "provisional" else {}),
                }
            )
    return result


def study_preparation(state: StudyState, ledger: CoverageLedger | None) -> dict[str, JsonValue]:
    """Authoring preparation states; the learner app projects only known core gaps."""
    recorded = {entry.source: entry for entry in ledger.sources} if ledger else {}
    pending: list[JsonValue] = []
    enrichment: list[JsonValue] = []
    unrecorded: list[JsonValue] = []
    for resource in state.resources:
        if resource.status != "current" or resource.resource.kind != "content":
            continue
        key, title = resource.resource.key, resource.resource.title
        entry = recorded.get(key)
        if entry is None or (not entry.outcomes and not entry.items):
            unrecorded.append({"source": key, "title": title})
            continue
        for role, target in (("core", pending), ("enrichment", enrichment)):
            outcomes: list[JsonValue] = [
                {
                    "key": outcome.key,
                    "text": outcome.text,
                    "status": outcome_state(outcome),
                    "locator": outcome.locator,
                }
                for outcome in entry.outcomes
                if outcome.role == role and outcome_state(outcome) in {"pending", "gap"}
            ]
            if outcomes:
                target.append({"source": key, "title": title, "outcomes": outcomes})
    result = {"pending": pending, "unrecorded": unrecorded}
    if enrichment:
        result["enrichmentPending"] = enrichment
    return result


def unrecorded_sources(state: StudyState, ledger: CoverageLedger | None) -> list[str]:
    """Current content sources with no exam requirement: unread for the cheatsheet."""
    recorded = {entry.source for entry in ledger.sources if entry.exam} if ledger else set()
    return sorted(
        item.resource.key
        for item in state.resources
        if item.status == "current"
        and item.resource.kind == "content"
        and item.resource.key not in recorded
    )


def sheet_flags(
    state: StudyState, ledger: CoverageLedger | None, exam: "ExamContent | None"
) -> list[dict[str, JsonValue]]:
    """A cheatsheet review cannot pass coverage while a source was never read for it."""
    if not (exam and exam.concepts) or not (missing := unrecorded_sources(state, ledger)):
        return []
    return [
        {
            "item": "exam/sheet",
            "flag": "unrecorded_sources",
            "detail": f"{len(missing)} current content source(s) have no exam requirement, such "
            f"as {', '.join(missing[:5])}. Read each and record its requirements, or one "
            "out_of_scope requirement saying why it is outside the sheet.",
        }
    ]


def coverage_report(
    state: StudyState,
    content: StudyContent | None,
    exercises: ExerciseContent | None,
    ledger: CoverageLedger | None,
    exam: "ExamContent | None" = None,
) -> dict[str, JsonValue]:
    """What is not yet inspected, taught or prepared, so completion is judged against sources."""
    recorded = {entry.source: entry for entry in ledger.sources} if ledger else {}
    cheatsheet: dict[str, JsonValue] | None = None
    if exam and exam.concepts:
        requirements = [(entry.source, item) for entry in recorded.values() for item in entry.exam]
        cheatsheet = {
            # The sheet is judged against what the sources make exam-relevant, never against
            # its own entry list; unread sources stay unknown.
            "requirements": len(requirements),
            "gaps": [
                {
                    "source": source,
                    "requirement": item.key,
                    "text": item.text,
                    "status": requirement_state(item),
                    "locator": item.locator,
                    **({"note": item.note} if item.note else {}),
                }
                for source, item in requirements
                if requirement_state(item) in {"gap", "pending"}
            ],
            "sources_without_requirements": unrecorded_sources(state, ledger),
            "entries_without_requirement": sorted(
                {concept.key for concept in exam.concepts}
                - {key for _, item in requirements for key in item.concepts}
            ),
        }
    current = [item for item in state.resources if item.status == "current"]
    taught = {unit.key for unit in content.units} if content else set()
    uninspected = [
        {"source": item.resource.key, "title": item.resource.title, "kind": item.resource.kind}
        for item in current
        if item.resource.kind in {"content", "exercise"} and item.resource.key not in recorded
    ]
    gaps = [
        {
            "source": entry.source,
            "outcome": outcome.key,
            "text": outcome.text,
            "status": outcome_state(outcome),
            "locator": outcome.locator,
            **({"note": outcome.note} if outcome.note else {}),
            "role": outcome.role,
        }
        for entry in recorded.values()
        for outcome in entry.outcomes
        if outcome_state(outcome) in {"gap", "pending"}
    ]
    outcomes = [
        {k: v for k, v in gap.items() if k != "role"} for gap in gaps if gap["role"] == "core"
    ]
    enrichment = [
        {k: v for k, v in gap.items() if k != "role"} for gap in gaps if gap["role"] == "enrichment"
    ]
    sources_without_outcomes = [
        key
        for key, entry in recorded.items()
        if not entry.outcomes
        and not entry.items
        and any(item.resource.key == key and item.resource.kind == "content" for item in current)
    ]
    items = [
        {"source": entry.source, "label": item.label, "status": item_state(item)}
        for entry in recorded.values()
        for item in entry.items
        if item.role == "core" and item_state(item) in {"pending", "not_inspected", "unavailable"}
    ]
    bonus = [
        {"source": entry.source, "label": item.label}
        for entry in recorded.values()
        for item in entry.items
        if item.role == "bonus" and item_state(item) != "prepared"
    ]
    other_semester = [
        {"source": key, "semester": entry.status.semester}
        for key, entry in recorded.items()
        if entry.status.semester and entry.status.semester != state.course.semester
    ]
    unlinked_units = sorted(
        taught - {key for e in recorded.values() for o in e.outcomes for key in o.units}
    )
    core_complete = not (uninspected or outcomes or sources_without_outcomes or items)
    return {
        "ledger": ledger is not None,
        "study_preparation": study_preparation(state, ledger),
        "complete": core_complete and not enrichment,
        "core_complete": core_complete,
        "not_inspected": uninspected,
        "outcome_gaps": outcomes,
        "enrichment_gaps": enrichment,
        "sources_without_outcomes": sources_without_outcomes,
        "unprepared_items": items,
        "skipped_bonus": bonus,
        "other_semester": other_semester,
        "units_without_outcomes": unlinked_units,
        "status_unknown": sorted(
            key for key, entry in recorded.items() if entry.status.availability == "unknown"
        ),
        **({"cheatsheet": cheatsheet} if cheatsheet is not None else {}),
    }
