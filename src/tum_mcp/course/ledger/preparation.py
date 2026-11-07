"""The source-backed scope of one Study and Exercises preparation request."""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from tum_mcp.course.content.study import Label, Text
from tum_mcp.course.ledger.coverage import CoverageLedger, Locator
from tum_mcp.course.project.models import Digest, Key, StudyState
from tum_mcp.course.project.schedule import Schedule
from tum_mcp.course.project.store import digest, private_path, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


class Candidate(Frozen):
    source: Key
    sha256: Digest | None = None
    disposition: Literal["required", "later", "optional", "logistics", "unresolved", "excluded"]
    basis: Literal["schedule", "release", "corroborated", "source", "unknown"]
    on: date | None = None
    reason: Text
    locator: Locator
    # A source may state semester objectives that are taught later in different lectures.
    deferred_outcomes: dict[Key, Text] = Field(default_factory=dict)
    deferred_items: dict[Label, Text] = Field(
        default_factory=dict,
        exclude_if=lambda items: not items,
        description="Original sheet entry labels excluded from this selected scope, with reasons.",
    )


class StudyTarget(Frozen):
    unit: Key
    blocks: tuple[Key, ...] = Field(min_length=1, max_length=40)
    objective: Key
    question: Key
    reason: Text


class ExerciseTarget(Frozen):
    set: Key
    exercise: Key
    part: Label | None = None
    statement: Key
    step: Key
    # Stable keys are preferred. Legacy solution blocks may only have a position.
    answer_block: Key | Annotated[int, Field(ge=0)]


class Demand(Frozen):
    id: Key
    source: Key
    text: Text
    locator: Locator
    values: tuple[Text, ...] = ()
    walkthroughs: tuple[Key, ...] = ()


class StudyDemand(Demand):
    kind: Literal["study"]
    outcome: Key
    level: Literal["recall", "apply", "reason"]
    target: StudyTarget | None = None


class ExerciseDemand(Demand):
    kind: Literal["exercises"]
    label: Label
    part: Label | None = Field(
        default=None,
        description="Original part label, even when this scope selects only that part.",
    )
    target: ExerciseTarget | None = None


Requirement = Annotated[StudyDemand | ExerciseDemand, Field(discriminator="kind")]
Workspace = Literal["study", "exercises"]


class Preparation(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    semester: Label
    workspaces: tuple[Workspace, ...] = Field(min_length=1, max_length=2)
    mode: Literal["through_date", "selected_sources"]
    cutoff: date | None = None
    inventory: tuple[Candidate, ...] = Field(max_length=10000)
    demands: tuple[Requirement, ...] = Field(max_length=10000)
    # A partial provider may be immaterial, for example a discussion-only binding.
    provider_limits: dict[Key, Text] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self) -> "Preparation":
        if (self.mode == "through_date") != (self.cutoff is not None):
            raise ValueError("Only a through-date preparation has a cutoff.")
        sources = {candidate.source for candidate in self.inventory}
        demands = {(demand.source, demand.id) for demand in self.demands}
        if len(sources) != len(self.inventory) or len(demands) != len(self.demands):
            raise ValueError("Use each source and source-qualified demand only once.")
        if len(set(self.workspaces)) != len(self.workspaces):
            raise ValueError("Name each workspace once.")
        return self

    def fingerprint(self) -> str:
        """Keep the requested requirements fixed while their draft mappings can change."""
        return digest(self.model_dump_json(exclude={"demands": {"__all__": {"target"}}}).encode())


def read_preparation(root: Path, identifier: str) -> Preparation | None:
    try:
        key = TypeAdapter(Key).validate_python(identifier)
        body = read_bytes(private_path(root, f"preparation/{key}.json"))
        return Preparation.model_validate_json(body) if body is not None else None
    except ValidationError as error:
        problem = error.errors(include_input=False)[0]
        location = ".".join(str(part) for part in problem["loc"])
        raise CampusError(
            Code.INVALID_RESPONSE, f"Invalid preparation scope {location}: {problem['msg']}"
        ) from None


