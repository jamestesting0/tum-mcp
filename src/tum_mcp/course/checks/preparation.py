"""Preflight for prepared review. The author's mapping is evidence for a fresh reader."""

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, JsonValue

from tum_mcp.course.app.browser_evidence import browser_choice, browser_identity, read_receipt
from tum_mcp.course.app.build import current_data, read_content, stale_units
from tum_mcp.course.app.visuals import WIDTHS, interaction_routes, shell_workspace
from tum_mcp.course.checks.plans import (
    coverage_reader,
    gate_status,
    plan_problems,
    read_plan,
)
from tum_mcp.course.content.exercise_data import read_exercises, stale_exercises
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.store import present
from tum_mcp.course.content.study import StudyContent
from tum_mcp.course.ledger.coverage import CoverageLedger, read_ledger
from tum_mcp.course.ledger.preparation import (
    ExerciseDemand,
    Preparation,
    StudyDemand,
    read_preparation,
    scope_problems,
    scope_summary,
)
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.course.project.schedule import read_schedule
from tum_mcp.course.project.store import confined, load_state, read_bytes
from tum_mcp.course.review.items import digest
from tum_mcp.course.review.models import INVARIANT_FLAGS
from tum_mcp.settings import Frozen

if TYPE_CHECKING:
    from tum_mcp.course.review.loop import Context


class PreparedScope(Frozen):
    identifier: Key
    fingerprint: Digest


class Readiness(Frozen):
    identifier: str
    scope: PreparedScope | None = None
    mode: Literal["through_date", "selected_sources"] | None = None
    cutoff: str | None = None
    request: dict[str, JsonValue] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    problems: tuple[str, ...] = ()
    dispositions: tuple[dict[str, JsonValue], ...] = ()
    items: dict[str, list[dict[str, JsonValue]]] = Field(default_factory=dict)
    fingerprints: dict[str, str] = Field(default_factory=dict)
    provisional_plans: tuple[str, ...] = ()
    provisional_sources: tuple[Key, ...] = ()
    unresolved_sources: tuple[Key, ...] = ()
    partial_providers: tuple[Key, ...] = ()
    cutoff_verified: bool | None = None
    walkthrough_evidence: Literal["source_mapped"] | None = None
    preparations: tuple[dict[str, JsonValue], ...] = ()

    @property
    def ready(self) -> bool:
        return bool(self.items) and not self.problems

    def report(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"fingerprints"}) | {
            "ready": self.ready,
            "next_action": (
                "The checks passed; continue to the requested next stage."
                if self.ready
                else "Continue authoring and repairing the first unresolved requirement: "
                + (self.problems[0] if self.problems else "No requested items are mapped yet.")
            ),
        }


def _study_problem(
    demand: StudyDemand, content: StudyContent | None, ledger: CoverageLedger
) -> str | None:
    target = demand.target
    if not target or not content:
        return "missing Study teaching and practice mapping."
    unit = next((unit for unit in content.units if unit.key == target.unit), None)
    source = next((entry for entry in ledger.sources if entry.source == demand.source), None)
    outcome = (
        next((o for o in source.outcomes if o.key == demand.outcome), None) if source else None
    )
    if unit is None or outcome is None or unit.key not in outcome.units:
        return "teaching unit is missing or does not link this source outcome."
    blocks = {block.key: block for block in unit.blocks}
    if set(target.blocks) - blocks.keys() or not any(
        demand.source in blocks[key].sources for key in target.blocks
    ):
        return "the mapped core teaching blocks or their source are missing."
    question = next(
        (question for question in unit.questions if question.key == target.question), None
    )
    levels = {"recall": 0, "apply": 1, "reason": 2}
    if (
        question is None
        or question.objective != target.objective
        or demand.source not in question.sources
        or levels[question.level] < levels[demand.level]
    ):
        return "the mapped practice must address this objective, source and action level."
    return None


