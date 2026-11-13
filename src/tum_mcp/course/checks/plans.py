"""Structured plans, written before an item and checked by one fresh reader before writing.

A plan lives at `.tum-mcp/plans/<item>.json`. Code checks its links (outcomes in the ledger,
block keys in the written item, parts of the exercise) and the defaults each concept kind
brings; the plan gate records a fresh checker's verdict against the plan's fingerprint.
"""

import hashlib
import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.course.content.study import (
    Label,
    Text,
)
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.course.project.store import Write, apply, confined, private_name, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

if TYPE_CHECKING:
    from tum_mcp.course.checks.preparation import Readiness

type CoverageReader = Callable[[str, tuple[str, ...] | None], tuple["Readiness", tuple[str, ...]]]

ConceptKind = Literal[
    "definition", "fact", "rule", "procedure", "algorithm", "model", "comparison", "cases"
]
STEPPED = "a walkthrough, a stepped diagram, a derivation walkthrough or a code walkthrough"
# A model is a system of parts and the flows between them; it is understood from a picture.
PICTURES = {"figure", "diagram", "uml", "tree"}


# Only these kinds require an example or skip; a selected example can teach any kind.
WORKED_KINDS = {"procedure", "algorithm", "model"}


class Example(Frozen):
    """The worked example a concept is taught on, chosen from the lecture's demonstrations."""

    origin: Literal["source", "constructed"]
    source: Key | None = Field(default=None, exclude_if=lambda value: value is None)
    pages: Annotated[str, Field(min_length=1, max_length=40)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    shows: Text = Field(
        description="The example's inputs and conventions, the object to show, and the decisive "
        "working or test that makes its teaching point. Include what other chosen examples "
        "cannot show."
    )
    endpoint: Text = Field(
        description="The full endpoint and the result or comparison it teaches. A justified "
        "inconclusive endpoint is valid; a useful continuation beyond the lecture is allowed."
    )
    block: Key
    states: Annotated[int, Field(strict=True, ge=1)] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Number of distinct states the cited source pages show for this run.",
    )
    phases: tuple[Label, ...] = Field(
        default=(),
        exclude_if=lambda value: not value,
        description="The source's phase names, used as walkthrough subgoal groups.",
    )
    why: Text | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="For a constructed example: why the lecture has no example for this concept.",
    )

    @model_validator(mode="after")
    def located(self) -> "Example":
        if self.origin == "source" and not (self.source and self.pages):
            raise ValueError("A lecture example names its source and pages.")
        if self.origin == "constructed" and not self.why:
            raise ValueError("A constructed example says why the lecture has none.")
        return self


class Concept(Frozen):
    name: Label
    kind: ConceptKind
    # The worked case that shows the idea: an example, an instance, a counterexample.
    instance: Text = Field(
        description="A concrete case with its input, result or classification, and why it "
        "demonstrates the concept. A scenario or a question without its result is incomplete."
    )
    outcomes: tuple[Key, ...] = ()
    blocks: tuple[Key, ...] = ()
    # Why the kind's default representation does not fit this concept.
    skip: Text | None = None
    example: Example | None = Field(default=None, exclude_if=lambda value: value is None)


class Part(Frozen):
    part: Annotated[str, Field(min_length=1, max_length=20)]
    answer: Text
    method: Text


class PracticeCase(Frozen):
    question: Key
    contrast: Text = Field(
        description="Name the worked case and the unworked input or decision the student "
        "must solve. Routine application can use new values; do not claim that cosmetic "
        "renaming alone establishes deeper transfer."
    )
    answer: Text = Field(description="The new case's result and shortest valid reasoning.")


class GateEntry(Frozen):
    check: int
    kind: Literal["reason", "advice"]
    text: Text
    state: Literal["open", "resolved", "escalated"] = "open"


class GateUpdates(Frozen):
    resolved: tuple[str | int, ...] = ()
    evidence: dict[str, str] = Field(default_factory=dict)


