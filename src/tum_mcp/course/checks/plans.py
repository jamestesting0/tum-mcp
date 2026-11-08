"""Structured plans, written before an item and checked by one fresh reader before writing.

A plan lives at `.tum-mcp/plans/<item>.json`. Code checks its links (outcomes in the ledger,
block keys in the written item, parts of the exercise) and the defaults each concept kind
brings; the plan gate records a fresh checker's verdict against the plan's fingerprint.
"""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.content.study import Label, Text
from tum_mcp.course.project.models import Digest, Key
from tum_mcp.course.project.store import Write, apply, confined, private_name, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

ConceptKind = Literal["definition", "fact", "rule", "procedure", "algorithm", "model", "comparison"]
STEPPED = "a walkthrough, a stepped diagram, a derivation walkthrough or a code walkthrough"
# A model is a system of parts and the flows between them; it is understood from a picture.
PICTURES = {"figure", "diagram", "uml", "tree"}


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


class Approval(Frozen):
    fingerprint: str
    verdict: Literal["pass", "fail"]
    reasons: tuple[Text, ...] = ()
    provenance: Literal["fresh", "same"]
    coverage_fingerprint: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # The batches whose requests the approval read; a batch declared later, such as one that
    # groups earlier batches for a combined review, does not reopen it.
    batches: tuple[Key, ...] | None = Field(default=None, exclude_if=lambda value: value is None)


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
    gate: Approval | None = None

    def fingerprint(self) -> str:
        body = json.dumps(self.model_dump(mode="json", exclude={"gate"}), sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:16]


def plan_path(root: Path, item: str) -> Path:
    return confined(root, f".tum-mcp/plans/{item}.json")


def read_plan(root: Path, item: str) -> Plan | None:
    body = read_bytes(plan_path(root, item))
    if body is None:
        return None
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


def gate_status(plan: Plan, root: Path | None = None) -> str:
    """approved, rejected, provisional (only the author read it), changed or unchecked."""
    if plan.gate is None:
        return "unchecked"
    if plan.gate.fingerprint != plan.fingerprint():
        return "changed"
    if root is not None and plan.preparation:
        from tum_mcp.course.checks.coverage_plan import assess_plan

        coverage = assess_plan(root, plan.preparation, plan.gate.batches)
        if coverage.scope is None or plan.gate.coverage_fingerprint != coverage.scope.fingerprint:
            return "changed"
    if plan.gate.verdict == "fail":
        return "rejected"
    return "approved" if plan.gate.provenance == "fresh" else "provisional"


def record_gate(root: Path, answers: list[dict], provenance: Literal["fresh", "same"]) -> dict:
    """Save a checker's plan verdicts; each applies to the plan as it was read."""
    from tum_mcp.course.checks.coverage_plan import declaring_batches

    writes: list[Write] = []
    recorded: list[str] = []
    verdicts: dict[str, dict] = {}
    for answer in answers:
        item = str(answer.get("item", ""))
        plan = read_plan(root, item)
        if plan is None:
            raise CampusError(Code.ACTION_REQUIRED, f"No plan for {item}.")
        if answer.get("fingerprint") != plan.fingerprint():
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item} changed since it was read.")
        coverage = _coverage(root, plan)
        if coverage and answer.get("coverage_fingerprint") != coverage["scope"]["fingerprint"]:
            raise CampusError(
                Code.ACTION_REQUIRED, f"Plan {item}: coverage changed or was not checked."
            )
        verdict = answer.get("verdict")
        reasons = tuple(str(reason) for reason in answer.get("reasons", []))
        if verdict not in {"pass", "fail"} or (verdict == "fail" and not reasons):
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item}: pass, or fail with the reasons.")
        gate = Approval(
            fingerprint=plan.fingerprint(),
            verdict=verdict,
            reasons=reasons,
            provenance=provenance,
            coverage_fingerprint=coverage["scope"]["fingerprint"] if coverage else None,
            batches=declaring_batches(root, plan.preparation) if plan.preparation else None,
        )
        name = private_name(root, f"plans/{item}.json")
        body = json.dumps(plan.model_copy(update={"gate": gate}).model_dump(mode="json"), indent=2)
        writes.append(Write(name, read_bytes(confined(root, name)), body.encode()))
        recorded.append(item)
        verdicts[item] = {"verdict": verdict, "reasons": list(reasons)}
    apply(root, tuple(writes))
    return {
        "recorded": recorded,
        "verdicts": verdicts,
        "next": (
            "Repair the rejected plans using these reasons, then check the changed plans."
            if any(result["verdict"] == "fail" for result in verdicts.values())
            else "Author the requested items from these plans; reuse unchanged approvals."
        ),
    }