def scope_problems(
    scope: Preparation, state: StudyState, ledger: CoverageLedger | None, schedule: Schedule | None
) -> list[str]:
    """Check the frozen inventory and demands before looking at the authored draft."""
    if (scope.course_key, scope.semester) != (state.course.key, state.course.semester):
        raise CampusError(Code.SCOPE_DENIED, "The preparation belongs to another course or term.")
    kinds = {"study": "content", "exercises": "exercise"}
    expected = {kinds[workspace] for workspace in scope.workspaces}
    resources = {
        item.resource.key: item
        for item in state.resources
        if item.resource.kind in expected and item.status != "withdrawn"
    }
    candidates = {entry.source: entry for entry in scope.inventory}
    recorded = {entry.source: entry for entry in ledger.sources} if ledger else {}
    demands_by_source: dict[str, list[Requirement]] = {}
    for demand in scope.demands:
        demands_by_source.setdefault(demand.source, []).append(demand)
    required = {entry.source for entry in scope.inventory if entry.disposition == "required"}
    problems: list[str] = []
    if not required or not scope.demands:
        problems.append("Record at least one required source and demand.")
    if scope.cutoff:
        problems.extend(
            f"{key}: missing inventory disposition." for key in resources.keys() - candidates.keys()
        )
        problems.extend(
            f"{entry.binding}: provider inventory is {entry.status}; reconcile its scope."
            for entry in state.coverage
            if entry.status != "complete" and entry.binding not in scope.provider_limits
        )
    schedule_dates: dict[str, dict[str, date]] = {}
    if schedule and scope.cutoff:
        for session in sorted(schedule.sessions, key=lambda entry: entry.on):
            basis = "release" if session.basis == "release" else "schedule"
            for key in session.sources:
                schedule_dates.setdefault(key, {}).setdefault(basis, session.on)
    for key in demands_by_source.keys() - required:
        problems.append(f"{key}: demands belong to a required source.")
    for entry in scope.inventory:
        key = entry.source
        resource = resources.get(key)
        if resource is None:
            problems.append(
                f"{key}: source is absent, withdrawn or outside the requested workspace."
            )
            continue
        if resource.sha256 != entry.sha256:
            problems.append(f"{key}: source revision changed since the scope was recorded.")
        if scope.cutoff:
            if entry.disposition == "unresolved" or entry.disposition == "excluded":
                problems.append(f"{key}: unresolved for the requested cutoff.")
            if entry.disposition in {"required", "later"} and (
                entry.basis not in {"schedule", "release", "corroborated"}
                or entry.on is None
                or (entry.on <= scope.cutoff) != (entry.disposition == "required")
            ):
                problems.append(f"{key}: dated evidence does not support its cutoff disposition.")
        if scope.cutoff and entry.disposition in {"required", "later"}:
            dates = schedule_dates.get(key, {})
            basis = "schedule" if "schedule" in dates else entry.basis
            if basis in {"schedule", "release"} and (
                basis != entry.basis or dates.get(basis) != entry.on or entry.on is None
            ):
                problems.append(f"{key}: dated evidence does not match the recorded schedule.")
        if key not in required:
            continue
        if resource.status != "current":
            problems.append(f"{key}: required source is not available locally.")
        source = recorded.get(key)
        demands = demands_by_source.get(key, [])
        if source is None or not demands:
            problems.append(f"{key}: record its ledger entry and required demands.")
            continue
        if source.status.availability in {"provisional", "unavailable", "announced"}:
            problems.append(
                f"{key}: ledger marks the required source {source.status.availability}."
            )
        if resource.resource.kind == "content":
            if entry.deferred_items:
                problems.append(f"{key}: only an exercise sheet can defer sheet entries.")
            outcomes = {outcome.key for outcome in source.outcomes if outcome.role == "core"}
            mapped = {demand.outcome for demand in demands if isinstance(demand, StudyDemand)}
            deferred = set(entry.deferred_outcomes)
            if missing := outcomes - mapped - deferred:
                problems.append(f"{key}: missing required outcomes {', '.join(sorted(missing))}.")
            if len([d for d in demands if isinstance(d, StudyDemand)]) != len(demands) or (
                mapped & deferred or (mapped | deferred) - outcomes
            ):
                problems.append(
                    f"{key}: invalid outcome mapping. "
                    f"Unknown IDs: {', '.join(sorted((mapped | deferred) - outcomes)) or 'none'}; "
                    "both required and deferred: "
                    f"{', '.join(sorted(mapped & deferred)) or 'none'}. "
                    f"Use Study demands with core outcome IDs: {', '.join(sorted(outcomes))}."
                )
        else:
            items = {
                item.label
                for item in source.items
                if item.role == "core" and item.status != "out_of_scope"
            }
            mapped_items = {
                demand.label for demand in demands if isinstance(demand, ExerciseDemand)
            }
            deferred = set(entry.deferred_items)
            if deferred and scope.cutoff:
                problems.append(f"{key}: a through-date scope cannot defer required sheet entries.")
                deferred = set()
            if deferred & mapped_items or deferred - items:
                problems.append(f"{key}: exclusions must name unselected core sheet entries.")
            if missing := items - mapped_items - deferred:
                problems.append(
                    f"{key}: missing required sheet entries {', '.join(sorted(missing))}."
                )
            if any(not isinstance(d, ExerciseDemand) for d in demands) or mapped_items - items:
                problems.append(
                    f"{key}: demand does not resolve to an original entry of this sheet."
                )
    return sorted(problems)
