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
from tum_mcp.course.project.models import Key
from tum_mcp.course.project.store import Write, apply, confined, private_name, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

ConceptKind = Literal["definition", "fact", "rule", "procedure", "algorithm", "model", "comparison"]
STEPPED = "a walkthrough, a stepped diagram, a derivation walkthrough or a code walkthrough"


class Concept(Frozen):
    name: Label
    kind: ConceptKind
    # The worked case that shows the idea: an example, an instance, a counterexample.
    instance: Text
    outcomes: tuple[Key, ...] = ()
    blocks: tuple[Key, ...] = ()
    # Why the kind's default representation does not fit this concept.
    skip: Text | None = None


class Part(Frozen):
    part: Annotated[str, Field(min_length=1, max_length=20)]
    answer: Text
    method: Text


class Approval(Frozen):
    fingerprint: str
    verdict: Literal["pass", "fail"]
    reasons: tuple[Text, ...] = ()
    provenance: Literal["fresh", "same"]


class Plan(Frozen):
    item: Annotated[str, Field(min_length=1, max_length=200)]
    outcomes: tuple[Key, ...] = ()
    concepts: tuple[Concept, ...] = Field(default=(), max_length=30)
    parts: tuple[Part, ...] = Field(default=(), max_length=30)
    # The cases of an exam pattern, or the notes and highlights of a lecture.
    cases: tuple[Text, ...] = Field(default=(), max_length=20)
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
        if concept.kind == "definition" and all(b.get("kind") == "definition" for b in shown):
            problems.append(
                f"{concept.name}: a definition is shown with an example or case; name the "
                "block that shows it in the concept's `blocks`"
            )
    if plan.parts and (declared := value.get("parts")) is not None:
        planned = [part.part for part in plan.parts]
        if planned != list(declared):
            problems.append(f"parts {planned} do not match the exercise's parts {declared}")
    return problems


def gate_status(plan: Plan) -> str:
    """approved, rejected, provisional (only the author read it), changed or unchecked."""
    if plan.gate is None:
        return "unchecked"
    if plan.gate.fingerprint != plan.fingerprint():
        return "changed"
    if plan.gate.verdict == "fail":
        return "rejected"
    return "approved" if plan.gate.provenance == "fresh" else "provisional"


def record_gate(root: Path, answers: list[dict], provenance: Literal["fresh", "same"]) -> dict:
    """Save a checker's plan verdicts; each applies to the plan as it was read."""
    writes: list[Write] = []
    recorded: list[str] = []
    for answer in answers:
        item = str(answer.get("item", ""))
        plan = read_plan(root, item)
        if plan is None:
            raise CampusError(Code.ACTION_REQUIRED, f"No plan for {item}.")
        if answer.get("fingerprint") != plan.fingerprint():
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item} changed since it was read.")
        verdict = answer.get("verdict")
        reasons = tuple(str(reason) for reason in answer.get("reasons", []))
        if verdict not in {"pass", "fail"} or (verdict == "fail" and not reasons):
            raise CampusError(Code.ACTION_REQUIRED, f"Plan {item}: pass, or fail with the reasons.")
        gate = Approval(
            fingerprint=plan.fingerprint(), verdict=verdict, reasons=reasons, provenance=provenance
        )
        name = private_name(root, f"plans/{item}.json")
        body = json.dumps(plan.model_copy(update={"gate": gate}).model_dump(mode="json"), indent=2)
        writes.append(Write(name, read_bytes(confined(root, name)), body.encode()))
        recorded.append(item)
    apply(root, tuple(writes))
    return {"recorded": recorded}


def plan_packet(root: Path) -> dict[str, JsonValue]:
    """The plans not yet approved, for one fresh checker to read before anything is written."""
    waiting = [plan for plan in plans(root) if gate_status(plan) != "approved"]
    return {
        "plans": [
            {**plan.model_dump(mode="json", exclude={"gate"}), "fingerprint": plan.fingerprint()}
            for plan in waiting
        ],
        "ask": (
            "For each plan: does every concept have a worked instance that shows it (a concrete "
            "case, not the concept restated), does each "
            "kind get a fitting representation (or a real reason to skip it), does the order "
            "build each idea before it is used, and does it cover its outcomes? Answer "
            '{"items": [{"item", "fingerprint", "verdict": "pass"|"fail", "reasons": []}]}.'
        ),
    }