class Approval(Frozen):
    fingerprint: str
    verdict: Literal["pass", "fail"]
    reasons: tuple[Text, ...] = ()
    # Improvements a checker suggests without failing the plan.
    advice: tuple[Text, ...] = Field(default=(), exclude_if=lambda value: not value)
    provenance: Literal["fresh", "same"]
    coverage_fingerprint: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # The batches whose requests the approval read; a batch declared later, such as one that
    # groups earlier batches for a combined review, does not reopen it.
    batches: tuple[Key, ...] | None = Field(default=None, exclude_if=lambda value: value is None)
    history: tuple[GateEntry, ...] = Field(default=(), exclude_if=lambda value: not value)
    concepts: dict[str, str] = Field(default_factory=dict, exclude_if=lambda value: not value)
    checks: int = Field(default=0, exclude_if=lambda value: not value)


class WorkedDecision(Frozen):
    source: Key
    demand: Key
    decision: Key
    block: Key
    run: Literal["primary", "variant"] = "primary"
    step: Annotated[int, Field(ge=1)] | None = None
    value_path: Text | None = None


class Plan(Frozen):
    item: Annotated[str, Field(min_length=1, max_length=200)]
    preparation: Key | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Source preparation scope determined before drafting this item.",
    )
    outcomes: tuple[Key, ...] = ()
    concepts: tuple[Concept, ...] = Field(default=(), max_length=30)
    parts: tuple[Part, ...] = Field(default=(), max_length=30)
    # The cases of an exam pattern, or the notes and highlights of a lecture.
    cases: tuple[Text, ...] = Field(default=(), max_length=20)
    practice: tuple[PracticeCase, ...] = Field(
        default=(), max_length=100, exclude_if=lambda value: not value
    )
    worked_decisions: tuple[WorkedDecision, ...] = Field(
        default=(), max_length=200, exclude_if=lambda v: not v
    )
    gate: Approval | None = None

    def fingerprint(self) -> str:
        body = json.dumps(self.model_dump(mode="json", exclude={"gate"}), sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:16]


def plan_path(root: Path, item: str) -> Path:
    return confined(root, f".tum-mcp/plans/{item}.json")


def read_plan(root: Path, item: str) -> Plan | None:
    body = read_bytes(plan_path(root, item))
    return _parse_plan(item, body) if body is not None else None


def _parse_plan(item: str, body: bytes) -> Plan:
    try:
        return Plan.model_validate_json(body)
    except ValidationError as error:
        raise CampusError(
            Code.INVALID_RESPONSE, f"Plan {item}: {error.errors()[0]['msg']}"
        ) from None


def plans(root: Path) -> list[Plan]:
    folder = confined(root, ".tum-mcp/plans")
    found = sorted(folder.glob("**/*.json")) if folder.is_dir() else []
    return [
        plan
        for path in found
        if (plan := read_plan(root, path.relative_to(folder).with_suffix("").as_posix()))
    ]


def _stepped(block: dict) -> bool:
    return (
        block.get("kind") == "walkthrough"
        or (block.get("kind") == "diagram" and len(block.get("frames", [])) > 1)
        or (block.get("kind") == "code" and bool(block.get("walkthrough")))
        or (block.get("kind") == "derivation" and bool(block.get("walkthrough")))
    )