def _coverage(root: Path, plan: Plan) -> dict | None:
    if plan.preparation is None:
        return None
    from tum_mcp.course.checks.coverage_plan import assess_plan

    report = assess_plan(root, plan.preparation).report()
    if not report["ready"]:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"Plan {plan.item}: determine coverage before drafting. "
            + " ".join(report["problems"][:5]),
        )
    return report


def plan_packet(root: Path, items: tuple[str, ...] = ()) -> dict[str, JsonValue]:
    """Read the requested authoring batch or all plans waiting for a fresh checker."""
    if items:
        waiting = []
        for item in dict.fromkeys(items):
            plan = read_plan(root, item)
            if plan is None or plan.item != item:
                raise CampusError(Code.ACTION_REQUIRED, f"No plan for {item}.")
            waiting.append(plan)
    else:
        waiting = [plan for plan in plans(root) if gate_status(plan, root) != "approved"]
    coverage = {plan.preparation: _coverage(root, plan) for plan in waiting if plan.preparation}
    return {
        **({"coverage": coverage} if coverage else {}),
        "plans": [
            {
                **plan.model_dump(mode="json", exclude={"gate"}),
                "fingerprint": plan.fingerprint(),
                **(
                    {"coverage_fingerprint": coverage[plan.preparation]["scope"]["fingerprint"]}
                    if plan.preparation
                    else {}
                ),
                **({"status": gate_status(plan, root)} if items else {}),
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
                }
                for plan in waiting
            ]
        },
        "ask": (
            "For each plan: does every concept have a worked instance that shows it (a concrete "
            "case, not the concept restated), does each "
            "kind get a fitting representation (or a real reason to skip it), does the order "
            "build each idea before it is used, and does it cover its outcomes? "
            "Identify new core terms and properties used to compare methods or justify answers, "
            "even when they appear only in headings or conditions. Plan their concise general "
            "meaning as definitions, with their defining conditions and a useful case. A "
            "method-specific guarantee or example does not define the underlying property. "
            "For Study application or reasoning outcomes, inspect `practice`: each question "
            "needs its solved result and an unworked input or decision. Routine application "
            "with new inputs is valid; require substantive transfer when the objective calls "
            "for it. A general rule taught in the lesson is not itself a solved assessment "
            "case. Replaying an unchanged worked input and answer tests recall. Reusing a "
            "graph can be valid when a changed "
            "start, goal or ordering genuinely changes the reasoning. Recall-only objectives "
            "and original released exercise statements do not need invented transfer cases. "
            "Check that each stated contrast is actually true of the solved worked instances, "
            "not merely a promise that the case is different. Reserve assessment cases for "
            "practice rather than also using them as lesson examples. "
            "First read coverage for the plan's preparation: check every source demand and "
            "its original request. Audit every deferred outcome and subpart against that "
            "request and the actual source sections. A broad topic request does not authorize "
            "excluding its own conditions, guarantees or costs simply to shorten the lesson. "
            "A selected exercise retains all requested subparts. Then check every "
            "planned learner action, "
            "including all clauses and the procedure's final result. Copy its scope fingerprint "
            "as coverage_fingerprint in the answer when present. A first-step question does not "
            "cover an "
            "end-to-end procedure or recovering its result. Do not narrow the requirements "
            "to fit the draft. Use the answer template, replacing pass|fail with your verdict "
            "and giving reasons for a failure. Keep every copied fingerprint."
        ),
    }