def _exercise_problem(
    demand: ExerciseDemand, content: ExerciseContent | None, ledger: CoverageLedger
) -> str | None:
    target = demand.target
    if not target or not content:
        return "missing original exercise statement, guide and answer mapping."
    group = next((group for group in content.sets if group.key == target.set), None)
    exercise = (
        next((item for item in group.exercises if item.key == target.exercise), None)
        if group
        else None
    )
    source = next((entry for entry in ledger.sources if entry.source == demand.source), None)
    item = (
        next((entry for entry in source.items if entry.label == demand.label), None)
        if source
        else None
    )
    if (
        group is None
        or group.sheet != demand.source
        or exercise is None
        or exercise.kind != "original"
        or item is None
        or item.exercise != exercise.key
        or (item.part and item.part != target.part)
        or not any(ref.key == demand.source for ref in exercise.sources)
    ):
        return "the mapping must point to the original problem on this source sheet."
    if demand.part != target.part:
        return "the authored part must keep the original part label."
    step = next((step for step in exercise.steps if step.key == target.step), None)
    if step is None or step.part != target.part:
        return "the guide step does not belong to this part."
    if target.part is None:
        if exercise.parts or demand.part is not None or len(exercise.solution.answers) != 1:
            return "map each original part separately."
        if target.statement not in {block.key for block in exercise.statement}:
            return "the statement block is missing."
        answer = exercise.solution.answers[0]
    else:
        if demand.part is None or exercise.part_blocks.get(target.part) != target.statement:
            return "the original part or its statement block is missing."
        answer = exercise.solution.answers[exercise.parts.index(target.part)]
    if isinstance(target.answer_block, int):
        if target.answer_block >= len(answer.blocks):
            return "the mapped answer block is missing."
    elif target.answer_block not in {block.key for block in answer.blocks}:
        return "the mapped answer block is missing."
    return None


def _draft_items(
    scope: Preparation,
    ledger: CoverageLedger,
    study: StudyContent | None,
    exercises: ExerciseContent | None,
) -> tuple[dict[str, list[dict[str, JsonValue]]], list[str]]:
    items: dict[str, list[dict[str, JsonValue]]] = defaultdict(list)
    problems: list[str] = []
    for demand in scope.demands:
        match demand:
            case StudyDemand(target=target):
                problem = _study_problem(demand, study, ledger)
                key = f"study/{target.unit}" if target else ""
            case ExerciseDemand(target=target):
                problem = _exercise_problem(demand, exercises, ledger)
                key = f"exercises/{target.set}/{target.exercise}" if target else ""
        if problem:
            problems.append(f"{demand.source}/{demand.id}: {problem}")
        elif key:
            items[key].append(demand.model_dump(mode="json"))
    for group in exercises.sets if exercises else ():
        for exercise in group.exercises:
            key = f"exercises/{group.key}/{exercise.key}"
            if key not in items:
                continue
            mapped = {
                demand.target.part
                for demand in scope.demands
                if isinstance(demand, ExerciseDemand)
                and demand.target
                and demand.target.set == group.key
                and demand.target.exercise == exercise.key
            }
            if missing := set(exercise.parts) - mapped:
                problems.append(
                    f"{key}: missing original part mappings {', '.join(sorted(missing))}."
                )
    return dict(items), problems


def _browser_problems(root: Path, routes: list[str], visuals: set[str]) -> list[str]:
    receipt = read_receipt(root)
    if receipt is None:
        return [
            "Missing browser receipts. Run study visuals and study visuals --interact with --phone."
        ]
    identity = browser_identity(root, browser_choice())
    if not identity.managed or receipt.identity != identity:
        return ["Browser evidence is stale or the app has custom templates. Rebuild and recheck."]
    required = {
        *(f"visual/{width}/{item}" for width in WIDTHS for item in visuals),
        *(f"interact/{width}/{route}" for width in WIDTHS for route in routes),
        *(
            f"shell/{width}/{theme}/{workspace}"
            for width in WIDTHS
            for theme in ("light", "dark")
            for workspace in {shell_workspace(route) for route in routes}
        ),
    }
    return [
        f"{key}: browser evidence is {'failed' if receipt.states.get(key) is False else 'missing'}."
        for key in sorted(required)
        if not receipt.evidence(root, key)
    ]