def plan_problems(plan: Plan, value: dict | None, outcomes: set[str] | None) -> list[str]:
    """What a plan links to that does not exist, and the kind defaults it misses without a
    reason. `value` is the written item (None before writing); `outcomes` the ledger's keys."""
    problems: list[str] = []
    wanted = {*plan.outcomes, *(key for concept in plan.concepts for key in concept.outcomes)}
    if outcomes is not None and (unknown := sorted(wanted - outcomes)):
        problems.append(f"outcomes not in the ledger: {', '.join(unknown)}")
    if value is None:
        return problems
    problems.extend(str(flag["detail"]) for flag in example_state_flags(plan, value))
    questions = {question["key"]: question for question in value.get("questions", [])}
    for case in plan.practice:
        if case.question not in questions:
            problems.append(f"{case.question}: planned practice question is missing")
    blocks = {
        block["key"]: block
        for block in value.get("blocks", value.get("statement", []))
        if isinstance(block, dict) and block.get("key")
    }
    for concept in plan.concepts:
        if concept.example and concept.example.block not in blocks:
            problems.append(f"{concept.name}: the example block {concept.example.block} is missing")
        if missing := sorted(set(concept.blocks) - blocks.keys()):
            problems.append(f"{concept.name}: blocks not in the item: {', '.join(missing)}")
            continue
        if concept.skip:
            continue
        shown = [blocks[key] for key in concept.blocks]
        if concept.kind in {"procedure", "algorithm"} and not any(map(_stepped, shown)):
            problems.append(f"{concept.name}: a {concept.kind} is taught with {STEPPED}")
        if concept.kind == "comparison" and not any(b.get("kind") == "table" for b in shown):
            problems.append(f"{concept.name}: a comparison is shown as a table")
        if concept.kind == "cases" and not any(
            b.get("kind") in {"table", "example"} for b in shown
        ):
            problems.append(
                f"{concept.name}: parallel cases are a table, or one example block per case"
            )
        if concept.kind == "model" and not any(b.get("kind") in PICTURES for b in shown):
            problems.append(
                f"{concept.name}: a model is drawn as a figure, diagram, UML diagram or tree"
            )
        if concept.kind == "definition":
            if not any(b.get("kind") == "definition" for b in shown):
                problems.append(
                    f"{concept.name}: link the definition block that states its meaning."
                )
            elif all(b.get("kind") == "definition" for b in shown):
                problems.append(
                    f"{concept.name}: a definition is shown with an example or case; name the "
                    "block that shows it in the concept's `blocks`"
                )
    if plan.parts and (declared := value.get("parts")) is not None:
        planned = [part.part for part in plan.parts]
        if planned != list(declared):
            problems.append(f"parts {planned} do not match the exercise's parts {declared}")
    return problems


def example_state_flags(plan: Plan, value: dict) -> list[dict[str, JsonValue]]:
    """Compare a selected walkthrough with the source states and phases its planner counted."""
    blocks = {block.get("key"): block for block in value.get("blocks", [])}
    flags: list[dict[str, JsonValue]] = []
    for concept in plan.concepts:
        example = concept.example
        if example is None or (block := blocks.get(example.block)) is None:
            continue
        if block.get("kind") != "walkthrough":
            continue
        steps = block["steps"]
        item = f"{plan.item.removeprefix('study/')}/{example.block}"
        if example.states is not None and len(steps) < example.states:
            flags.append(
                {
                    "item": item,
                    "flag": "source_states_missing",
                    "detail": f"{concept.name}: walkthrough {example.block} has {len(steps)} "
                    f"steps for {example.states} planned source states. Restore the source's "
                    "states in this one walkthrough; never drop, merge or split steps "
                    "to shorten it.",
                }
            )
        groups = {_normalized(step["subgoal"]) for step in steps if step.get("subgoal")}
        missing = [phase for phase in example.phases if _normalized(phase) not in groups]
        if example.phases and (missing or any(not step.get("subgoal") for step in steps)):
            flags.append(
                {
                    "item": item,
                    "flag": "source_phases_missing",
                    "detail": f"{concept.name}: group walkthrough {example.block}'s steps with "
                    f"`subgoal` covering the planned source phases: {', '.join(example.phases)}."
                    + (f" Missing: {', '.join(missing)}." if missing else "")
                    + " Keep all steps in this one walkthrough, including any continuation.",
                }
            )
    return flags


def coverage_reader(root: Path) -> CoverageReader:
    from tum_mcp.course.checks.coverage_plan import assess_plan, declaring_batches

    @cache
    def discovered(identifier: str) -> tuple[str, ...]:
        return declaring_batches(root, identifier)

    @cache
    def assess(identifier: str, batches: tuple[str, ...]) -> "Readiness":
        return assess_plan(root, identifier, batches)

    def read(
        identifier: str, batches: tuple[str, ...] | None
    ) -> tuple["Readiness", tuple[str, ...]]:
        bound = discovered(identifier) if batches is None else batches
        return assess(identifier, bound), bound

    return read


def example_problems(plan: Plan) -> list[str]:
    """A Study concept that is performed or read off a picture is taught on a chosen example."""
    if not plan.item.startswith("study/"):
        return []
    return [
        f"{plan.item}/{concept.name}: choose the lecture example that teaches this {concept.kind}, "
        "or say why the lecture has none."
        for concept in plan.concepts
        if concept.kind in WORKED_KINDS and concept.example is None and not concept.skip
    ]


def gate_status(
    plan: Plan,
    root: Path | None = None,
    *,
    coverage_reader_for_command: CoverageReader | None = None,
) -> str:
    """approved, rejected, provisional (only the author read it), changed or unchecked."""
    if plan.gate is None:
        return "unchecked"
    if plan.gate.fingerprint != plan.fingerprint():
        return "changed"
    read = coverage_reader_for_command or (coverage_reader(root) if root is not None else None)
    if read is not None and plan.preparation:
        coverage, _ = read(plan.preparation, plan.gate.batches)
        if (
            not coverage.ready
            or coverage.scope is None
            or plan.gate.coverage_fingerprint != coverage.scope.fingerprint
        ):
            return "changed"
    if plan.gate.verdict == "fail":
        return "rejected"
    return "approved" if plan.gate.provenance == "fresh" else "provisional"


def _concept_hashes(plan: Plan) -> dict[str, str]:
    return {
        concept.name: hashlib.sha256(
            json.dumps(concept.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()[:16]
        for concept in plan.concepts
    }


def _history(gate: Approval | None) -> list[GateEntry]:
    if gate is None:
        return []
    if gate.history:
        return list(gate.history)
    return [
        *(GateEntry(check=1, kind="reason", text=text) for text in gate.reasons),
        *(GateEntry(check=1, kind="advice", text=text) for text in gate.advice),
    ]


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _updated_history(
    plan: Plan, updates: GateUpdates, reasons: tuple[str, ...], advice: tuple[str, ...]
) -> tuple[GateEntry, ...]:
    history = _history(plan.gate)
    for reason in reasons:
        matching = [
            entry
            for entry in history
            if entry.kind == "advice"
            and entry.state != "escalated"
            and _normalized(entry.text) == _normalized(reason)
        ]
        if not matching or any(
            entry.kind == "reason" and _normalized(entry.text) == _normalized(reason)
            for entry in history
        ):
            continue
        history = [
            entry.model_copy(update={"state": "escalated"}) if entry in matching else entry
            for entry in history
        ]
    for resolved in updates.resolved:
        matches = [
            index
            for index, entry in enumerate(history)
            if (isinstance(resolved, int) and not isinstance(resolved, bool) and index == resolved)
            or (isinstance(resolved, str) and _normalized(entry.text) == _normalized(resolved))
        ]
        if not matches:
            raise CampusError(
                Code.ACTION_REQUIRED,
                f"Plan {plan.item}: unknown resolved history entry {resolved!r}.",
            )
        for index in matches:
            if history[index].state == "open":
                history[index] = history[index].model_copy(update={"state": "resolved"})
    number = (
        max(
            plan.gate.checks if plan.gate else 0, max((entry.check for entry in history), default=0)
        )
        + 1
    )
    history.extend(GateEntry(check=number, kind="reason", text=text) for text in reasons)
    history.extend(GateEntry(check=number, kind="advice", text=text) for text in advice)
    return tuple(history)


def record_gate(root: Path, answers: list[dict], provenance: Literal["fresh", "same"]) -> dict:
    """Save a checker's plan verdicts; each applies to the plan as it was read."""
    read_coverage = coverage_reader(root)
    writes: list[Write] = []
    recorded: list[str] = []
    verdicts: dict[str, dict] = {}
    for answer in answers:
        item = str(answer.get("item", ""))
        name = private_name(root, f"plans/{item}.json")
        original = read_bytes(confined(root, name))
        if original is None:
            raise CampusError(Code.ACTION_REQUIRED, f"No plan for {item}.")
        plan = _parse_plan(item, original)
        if answer.get("fingerprint") != plan.fingerprint():
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item} changed since it was read.")
        coverage, batches = (
            _coverage(plan.preparation, plan.item, read_coverage)
            if plan.preparation
            else (None, None)
        )
        if coverage and answer.get("coverage_fingerprint") != coverage["scope"]["fingerprint"]:
            raise CampusError(
                Code.ACTION_REQUIRED, f"Plan {item}: coverage changed or was not checked."
            )
        verdict = answer.get("verdict")
        reasons = tuple(str(reason) for reason in answer.get("reasons", []))
        advice = tuple(str(note) for note in answer.get("advice", []))
        if verdict not in {"pass", "fail"} or (verdict == "fail" and not reasons):
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item}: pass, or fail with the reasons.")
        if (
            provenance == "same"
            and plan.gate
            and (plan.gate.provenance == "fresh" or plan.gate.verdict == "fail")
            and gate_status(plan, coverage_reader_for_command=read_coverage)
            in {"approved", "rejected"}
        ):
            reason = (
                "a current independent verdict already exists."
                if plan.gate.provenance == "fresh"
                else "repair the rejected plan and check the changed inputs first."
            )
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item}: {reason}")
        checks = (
            max(
                plan.gate.checks if plan.gate else 0,
                max((entry.check for entry in _history(plan.gate)), default=0),
            )
            + 1
        )
        try:
            updates = GateUpdates.model_validate(
                {"resolved": answer.get("resolved", []), "evidence": answer.get("evidence", {})}
            )
        except ValidationError as error:
            raise CampusError(
                Code.ACTION_REQUIRED, f"Plan {item}: {error.errors()[0]['msg']}"
            ) from None
        if plan.gate:
            hashes = _concept_hashes(plan)
            changed = {
                name
                for name in hashes.keys() | plan.gate.concepts.keys()
                if hashes.get(name) != plan.gate.concepts.get(name)
            }
            prior = {
                _normalized(entry.text)
                for entry in _history(plan.gate)
                if entry.kind == "reason" and entry.state == "open"
            }
            evidence = {_normalized(key): value.strip() for key, value in updates.evidence.items()}
            demoted = tuple(
                reason
                for reason in reasons
                if _normalized(reason) not in prior
                and not any(_normalized(name) in _normalized(reason) for name in changed)
                and not evidence.get(_normalized(reason))
            )
            reasons = tuple(reason for reason in reasons if reason not in demoted)
            advice = tuple(dict.fromkeys((*advice, *demoted)))
            if verdict == "fail" and not reasons:
                verdict = "pass"
        if verdict == "pass" and (problems := example_problems(plan)):
            raise CampusError(Code.ACTION_REQUIRED, " ".join(problems[:5]))
        history = _updated_history(plan, updates, reasons, advice)
        gate = Approval(
            fingerprint=plan.fingerprint(),
            verdict=verdict,
            reasons=reasons,
            advice=advice,
            provenance=provenance,
            coverage_fingerprint=coverage["scope"]["fingerprint"] if coverage else None,
            batches=batches,
            history=history,
            concepts=_concept_hashes(plan),
            checks=checks,
        )
        body = json.dumps(plan.model_copy(update={"gate": gate}).model_dump(mode="json"), indent=2)
        writes.append(Write(name, original, body.encode()))
        recorded.append(item)
        verdicts[item] = {
            "verdict": verdict,
            "reasons": list(reasons),
            **({"advice": list(advice)} if advice else {}),
        }
    apply(root, tuple(writes))
    return {
        "recorded": recorded,
        "verdicts": verdicts,
        "provenance": provenance,
        "next": (
            "Repair the rejected plans using these reasons, then check the changed plans."
            if any(result["verdict"] == "fail" for result in verdicts.values())
            else (
                "Author a provisional draft from these same-author checks."
                if provenance == "same"
                else "Author the requested items from these plans; reuse unchanged approvals. "
                "Apply any advice that improves the lesson; it needs no further check."
            )
        ),
    }