def assess(root: Path, identifier: str, context: "Context | None" = None) -> Readiness:
    """Read the prepared request, map its evidence and check the current build."""
    from tum_mcp.course.review.loop import load

    root = root.expanduser().resolve()
    scope = read_preparation(root, identifier)
    if scope is None:
        return Readiness(identifier=identifier, problems=("Record the preparation scope first.",))
    state = load_state(root)
    ledger = read_ledger(root)
    schedule = read_schedule(root, state) if scope.cutoff else None
    problems = scope_problems(scope, state, ledger, schedule)
    kwargs = {
        "identifier": identifier,
        "scope": PreparedScope(identifier=identifier, fingerprint=scope.fingerprint()),
        "mode": scope.mode,
        "cutoff": scope.cutoff.isoformat() if scope.cutoff else None,
        "dispositions": tuple(entry.model_dump(mode="json") for entry in scope.inventory),
        "walkthrough_evidence": scope.walkthrough_evidence,
        **scope_summary(scope, state, problems),
    }
    if ledger is None:
        return Readiness(**kwargs, problems=tuple(problems))
    study = read_content(root) if present(root, "study") else None
    exercises = read_exercises(root)
    items, draft_problems = _draft_items(scope, ledger, study, exercises)
    problems.extend(draft_problems)
    if problems:
        return Readiness(**kwargs, items=items, problems=tuple(problems))

    context = context or load(root)
    outcomes = {outcome.key for entry in ledger.sources for outcome in entry.outcomes}
    verified = {result["item"]: result for result in context.answer_keys}
    provisional = []
    read_coverage = coverage_reader(root)
    for key, demands in items.items():
        plan = read_plan(root, key)
        status = (
            gate_status(plan, coverage_reader_for_command=read_coverage) if plan else "unchecked"
        )
        if plan is None or plan.item != key or status == "unchecked":
            problems.append(f"{key}: check the teaching plan with review plans --item {key}.")
        elif status == "changed":
            problems.append(f"{key}: source coverage changed or plan edited. Check it again.")
        elif status == "rejected":
            reasons = "; ".join(plan.gate.reasons) if plan.gate else ""
            problems.append(f"{key}: repair the rejected teaching plan. {reasons}")
        else:
            if plan.preparation and (plan.preparation != identifier or plan.gate is None):
                problems.append(f"{key}: source coverage changed; check the plan against it again.")
            problems.extend(
                f"{key}: {problem}"
                for problem in plan_problems(plan, context.items[key].value, outcomes)
            )
            if status == "provisional":
                provisional.append(key)
        problems.extend(
            f"{key}: {flag['detail']}"
            for flag in context.flags_by_item.get(key, [])
            if flag["flag"] in INVARIANT_FLAGS
        )
        result = verified.get(key, {})
        for demand in demands:
            for kind in ("values", "walkthroughs"):
                if demand[kind] and (
                    not result.get("passed") or not set(demand[kind]) <= set(result.get(kind, ()))
                ):
                    problems.append(f"{key}/{demand['id']}: missing or failed answer-key {kind}.")
    stale = {
        "study": set(stale_units(root, state, study) if study else ()),
        "exercises": set(stale_exercises(root, state, exercises) if exercises else ()),
    }
    problems.extend(
        f"{key}: cited source bytes or revisions changed."
        for key in items
        if key.rsplit("/", 1)[-1] in stale[key.split("/", 1)[0]]
    )
    data = read_bytes(confined(root, "app/data.mjs"))
    if data is None or data != current_data(root):
        problems.append("The built app does not match current content. Run study build.")
    elif not problems:
        routes = interaction_routes(study, exercises)
        problems.extend(
            _browser_problems(
                root,
                [route for key, route in routes.items() if key in items],
                set(items) & context.visuals.keys(),
            )
        )

    sources = {entry.source: entry.sha256 for entry in scope.inventory}
    fingerprints = {
        key: digest(
            {
                "scope": scope.fingerprint(),
                "demands": demands,
                "sources": {demand["source"]: sources[demand["source"]] for demand in demands},
            }
        )
        for key, demands in items.items()
    }
    return Readiness(
        **kwargs,
        items=items,
        fingerprints=fingerprints,
        problems=tuple(problems),
        provisional_plans=tuple(provisional),
    )