def _coverage(
    preparation: str, item: str, read_coverage: CoverageReader
) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
    coverage, batches = read_coverage(preparation, None)
    report = coverage.report()
    if not report["ready"]:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Plan {item}: determine coverage before drafting. " + " ".join(coverage.problems[:5]),
        )
    return report, batches


def _pages(value: str) -> set[int]:
    if not re.fullmatch(r"\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*", value):
        return set()
    pages: set[int] = set()
    for part in value.split(","):
        start, _, end = part.strip().partition("-")
        pages.update(range(int(start), int(end or start) + 1))
    return pages


def _unused_examples(root: Path, waiting: list[Plan]) -> list[JsonValue]:
    from tum_mcp.course.sources.digests import read_digest

    used: dict[str, set[int]] = {}
    for plan in waiting:
        for concept in plan.concepts:
            example = concept.example
            if example and example.source and example.pages:
                used.setdefault(example.source, set()).update(_pages(example.pages))
    folder = confined(root, ".tum-mcp/digests")
    unused: list[JsonValue] = []
    for path in sorted(folder.glob("*.json")):
        digest = read_digest(root, path.stem)
        if digest:
            unused.extend(
                {"source": digest.source, "kind": kind, "pages": entry.pages, "text": entry.text}
                for kind, entries in (("example", digest.examples), ("figure", digest.figures))
                for entry in entries
                # A figure can teach a separate idea on the same page as a selected example.
                if kind == "figure" or not (_pages(entry.pages) & used.get(digest.source, set()))
            )
    return unused


def plan_packet(root: Path, items: tuple[str, ...] = ()) -> dict[str, JsonValue]:
    """Read the requested authoring batch or all plans waiting for a fresh checker."""
    read_coverage = coverage_reader(root)
    if items:
        waiting = []
        for item in dict.fromkeys(items):
            plan = read_plan(root, item)
            if plan is None or plan.item != item:
                raise CampusError(Code.ACTION_REQUIRED, f"No plan for {item}.")
            waiting.append(plan)
    else:
        waiting = [
            plan
            for plan in plans(root)
            if gate_status(plan, coverage_reader_for_command=read_coverage) != "approved"
        ]
    coverage = {}
    for plan in waiting:
        if plan.preparation and plan.preparation not in coverage:
            coverage[plan.preparation] = _coverage(plan.preparation, plan.item, read_coverage)[0]
    return {
        **({"coverage": coverage} if coverage else {}),
        "unused_examples": _unused_examples(root, waiting),
        "plans": [
            {
                **plan.model_dump(mode="json", exclude={"gate"}),
                "concepts": [
                    concept.model_dump(mode="json")
                    | (
                        {
                            "changed": (
                                _concept_hashes(plan)[concept.name]
                                != plan.gate.concepts.get(concept.name)
                            )
                        }
                        if plan.gate
                        else {}
                    )
                    for concept in plan.concepts
                ],
                "fingerprint": plan.fingerprint(),
                **(
                    {"coverage_fingerprint": coverage[plan.preparation]["scope"]["fingerprint"]}
                    if plan.preparation
                    else {}
                ),
                **(
                    {"status": gate_status(plan, coverage_reader_for_command=read_coverage)}
                    if items
                    else {}
                ),
                **(
                    {"previous": list(plan.gate.reasons)}
                    if plan.gate and plan.gate.verdict == "fail"
                    else {}
                ),
                **(
                    {"history": [entry.model_dump(mode="json") for entry in _history(plan.gate)]}
                    if plan.gate
                    else {}
                ),
            }
            for plan in waiting
        ],
        "answer": {
            "items": [
                {
                    "item": plan.item,
                    "fingerprint": plan.fingerprint(),
                    **(
                        {"coverage_fingerprint": coverage[plan.preparation]["scope"]["fingerprint"]}
                        if plan.preparation
                        else {}
                    ),
                    "verdict": "pass|fail",
                    "reasons": [],
                    "advice": [],
                    "resolved": [],
                    "evidence": {},
                }
                for plan in waiting
            ]
        },
        "ask": (
            "1. On the first check, list every blocking problem you can find in one pass. "
            "On later checks, verify each history reason first; put fixed entry texts or "
            "zero-based history indices in resolved. Raise a new blocker only for a changed "
            "concept named in full in the reason or something that change breaks. A new blocker on "
            "an unchanged concept, including earlier advice, needs an evidence entry keyed "
            "by its reason naming a new source page or fact; otherwise it becomes advice.\n"
            "2. Read coverage and the original request. Audit every demand, deferred outcome "
            "and subpart against the source. Broad requests include conditions, guarantees "
            "and costs; exercises retain requested parts. Check all learner actions, clauses "
            "and final results, not just a first step. Never narrow scope to fit the draft.\n"
            "3. Check each concept has a concrete case, a fitting representation or a real "
            "skip reason, and prerequisites before use. Definitions, rules and comparisons can "
            "use short cases when no source demonstration is needed; do not invent worked runs. "
            "Define core terms and properties "
            "used in comparisons, headings and conditions, with their defining conditions "
            "and a useful case; a method-specific guarantee is not a general definition.\n"
            "4. Compare critical Study demonstrations of any concept kind with digest "
            "examples, figures and source pages. A critical source example or figure that "
            "teaches a rule, comparison, property, theorem or definition is planned as that "
            "concept's `example`, naming its representation. Mentioning its idea in `instance` "
            "text does not select it. A concept without a source demonstration needs no "
            "example unless its kind requires one. On the first check judge "
            "unused_examples "
            "as selection context: a required method run, a new decision, branch or failure, "
            "a case later material builds on, or a worked argument, calculation or visual "
            "that explains a method's validity, limits or costs can be critical. Judge the "
            "learning need; decorative illustrations without reasoning or usable inputs are "
            "not worked demonstrations. The kind marker distinguishes examples and figures; "
            "figures remain context even on selected pages because page overlap does not "
            "prove their idea is taught. This is selection context, not a quota. Write nothing "
            "for the rest. "
            "Keep critical lecture examples complete: inputs, representation, decisive tests "
            "and working, and endpoint or comparison. Page overlap or a concept mention does "
            "not establish that the selected demonstration is complete. Keep the source range "
            "that contains its decisive test and conclusion, not just its setup. "
            "When an example records states or phases, verify the count of distinct states "
            "and the phase names against its cited source pages. They are a floor, not a cap. "
            "Finish incomplete source working with its original inputs when the result matters. "
            "Going beyond the source is fine; covering less is not. Do not invent missing "
            "givens or a desired result to force an ending. For each additional example "
            "of one mechanism say what it shows that the first cannot; otherwise it is a repeat. "
            "Leave out repeated mechanisms on another object, applications without workable "
            "inputs and empirical tables. Construct a case only when the lecture has none.\n"
            "5. For Study application or reasoning, check each practice case has its solved "
            "result and an unworked input or decision. Routine new inputs are valid; require "
            "substantive transfer when the objective does. A general rule is not a solved "
            "assessment case; an unchanged worked input tests recall. Reusing a setting can "
            "be valid when a changed condition or input changes the required reasoning. "
            "Do not demand a new setting for routine application. Recall-only objectives "
            "and released exercise statements need no invented transfer case. Check contrasts "
            "against solved examples and reserve assessment cases for practice.\n"
            "6. Fail only for source contradictions, missing or altered critical examples, "
            "untaught outcomes, ideas used before teaching, or wrong solved practice. Put "
            "other improvements in advice. Each reason names everything a complete fix "
            "contains, so one revision can resolve it. Use the answer template, provide "
            "reasons on fail, "
            "and preserve both plan and coverage fingerprints when present."
        ),
    }
