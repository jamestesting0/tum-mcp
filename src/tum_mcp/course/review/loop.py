"""The review loop: a fixed scope, rounds of fresh checking, a computed gate and a scorecard.

Round 1 asks every applicable check of every item; later rounds ask only what changed, the
fixes to verify and the dependents a change reaches, so each round costs less than the last.
"""

import datetime
import json
from collections import Counter
from dataclasses import dataclass, field, replace
from importlib.resources import files
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.app.browser_evidence import current_sheets
from tum_mcp.course.checks.plans import plan_problems, read_plan
from tum_mcp.course.checks.preparation import PreparedScope, Readiness, assess
from tum_mcp.course.project.store import (
    Write,
    apply,
    confined,
    load_state,
    private_name,
    private_path,
    read_bytes,
)
from tum_mcp.course.review import registry
from tum_mcp.course.review.items import ReviewItem, collect, course_item, digest, resolve_item
from tum_mcp.course.review.ledger import (
    LIVE,
    ClosestCall,
    Finding,
    ItemRecord,
    RoundEntry,
    Ruling,
    Verdict,
    read_record,
    record_write,
)
from tum_mcp.course.review.models import (
    COURSE_WIDE_FLAGS,
    INVARIANT_FLAGS,
    RULED_FLAGS,
    VisualReview,
    _flagged_items,
    quoted,
)
from tum_mcp.course.sources.digests import definition_flags
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

DEFAULT_ROUNDS: Final = 1
PACKET_CHARS = 60_000
# One checker reply must hold a quoted verdict per check: trial checkers completed packets of
# up to about 100 short verdicts and gave up on 100 to 312 long ones.
PACKET_VERDICTS = 60
GATED = ("correctness", "coverage")


class RoundLog(Frozen):
    round: int = Field(ge=1)
    started: datetime.datetime
    closed: datetime.datetime | None = None
    packets: tuple[str, ...] = ()
    answered: tuple[str, ...] | None = Field(default=None, exclude_if=lambda value: value is None)
    opened: int = Field(default=0, ge=0)
    resolved: int = Field(default=0, ge=0)
    gate: bool | None = None
    verified: bool = False

    @property
    def pending_packets(self) -> tuple[str, ...]:
        if self.answered is None:
            return ()
        return tuple(packet for packet in self.packets if packet not in self.answered)


class LoopState(Frozen):
    schema_version: Literal[1] = 1
    budget: int = Field(ge=1, le=20)
    scope: tuple[str, ...] = Field(max_length=5000)
    status: Literal["running", "passed", "budget_spent"] = "running"
    rounds: tuple[RoundLog, ...] = ()
    preparation: PreparedScope | None = Field(default=None, exclude_if=lambda value: value is None)
    batch: PreparedScope | None = Field(default=None, exclude_if=lambda value: value is None)
    batch_contract: str | None = Field(default=None, exclude_if=lambda value: value is None)
    batch_sources: tuple[str, ...] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    structural_repairs: tuple[dict[str, JsonValue], ...] = Field(
        default=(), exclude_if=lambda value: not value
    )

    @property
    def round(self) -> int:
        return self.rounds[-1].round if self.rounds else 0


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _state_name() -> str:
    return private_name(Path("."), "loop.json")


def read_state(root: Path) -> LoopState | None:
    body = read_bytes(confined(root, _state_name()))
    if body is None:
        return None
    try:
        return LoopState.model_validate_json(body)
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "The review loop state needs review.") from None


def _state_write(root: Path, state: LoopState) -> Write:
    name = _state_name()
    return Write(name, read_bytes(confined(root, name)), state.model_dump_json(indent=2).encode())


@dataclass
class Context:
    root: Path
    items: dict[str, ReviewItem]
    flags: list[dict[str, JsonValue]]
    visuals: dict[str, list[str]]
    media_passed: bool = True
    media: dict[str, JsonValue] = field(default_factory=dict)
    records: dict[str, ItemRecord] = field(default_factory=dict)
    flags_by_item: dict[str, list[dict[str, JsonValue]]] = field(default_factory=dict)
    answer_keys: list[dict[str, JsonValue]] = field(default_factory=list)
    preparation: Readiness | None = None

    def record(self, key: str) -> ItemRecord:
        if key not in self.records:
            self.records[key] = read_record(self.root, key)
        return self.records[key]


def load(root: Path, *, answer_item: str | None = None) -> Context:
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.app.visuals import visual_ids
    from tum_mcp.course.checks.answers import verify
    from tum_mcp.course.checks.report import citation_flags, quality_flags
    from tum_mcp.course.checks.structure import course_map, forward_terms
    from tum_mcp.course.content.exam_data import (
        exam_item_flags,
        meta_flags,
        practice_flags,
        read_exam,
        retrieval_flags,
        sheet_flags,
    )
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.content.store import present
    from tum_mcp.course.lecture.data import read_lectures
    from tum_mcp.course.ledger.coverage import read_ledger
    from tum_mcp.course.ledger.coverage import sheet_flags as coverage_flags
    from tum_mcp.course.media.inventory import discover
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review.media import media_report, read_media_reviews

    root = root.expanduser().resolve()
    state = load_state(root)
    content = read_content(root) if present(root, "study") else None
    exercises = read_exercises(root)
    exam = read_exam(root)
    lectures = read_lectures(root)
    ledger = read_ledger(root)
    items = collect(
        root, content=content, exercises=exercises, exam=exam, lectures=lectures, ledger=ledger
    )
    from tum_mcp.course.memory.report import knowledge_revision

    media = discover(root, state, content)
    links: list[dict[str, JsonValue]] = []
    if items:
        semantics = knowledge_revision(root)
        structure = course_map(
            content,
            exercises,
            exam,
            lectures,
            ledger=ledger,
            knowledge_revision=semantics,
            media=media.structure,
        )
        items["course"] = course_item(structure, str(structure["revision"]), semantics)
        # Every exercise, cheatsheet entry, note and unit links each existing workspace or
        # records why none fits; an open decision holds that item's gate.
        from tum_mcp.course.checks.links import undecided

        links = [
            {
                "item": pair.item,
                "flag": "undecided_link",
                "detail": f"No {pair.target} link and no recorded reason; run tum-mcp study "
                "links to see candidates, then link it or record why none fits.",
            }
            for pair in undecided(root, content, exercises, exam, lectures)
        ]
    flags = [
        *quality_flags(content, exercises),
        *links,
        *(forward_terms(content) if content else ()),
        *sheet_flags(exam),
        *exam_item_flags(exam),
        *meta_flags(exam),
        *practice_flags(exam),
        *retrieval_flags(exam, content),
        *citation_flags(
            root,
            state,
            {
                **{
                    unit.key: unit.model_dump(mode="json")
                    for unit in (content.units if content else ())
                },
                **{
                    exercise.key: exercise.model_dump(mode="json")
                    for group in (exercises.sets if exercises else ())
                    for exercise in group.exercises
                },
                **{
                    f"exam/pattern/{pattern.key}": pattern.model_dump(mode="json")
                    for pattern in (exam.patterns if exam else ())
                },
                **{
                    f"concept:{concept.key}": concept.model_dump(mode="json")
                    for concept in (exam.concepts if exam else ())
                },
            },
        ),
        *coverage_flags(state, ledger, exam),
        *definition_flags(root, state, content, exam),
        *(
            {
                "item": "course",
                "flag": "unreplayable_paper",
                "detail": f"Past paper {variant.key} of {sitting.key} has no stored "
                "statement and solution, so students cannot practise it.",
            }
            for sitting in (exam.sittings if exam else ())
            for variant in sitting.variants
            if not variant.replayable
        ),
    ]
    # An answer key that disagrees with its item is a correctness defect the gate holds on.
    answer_keys = verify(
        root, items, resolve_item(items, answer_item) if answer_item is not None else None
    )
    flags += [
        {"item": result["item"], "flag": "answer_key", "detail": "; ".join(result["problems"])}
        for result in answer_keys
        if not result["passed"]
    ]
    context = Context(root, items, flags, visual_ids(content, exercises), answer_keys=answer_keys)
    for flag in flags:
        source = str(flag["item"])
        targets = (
            [source]
            if source == "course" or source in items
            else _flagged_items(source, content, exercises)
        )
        for target in targets:
            context.flags_by_item.setdefault(target, []).append(flag)
    context.media = media_report(root, media, read_media_reviews(root))
    context.media_passed = bool(context.media["passed"])
    return context


def covered(item: ReviewItem, covers: tuple[str, ...], check: str = "") -> str:
    blocks = item.blocks if "*" in covers else {block: item.blocks.get(block) for block in covers}
    if item.annotations and check.startswith(("clarity.", "correctness.")):
        blocks = blocks | {"@annotations": item.blocks["@annotations"]}
    if item.preparation and (check.startswith("coverage.") or check == "correctness.source_match"):
        return digest([blocks, item.preparation])
    return digest(blocks)


def packet_fingerprint(item: ReviewItem) -> str:
    return digest([item.blocks, item.preparation]) if item.preparation else digest(item.blocks)


def is_current(verdict: Verdict | None, check: registry.Check, item: ReviewItem) -> bool:
    return (
        verdict is not None
        and verdict.version == check.version
        and all(block == "*" or block in item.blocks for block in verdict.covers)
        and verdict.fingerprint == covered(item, verdict.covers, check.id)
    )


def _decided(context: Context, key: str, check: registry.Check) -> tuple[bool, str]:
    hits = [flag for flag in context.flags_by_item.get(key, []) if flag["flag"] == check.decided_by]
    return (not hits, "; ".join(str(flag["detail"]) for flag in hits[:3]))


def _visuals_current(context: Context, key: str, record: ItemRecord) -> bool:
    expected = context.visuals.get(key, [])
    reviewed = {visual.visual for visual in record.visuals}
    return not expected or (
        set(expected) <= reviewed
        and record.visuals_fingerprint == digest(context.items[key].blocks)
    )


def ruled_flags(context: Context, key: str) -> dict[str, dict[str, JsonValue]]:
    """The item's advisory flags that need a checker's ruling, keyed `flag@where`."""
    return {
        f"{flag['flag']}@{flag['item']}": flag
        for flag in context.flags_by_item.get(key, [])
        if str(flag["flag"]) in RULED_FLAGS
    }


def _ruling_current(record: ItemRecord, flag_key: str, item: ReviewItem) -> bool:
    ruling = record.rulings.get(flag_key)
    return ruling is not None and ruling.fingerprint == digest(item.blocks)


def item_tasks(context: Context, key: str) -> dict[str, JsonValue]:
    """What one item still needs: checks without a current verdict, fixes to verify, visuals
    and the advisory flags without a current ruling."""
    item, record = context.items[key], context.record(key)
    needs = [
        check.id
        for check in registry.judged(item.profile)
        if not is_current(record.checks.get(check.id), check, item)
        or record.checks[check.id].verdict == "uncertain"
    ]
    verify = [finding.id for finding in record.findings if finding.status == "fixed"]
    visuals = [] if _visuals_current(context, key, record) else list(context.visuals.get(key, []))
    rule = [k for k in ruled_flags(context, key) if not _ruling_current(record, k, item)]
    return {"needs": needs, "verify": verify, "visuals": visuals, "rule": rule}


def _bind_preparation(context: Context, state: LoopState) -> Readiness | None:
    binding = state.batch or state.preparation
    if binding is None:
        return None
    if state.batch:
        from tum_mcp.course.checks.batch import assess_batch

        reading = assess_batch(context.root, binding.identifier, context)
    else:
        reading = assess(context.root, binding.identifier, context)
    if reading.scope != binding or set(reading.items) != set(state.scope):
        reading = reading.model_copy(
            update={
                "problems": (
                    *reading.problems,
                    "Prepared review scope changed. Record a new scope.",
                ),
            }
        )
    context.preparation = reading
    for key, fingerprint in reading.fingerprints.items():
        context.items[key] = replace(context.items[key], preparation=fingerprint)
    return reading


def _require_ready(readiness: Readiness) -> None:
    if not readiness.ready:
        problems = " ".join(readiness.problems[:5])
        raise CampusError(Code.ACTION_REQUIRED, f"Preparation is not ready. {problems}")


def start(
    root: Path,
    budget: int = DEFAULT_ROUNDS,
    workspaces: tuple[str, ...] = (),
    *,
    preparation: str | None = None,
    batch: str | None = None,
    ad_hoc: bool = False,
) -> LoopState:
    context = load(root)
    existing = read_state(context.root)
    if batch is None and not ad_hoc and any(private_path(context.root, "batches").glob("*.json")):
        raise CampusError(
            Code.ACTION_REQUIRED,
            "This project has a declared batch. Complete it and use --batch ID, "
            "or choose --ad-hoc for an explicitly partial review.",
        )
    if sum((bool(preparation), bool(batch), bool(workspaces))) > 1:
        raise CampusError(Code.ACTION_REQUIRED, "Choose a batch, preparation or workspace filters.")
    binding = (existing.batch or existing.preparation) if existing else None
    if existing and binding and existing.status == "running":
        if (batch if existing.batch else preparation) == binding.identifier:
            if reading := _bind_preparation(context, existing):
                _require_ready(reading)
                return existing
        raise CampusError(
            Code.ACTION_REQUIRED, "Finish the open prepared review before starting another."
        )
    if batch:
        from tum_mcp.course.checks.batch import assess_batch
        from tum_mcp.course.review.repair_scope import contract

        readiness = assess_batch(context.root, batch, context)
        _require_ready(readiness)
        state = LoopState(
            budget=budget,
            scope=tuple(readiness.items),
            batch=readiness.scope,
            batch_contract=contract(context.root, batch),
            batch_sources=tuple(entry.resource.key for entry in load_state(context.root).resources),
        )
        apply(context.root, (_state_write(context.root, state),))
        return state
    if preparation:
        readiness = assess(context.root, preparation, context)
        _require_ready(readiness)
        state = LoopState(budget=budget, scope=tuple(readiness.items), preparation=readiness.scope)
        apply(context.root, (_state_write(context.root, state),))
        return state
    prefixes = {
        "study": ("study/",),
        "exercises": ("exercises/",),
        "exam": ("exam/",),
        "lectures": ("lecture/",),
        "course": ("course",),
    }
    wanted = workspaces or tuple(prefixes)
    scope = tuple(
        key
        for key in context.items
        if any(key.startswith(prefixes[name]) for name in wanted if name in prefixes)
    )
    if not scope:
        raise CampusError(Code.ACTION_REQUIRED, "Nothing to review: prepare content first.")
    state = LoopState(budget=budget, scope=scope)
    if ad_hoc:
        from tum_mcp.course.checks.batch import assess_batch
        from tum_mcp.course.review.repair_scope import contract

        matches = [
            reading
            for path in sorted(private_path(context.root, "batches").glob("*.json"))
            if (reading := assess_batch(context.root, path.stem, context)).ready
            and set(reading.items) == set(scope)
        ]
        if len(matches) == 1:
            reading = matches[0]
            state = state.model_copy(
                update={
                    "batch": reading.scope,
                    "batch_contract": contract(context.root, reading.identifier),
                    "batch_sources": tuple(
                        entry.resource.key for entry in load_state(context.root).resources
                    ),
                }
            )
    apply(context.root, (_state_write(context.root, state),))
    return state


CONCEPT_CHECK = "intuition.concepts_instanced"


def _concepts(root: Path, key: str) -> list[dict[str, JsonValue]]:
    """The item's planned concepts, so a checker answers concept by concept."""
    plan = read_plan(root, key)
    return [
        {"name": c.name, "kind": c.kind, "instance": c.instance, "blocks": list(c.blocks)}
        for c in (plan.concepts if plan else ())
    ]


def _passages(item: ReviewItem) -> list[dict[str, str]]:
    return [{"path": path, "text": text} for path, text in item.passages()]


def _snapshot_name(key: str) -> str:
    return private_name(Path("."), f"review/blocks/{key}.json")


def _changed(root: Path, item: ReviewItem) -> list[str]:
    body = read_bytes(confined(root, _snapshot_name(item.key)))
    if body is None:
        return []
    seen = json.loads(body)
    return sorted(
        block
        for block in seen.keys() | item.blocks.keys()
        if seen.get(block) != item.blocks.get(block)
    )


def _cited(value: object, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        for source in value.get("sources", ()) if isinstance(value.get("sources"), list) else ():
            found.add(source if isinstance(source, str) else str(source.get("key")))
        for child in value.values():
            _cited(child, found)
    elif isinstance(value, list):
        for child in value:
            _cited(child, found)
    return found


def _digests(root: Path, value: dict) -> list[dict[str, JsonValue]]:
    """The digests of the sources an item cites: what the checker compares it against."""
    from tum_mcp.course.sources.digests import read_digest

    return [
        found.model_dump(mode="json", exclude={"sha256", "figures"})
        for key in sorted(_cited(value, set()))
        if (found := read_digest(root, key)) is not None
    ]


def _page_evidence(root: Path, value: dict) -> list[dict[str, JsonValue]]:
    from tum_mcp.course.sources.text import page_images

    cited: dict[str, set[int]] = {}

    def visit(entry: object) -> None:
        if isinstance(entry, dict):
            pages = entry.get("pages")
            sources = entry.get("sources")
            if isinstance(pages, str) and isinstance(sources, list):
                start, _, end = pages.partition("-")
                if start.isdigit() and (not end or end.isdigit()):
                    for source in sources:
                        key = source if isinstance(source, str) else source.get("key")
                        if isinstance(key, str):
                            cited.setdefault(key, set()).update(
                                range(int(start), int(end or start) + 1)
                            )
            for child in entry.values():
                visit(child)
        elif isinstance(entry, list):
            for child in entry:
                visit(child)

    visit(value)
    results = []
    for key, pages in cited.items():
        cached: dict[str, str] = {}
        failed: dict[str, str] = {}
        ordered = sorted(pages)
        for offset in range(0, len(ordered), 12):
            batch = ordered[offset : offset + 12]
            try:
                cached.update({str(n): path for n, path in page_images(root, key, batch).items()})
            except (CampusError, OSError, ValueError) as error:
                for number in batch:
                    try:
                        cached.update(
                            {str(n): path for n, path in page_images(root, key, [number]).items()}
                        )
                    except (CampusError, OSError, ValueError) as page_error:
                        failed[str(number)] = str(page_error or error)
        results.append({"source": key, "cached": cached, "failed": failed})
    return results


def _study_context(context: Context, item: ReviewItem) -> dict[str, JsonValue]:
    if item.profile != "study-unit":
        return {}
    outline = [
        {"title": block["title"], "level": block["level"]}
        for block in item.value.get("blocks", [])
        if block.get("title")
    ]
    earlier = []
    for key, previous in context.items.items():
        if key == item.key:
            break
        if previous.profile == "study-unit":
            earlier.extend(
                block["term"]
                for block in previous.value.get("blocks", [])
                if block.get("kind") == "definition"
            )
    return {"outline": outline, "earlier_terms": earlier}


def next_round(root: Path) -> dict[str, JsonValue]:
    """Open the next round and write its packets: one profile each, small enough to read."""
    context = load(root)
    state = read_state(context.root)
    if state is None:
        raise CampusError(Code.ACTION_REQUIRED, "Start the loop first: tum-mcp review start.")
    if state.status != "running":
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"The loop has {state.status.replace('_', ' ')}; start a new loop to continue.",
        )
    if state.rounds and state.rounds[-1].closed is None:
        raise CampusError(Code.ACTION_REQUIRED, "Close the current round first.")
    if state.round >= state.budget:
        raise CampusError(Code.ACTION_REQUIRED, "The round budget is spent; extend it to go on.")
    _bind_preparation(context, state)
    if context.preparation:
        _require_ready(context.preparation)
    number = state.round + 1
    packets, writes = _packets(context, state, number, verify=False)
    log = RoundLog(round=number, started=_now(), packets=tuple(packets), answered=())
    writes.append(
        _state_write(context.root, state.model_copy(update={"rounds": (*state.rounds, log)}))
    )
    apply(context.root, tuple(writes))
    return _packet_result(number, state.budget, packets)


def verify_round(root: Path) -> dict[str, JsonValue]:
    """Refresh stale verdicts and verify fixes within the current round."""
    context = load(root)
    state = read_state(context.root)
    if state is None or not state.rounds or state.rounds[-1].closed is not None:
        raise CampusError(Code.ACTION_REQUIRED, "Open a round with tum-mcp review next first.")
    log = state.rounds[-1]
    if log.verified:
        raise CampusError(Code.ACTION_REQUIRED, "This round already has a verify pass.")
    if log.answered is None or log.pending_packets:
        raise CampusError(Code.ACTION_REQUIRED, "Record all original packets before verification.")
    _bind_preparation(context, state)
    if context.preparation:
        _require_ready(context.preparation)
    packets, writes = _packets(context, state, state.round, verify=True)
    log = log.model_copy(update={"packets": (*log.packets, *packets), "verified": True})
    writes.append(
        _state_write(context.root, state.model_copy(update={"rounds": (*state.rounds[:-1], log)}))
    )
    apply(context.root, tuple(writes))
    return _packet_result(state.round, state.budget, packets)


def _packets(
    context: Context, state: LoopState, number: int, *, verify: bool
) -> tuple[list[str], list[Write]]:
    sheets = current_sheets(context.root) if context.visuals else {}
    groups: dict[str, list[dict[str, JsonValue]]] = {}
    for key in state.scope:
        if key not in context.items:
            continue
        tasks = item_tasks(context, key)
        if not (tasks["needs"] or tasks["verify"] or tasks["visuals"] or tasks["rule"]):
            continue
        item, record = context.items[key], context.record(key)
        groups.setdefault(item.profile, []).append(
            {
                "item": key,
                "title": item.title,
                "fingerprint": packet_fingerprint(item),
                **(
                    {
                        "preparation": {
                            "mode": context.preparation.mode,
                            "cutoff": context.preparation.cutoff,
                            "demands": context.preparation.items[key],
                            "item_order": list(state.scope),
                        }
                    }
                    if context.preparation
                    else {}
                ),
                **tasks,
                **({"visual_sheets": sheets[key]} if tasks["visuals"] and key in sheets else {}),
                "verify": [
                    finding.model_dump(mode="json", exclude={"blocks_at_open"})
                    for finding in record.findings
                    if finding.id in tasks["verify"]
                ],
                "rejected": [
                    {"check": f.check, "quote": f.quote, "reason": f.reason}
                    for f in record.findings
                    if f.status == "rejected"
                ],
                "decided": {
                    check.id: detail
                    for check in registry.for_profile(item.profile)
                    if check.decided_by
                    for passed, detail in [_decided(context, key, check)]
                    if not passed
                },
                "report": [
                    {"flag": flag["flag"], "detail": flag["detail"]}
                    | (
                        {
                            "key": f"{flag['flag']}@{flag['item']}",
                            "needs_ruling": True,
                            "bears_on": (
                                "correctness.sheet_true"
                                if key == "exam/sheet" and flag["flag"] == "definition_refined"
                                else RULED_FLAGS[str(flag["flag"])]
                            ),
                        }
                        if str(flag["flag"]) in RULED_FLAGS
                        else {}
                    )
                    for flag in context.flags_by_item.get(key, [])
                ],
                "changed": _changed(context.root, item),
                "answer_key": next(
                    (entry for entry in context.answer_keys if entry["item"] == key), None
                ),
                "digests": _digests(context.root, item.value),
                "source_pages": _page_evidence(context.root, item.value),
                **_study_context(context, item),
                "concepts": _concepts(context.root, key),
                "blocks": sorted(item.blocks),
                "passages": _passages(item),
                **({"evidence": item.evidence} if item.evidence else {}),
                **({"annotations": item.annotations} if item.annotations else {}),
            }
        )
    packets: list[str] = []
    writes: list[Write] = []
    for profile, entries in groups.items():
        batch: list[dict[str, JsonValue]] = []
        size = verdicts = 0
        batches: list[list[dict[str, JsonValue]]] = []
        for entry in entries:
            length = len(json.dumps(entry["passages"]))
            asked = sum(len(entry[task]) for task in ("needs", "verify", "visuals", "rule"))
            if batch and (size + length > PACKET_CHARS or verdicts + asked > PACKET_VERDICTS):
                batches.append(batch)
                batch, size, verdicts = [], 0, 0
            batch.append(entry)
            size += length
            verdicts += asked
        if batch:
            batches.append(batch)
        for index, items in enumerate(batches, 1):
            packet_id = f"r{number}{'v' if verify else ''}-{profile}-{index}"
            packet = {
                "id": packet_id,
                "round": number,
                "profile": profile,
                "guidance": files("tum_mcp.bundled")
                .joinpath(
                    "skills/review-course/references/"
                    + ("course.md" if profile == "course" else "profiles.md")
                )
                .read_text(encoding="utf-8"),
                "checks": [check.brief() for check in registry.judged(profile)],
                "items": items,
                **(
                    {"scope_dispositions": list(context.preparation.dispositions)}
                    if context.preparation
                    else {}
                ),
                "answer": ANSWER_FORMAT,
            }
            name = private_name(Path("."), f"review/packets/{packet_id}.json")
            writes.append(
                Write(
                    name,
                    read_bytes(confined(context.root, name)),
                    json.dumps(packet, indent=2, ensure_ascii=False).encode(),
                )
            )
            packets.append(packet_id)
    return packets, writes


def _packet_result(number: int, budget: int, packets: list[str]) -> dict[str, JsonValue]:
    return {
        "round": number,
        "budget": budget,
        "packets": [
            {
                "packet": packet_id,
                "path": private_name(Path("."), f"review/packets/{packet_id}.json"),
            }
            for packet_id in packets
        ],
        "next": "Give each packet to a fresh checker, then tum-mcp review record."
        if packets
        else "Nothing left to check: tum-mcp review close-round.",
    }


ANSWER_FORMAT: dict[str, JsonValue] = {
    "packet": "the packet id",
    "items": [
        {
            "item": "the item key",
            "checks": {
                "<check id>": {
                    "verdict": "pass | fail | uncertain",
                    "method": "how you judged it, in a few words",
                    "quote": "pass and uncertain: the passage nearest to failing, word for word",
                    "location": "the passage path from the packet",
                    "reason": "why it passes, or what is uncertain",
                    "evidence": "default_fail checks: the script output, map or steps that pass it",
                    "covers": ["block scope only: the blocks you judged, else omit"],
                }
            },
            "findings": [
                {
                    "check": "a check id of this packet",
                    "also": ["other checks asked for this item that this defect also fails"],
                    "quote": "word for word from the passage at location",
                    "location": "the passage path",
                    "why": "what the student meets and why it fails",
                    "fix": "the change that would pass the check",
                    "score": "1 when it blocks learning, else 2",
                }
            ],
            "verify": [
                {
                    "finding": "F3",
                    "resolved": True,
                    "reason": "what you saw",
                    "quote": "resolved: the rewritten passage, word for word; it must read well "
                    "on its own, not only remove the finding",
                }
            ],
            "flags": [
                {
                    "key": "each report flag with needs_ruling, by its key",
                    "ruling": "finding (one of your findings in this answer is about it) "
                    "| not_applicable",
                    "reason": "why it does not apply here, or which finding covers it",
                }
            ],
            "visuals": [
                {
                    "visual": "block:3",
                    "scores": {
                        "fidelity": 3,
                        "form": 3,
                        "layout": 3,
                        "legibility": 3,
                        "focus": 3,
                        "convention": 3,
                    },
                    "note": "When any score is below 3, name the specific visual defect here.",
                }
            ],
        }
    ],
}


def _at(passages: list[tuple[str, str]], location: str) -> list[tuple[str, str]]:
    return [(path, text) for path, text in passages if path == location]


def _block(item: ReviewItem, location: str) -> str:
    head = location.split(".", 1)[0]
    if "[" in head:
        name, index = head.split("[", 1)
        index = index.rstrip("]")
        element = item.value.get(name, [])
        if index.isdigit() and int(index) < len(element):
            value = element[int(index)]
            label = value.get("key") if isinstance(value, dict) else None
            block = f"{name}:{label}" if isinstance(label, str) else f"{name}:{index}"
            if block in item.blocks:
                return block
            return f"{name}:{index}"
    return head


class AnswerError(CampusError):
    problems: list[dict[str, str]]

    def __init__(self, problems: list[dict[str, str]]) -> None:
        self.problems = problems
        super().__init__(
            Code.INVALID_RESPONSE,
            "Answers need fixing: " + " ".join(problem["message"] for problem in problems),
        )


def record(
    root: Path,
    answers: dict,
    provenance: Literal["fresh", "same", "provisional"],
) -> dict[str, JsonValue]:
    """Validate a checker's answers against its packet and the current content, then save."""
    context = load(root)
    state = read_state(context.root)
    if state is None or not state.rounds or state.rounds[-1].closed is not None:
        raise CampusError(Code.ACTION_REQUIRED, "Open a round with tum-mcp review next first.")
    _bind_preparation(context, state)
    if context.preparation:
        _require_ready(context.preparation)
    packet_id = str(answers.get("packet", ""))
    body = read_bytes(
        confined(context.root, private_name(Path("."), f"review/packets/{packet_id}.json"))
    )
    if body is None or packet_id not in state.rounds[-1].packets:
        raise CampusError(Code.ACTION_REQUIRED, f"No packet {packet_id} in this round.")
    packet = json.loads(body)
    number = state.rounds[-1].round
    asked = {entry["item"]: entry for entry in packet["items"]}
    problems: list[dict[str, str]] = []
    opened = resolved = 0
    for answer in answers.get("items", []):
        key = answer.get("item")
        if key not in asked:
            problems.append(
                {
                    "item": str(key),
                    "kind": "item",
                    "id": str(key),
                    "message": f"{key}: not in packet {packet_id}.",
                }
            )
            continue
        item = context.items.get(key)
        if item is None or packet_fingerprint(item) != asked[key]["fingerprint"]:
            problems.append(
                {
                    "item": key,
                    "kind": "item",
                    "id": key,
                    "message": f"{key}: the content changed since the packet; take a new round.",
                }
            )
            continue
        recorded = _record_item(context, item, asked[key], answer, number, provenance, problems)
        opened += recorded[0]
        resolved += recorded[1]
    missing = sorted(set(asked) - {answer.get("item") for answer in answers.get("items", [])})
    problems.extend(
        {"item": key, "kind": "item", "id": key, "message": f"{key}: not answered."}
        for key in missing
    )
    if problems:
        name = private_name(Path("."), f"review/packets/{packet_id}.problems.json")
        previous = read_bytes(confined(context.root, name))
        history = json.loads(previous) if previous else []
        apply(
            context.root,
            (Write(name, previous, json.dumps([*history, problems], indent=2).encode()),),
        )
        raise AnswerError(problems)
    log = state.rounds[-1].model_copy(
        update={
            "opened": state.rounds[-1].opened + opened,
            "resolved": state.rounds[-1].resolved + resolved,
            "answered": tuple(dict.fromkeys((*(state.rounds[-1].answered or ()), packet_id))),
        }
    )
    apply(
        context.root,
        (
            *(record_write(context.root, rec) for rec in context.records.values()),
            *(
                Write(
                    name,
                    read_bytes(confined(context.root, name)),
                    json.dumps(context.items[key].blocks, sort_keys=True).encode(),
                )
                for key in asked
                for name in (_snapshot_name(key),)
            ),
            _state_write(
                context.root, state.model_copy(update={"rounds": (*state.rounds[:-1], log)})
            ),
        ),
    )
    return {"recorded": sorted(asked), "opened": opened, "resolved": resolved}


def _record_item(
    context: Context,
    item: ReviewItem,
    asked: dict,
    answer: dict,
    number: int,
    provenance: str,
    problems: list[dict[str, str]],
) -> tuple[int, int]:
    key = item.key
    record = context.record(key)
    passages = item.passages()
    checks = {check.id: check for check in registry.judged(item.profile)}
    verdicts = dict(record.checks)
    findings = list(record.findings)
    next_id = 1 + max((int(f.id[1:]) for f in findings), default=0)
    candidates: list[Finding] = []

    def problem(kind: str, identifier: str, message: str) -> None:
        problems.append({"item": key, "kind": kind, "id": identifier, "message": message})

    for index, raw in enumerate(answer.get("findings", [])):
        check = checks.get(raw.get("check", ""))
        location = str(raw.get("location", ""))
        quote = str(raw.get("quote", ""))
        if check is None:
            problem(
                "finding", str(index), f"{key}: finding check {raw.get('check')} is not asked here."
            )
            continue
        also = raw.get("also", [])
        if (
            not isinstance(also, list)
            or any(not isinstance(link, str) for link in also)
            or any(link == check.id or link not in asked["needs"] for link in also)
            or any(answer.get("checks", {}).get(link, {}).get("verdict") != "fail" for link in also)
        ):
            problem(
                "finding",
                str(index),
                f"{key}: finding for {check.id} has invalid also checks {also}; "
                "each must be another asked check with a fail verdict.",
            )
            continue
        if not quoted(quote, _at(passages, location)):
            matches = [path for path, text in passages if quoted(quote, [(path, text)])]
            if len(matches) != 1:
                problem(
                    "finding",
                    str(index),
                    f"{key}: finding quote for {check.id} is not at {location}.",
                )
                continue
            location = matches[0]
        if not raw.get("why") or not raw.get("fix"):
            problem("finding", str(index), f"{key}: finding for {check.id} needs why and fix.")
            continue
        score = 1 if str(raw.get("score")) == "1" else 2
        duplicate = next(
            (
                finding
                for finding in candidates
                if (finding.location, finding.quote) == (location, quote)
            ),
            None,
        )
        if duplicate is not None:
            if check.id != duplicate.check and (
                check.id not in asked["needs"]
                or answer.get("checks", {}).get(check.id, {}).get("verdict") != "fail"
            ):
                problem(
                    "finding",
                    str(index),
                    f"{key}: merged check {check.id} must be asked and fail.",
                )
                continue
            linked = tuple(
                dict.fromkeys(
                    link for link in (*duplicate.also, check.id, *also) if link != duplicate.check
                )
            )
            candidates[candidates.index(duplicate)] = duplicate.model_copy(
                update={"also": linked, "score": min(duplicate.score, score)}
            )
            continue
        block = _block(item, location)
        previous = verdicts.get(check.id)
        candidates.append(
            Finding(
                id=f"F{next_id + len(candidates)}",
                check=check.id,
                also=tuple(dict.fromkeys(also)),
                quote=quote,
                location=location,
                why=raw["why"],
                fix=raw["fix"],
                score=score,
                opened=number,
                block=block,
                blocks_at_open=dict(item.blocks),
                late=previous is not None
                and previous.verdict == "pass"
                and is_current(previous, check, item),
            )
        )
    new: list[Finding] = []
    reported: list[Finding] = []
    for candidate in candidates:
        existing = next(
            (
                finding
                for finding in findings
                if finding.opened == number
                and finding.status != "verified"
                and (finding.check, finding.location, finding.quote)
                == (candidate.check, candidate.location, candidate.quote)
                and (finding.why, finding.fix, finding.score)
                == (candidate.why, candidate.fix, candidate.score)
                and set(finding.also) == set(candidate.also)
            ),
            None,
        )
        if existing is not None:
            reported.append(existing)
        else:
            new.append(candidate)
            reported.append(candidate)
    failed = {check_id for finding in reported for check_id in (finding.check, *finding.also)}
    missing = [
        check_id for check_id in asked["needs"] if answer.get("checks", {}).get(check_id) is None
    ]
    for check_id in missing:
        problem("check", check_id, f"{key}: missing verdict for {check_id}.")
    for check_id in asked["needs"]:
        check = checks[check_id]
        given = answer.get("checks", {}).get(check_id)
        if given is None:
            continue
        verdict = given.get("verdict")
        covers = tuple(given.get("covers") or ("*",)) if check.scope == "block" else ("*",)
        if any(block != "*" and block not in item.blocks for block in covers):
            problem("check", check_id, f"{key}: {check_id} covers unknown blocks.")
            continue
        closest = None
        if verdict == "fail" and check_id not in failed:
            problem("check", check_id, f"{key}: {check_id} fails but no finding names it.")
            continue
        if verdict in {"pass", "uncertain"}:
            location = str(given.get("location", ""))
            if not (
                given.get("reason") and quoted(str(given.get("quote", "")), _at(passages, location))
            ):
                problem(
                    "check",
                    check_id,
                    f"{key}: {check_id} needs a quote found at its location and a reason.",
                )
                continue
            closest = ClosestCall(quote=given["quote"], location=location, reason=given["reason"])
        if verdict == "pass" and check.default_fail and not given.get("evidence"):
            problem("check", check_id, f"{key}: {check_id} passes only with cited evidence.")
            continue
        if verdict == "pass" and check_id == CONCEPT_CHECK:
            evidence = str(given.get("evidence", "")).casefold()
            if skipped := [
                c["name"] for c in asked.get("concepts", []) if c["name"].casefold() not in evidence
            ]:
                problem(
                    "check",
                    check_id,
                    f"{key}: {check_id} names every planned concept with the block that shows "
                    f"it; missing {', '.join(skipped[:4])}.",
                )
                continue
        if verdict not in {"pass", "fail", "uncertain"}:
            problem(
                "check", check_id, f"{key}: {check_id} verdict must be pass, fail or uncertain."
            )
            continue
        verdicts[check_id] = Verdict(
            verdict=verdict,
            method=str(given.get("method") or "read"),
            round=number,
            provenance=provenance,
            fingerprint=covered(item, covers, check.id),
            covers=covers,
            version=check.version,
            finding_ids=tuple(
                finding.id
                for finding in reported
                if verdict == "fail" and check_id in (finding.check, *finding.also)
            ),
            closest=closest,
            evidence=given.get("evidence"),
        )
    resolved = 0
    verifying = {finding["id"] for finding in asked["verify"]}
    for check in verify_answers(answer):
        target = next((f for f in findings if f.id == check["finding"]), None)
        if target is None or target.id not in verifying:
            problem(
                "verify",
                str(check["finding"]),
                f"{key}: {check['finding']} was not asked to be verified.",
            )
            continue
        index = findings.index(target)
        if check.get("resolved") is True:
            # Verifying reads the new passage: a fix that removes the finding but reads badly
            # is not resolved.
            if not quoted(str(check.get("quote", "")), passages):
                problem(
                    "verify",
                    target.id,
                    f"{key}: {target.id} is resolved only with the rewritten passage quoted.",
                )
                continue
            contradicted = [
                check_id
                for check_id in (target.check, *target.also)
                if answer.get("checks", {}).get(check_id, {}).get("verdict") == "fail"
                and not any(
                    finding.id != target.id and check_id in (finding.check, *finding.also)
                    for finding in reported
                )
            ]
            if contradicted:
                problem(
                    "verify",
                    target.id,
                    f"{key}: {target.id} cannot be resolved while its checks fail: "
                    f"{', '.join(contradicted)}.",
                )
                continue
            findings[index] = target.model_copy(
                update={"status": "verified", "closed": number, "verified_provenance": provenance}
            )
            resolved += 1
        else:
            findings[index] = target.model_copy(
                update={"status": "reopened", "reopens": target.reopens + 1}
            )
    asked_verify = verifying - {item["finding"] for item in verify_answers(answer)}
    for finding in sorted(asked_verify):
        problem("verify", finding, f"{key}: {finding} was not verified.")
    rulings = dict(record.rulings)
    given_rulings = {
        str(entry.get("key")): entry for entry in answer.get("flags", []) if isinstance(entry, dict)
    }
    for flag_key in asked.get("rule", []):
        entry = given_rulings.get(flag_key)
        if entry is None:
            problem("flag", flag_key, f"{key}: flag {flag_key} needs a ruling.")
            continue
        ruling, reason = entry.get("ruling"), str(entry.get("reason") or "").strip()
        if ruling not in {"finding", "not_applicable"} or len(reason) < 15:
            problem(
                "flag",
                flag_key,
                f"{key}: flag {flag_key} is ruled finding or not_applicable, with why.",
            )
            continue
        bears_on = next(flag["bears_on"] for flag in asked["report"] if flag.get("key") == flag_key)
        if ruling == "finding" and not any(bears_on in (f.check, *f.also) for f in reported):
            problem(
                "flag",
                flag_key,
                f"{key}: flag {flag_key} is ruled a finding, but no finding names {bears_on}.",
            )
            continue
        rulings[flag_key] = Ruling(
            ruling=ruling,
            reason=reason,
            round=number,
            provenance=provenance,
            fingerprint=digest(item.blocks),
        )
    visuals = record.visuals
    fingerprint = record.visuals_fingerprint
    if asked["visuals"]:
        try:
            visuals = tuple(VisualReview.model_validate(v) for v in answer.get("visuals", []))
        except ValidationError as error:
            named = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg'].removeprefix('Value error, ')}"
                for e in error.errors(include_input=False)[:3]
            )
            for visual in answer.get("visuals", []):
                try:
                    VisualReview.model_validate(visual)
                except ValidationError:
                    problem(
                        "visual",
                        str(visual.get("visual", "")),
                        f"{key}: visual scores invalid ({named}).",
                    )
        else:
            if missing := set(asked["visuals"]) - {visual.visual for visual in visuals}:
                for visual in sorted(missing):
                    problem("visual", visual, f"{key}: visual not scored: {visual}.")
            fingerprint = digest(item.blocks)
    context.records[key] = record.model_copy(
        update={
            "checks": verdicts,
            "findings": (*findings, *new),
            "visuals": visuals,
            "visuals_fingerprint": fingerprint,
            "rulings": rulings,
        }
    )
    return len(new), resolved


def verify_answers(answer: dict) -> list[dict]:
    return [entry for entry in answer.get("verify", []) if isinstance(entry, dict)]


def _finding(context: Context, key: str, finding_id: str) -> tuple[ItemRecord, int, Finding]:
    if key not in context.items:
        raise CampusError(Code.ACTION_REQUIRED, f"No reviewed item {key}.")
    record = context.record(key)
    for index, finding in enumerate(record.findings):
        if finding.id == finding_id:
            return record, index, finding
    raise CampusError(Code.ACTION_REQUIRED, f"{key} has no finding {finding_id}.")


def change(
    root: Path,
    key: str,
    finding_id: str,
    action: Literal["fixed", "rejected", "kept"],
    *,
    reason: str | None = None,
    block: str | None = None,
) -> Finding:
    """Mark a finding fixed (only after its passage changed), rejected or kept, with reasons."""
    if action == "fixed":
        return fix_many(root, key, (finding_id,), block)[0]
    context = load(root)
    record, index, finding = _finding(context, key, finding_id)
    if finding.status not in LIVE:
        raise CampusError(Code.ACTION_REQUIRED, f"{finding_id} is {finding.status}, not open.")
    if not reason:
        raise CampusError(Code.ACTION_REQUIRED, "Say why with --reason.")
    updated = finding.model_copy(
        update={"status": action, **({"reason": reason} if reason else {})}
    )
    Finding.model_validate(updated.model_dump())
    findings = list(record.findings)
    findings[index] = updated
    apply(
        context.root,
        (record_write(context.root, record.model_copy(update={"findings": tuple(findings)})),),
    )
    return updated


def fix_many(root: Path, key: str, ids: tuple[str, ...], block: str | None = None) -> list[Finding]:
    context = load(root)
    selected = [_finding(context, key, finding_id) for finding_id in ids]
    if len(set(ids)) != len(ids):
        raise CampusError(Code.ACTION_REQUIRED, "Name each finding only once.")
    for _, _, finding in selected:
        if finding.status not in LIVE:
            raise CampusError(Code.ACTION_REQUIRED, f"{finding.id} is {finding.status}, not open.")
        target = block or finding.block
        if target not in context.items[key].blocks:
            raise CampusError(Code.ACTION_REQUIRED, f"{key} has no block {target}.")
        if context.items[key].blocks[target] == finding.blocks_at_open.get(target):
            raise CampusError(Code.ACTION_REQUIRED, f"{target} is unchanged since {finding.id}.")
    record = context.record(key)
    findings = list(record.findings)
    updated = []
    for _, index, finding in selected:
        result = finding.model_copy(update={"status": "fixed"})
        findings[index] = result
        updated.append(result)
    apply(
        context.root,
        (record_write(context.root, record.model_copy(update={"findings": tuple(findings)})),),
    )
    return updated


def resolve(
    root: Path, key: str, check_id: str, verdict: Literal["pass", "fail"], reason: str
) -> None:
    context = load(root)
    item = context.items.get(key)
    check = registry.checks().get(check_id)
    record = context.record(key) if item else None
    if item is None or check is None or record is None:
        raise CampusError(Code.ACTION_REQUIRED, f"No check {check_id} on {key}.")
    current = record.checks.get(check_id)
    if current is None or current.verdict != "uncertain":
        raise CampusError(Code.ACTION_REQUIRED, f"{check_id} on {key} is not uncertain.")
    decided = current.model_copy(
        update={"verdict": verdict, "provenance": "user", "method": f"user decision: {reason}"}
    )
    checks = dict(record.checks)
    checks[check_id] = decided
    apply(context.root, (record_write(context.root, record.model_copy(update={"checks": checks})),))


def item_gate(context: Context, key: str) -> list[str]:
    """Why one item does not pass yet; empty when it does."""
    item, record = context.items[key], context.record(key)
    profile = item.profile
    problems: list[str] = []
    dimensions = registry.dimensions(profile)
    scores = record.scores(dimensions)
    for check in registry.for_profile(profile):
        if check.decided_by:
            passed, detail = _decided(context, key, check)
            if not passed:
                problems.append(f"{check.id}: {detail}")
            continue
        verdict = record.checks.get(check.id)
        if not is_current(verdict, check, item):
            problems.append(f"{check.id}: no current verdict")
        elif verdict.verdict == "uncertain":
            problems.append(f"{check.id}: uncertain, needs your decision")
        else:
            if check.teaching and verdict.verdict != "pass":
                related = {finding.id: finding for finding in record.findings}
                if (
                    verdict.provenance == "user"
                    or not verdict.finding_ids
                    or any(
                        finding_id not in related
                        or check.id not in (related[finding_id].check, *related[finding_id].also)
                        or related[finding_id].status != "verified"
                        or related[finding_id].closed is None
                        or related[finding_id].closed < verdict.round
                        or related[finding_id].verified_provenance != "fresh"
                        for finding_id in verdict.finding_ids
                    )
                ):
                    problems.append(f"{check.id}: teaching check not passed")
            if check.default_fail and verdict.provenance not in {"fresh", "user", "code"}:
                problems.append(f"{check.id}: needs a fresh checker")
    for finding in record.findings:
        if finding.status in LIVE:
            problems.append(f"{finding.id} {finding.check}: {finding.status}")
    for name in GATED:
        if scores.get(name, 3) < 3:
            problems.append(f"{name} scores {scores[name]}")
    if any(score < 2 for score in scores.values()):
        problems.append("a dimension scores 1")
    for flag in context.flags_by_item.get(key, []):
        if str(flag["flag"]) in INVARIANT_FLAGS and str(flag["flag"]) not in COURSE_WIDE_FLAGS:
            problems.append(f"flag {flag['flag']}: {str(flag['detail'])[:120]}")
    if not _visuals_current(context, key, record):
        problems.append("visuals not scored for the current content")
    # The plan's links and kind defaults are code checks: a broken one holds the item.
    if (plan := read_plan(context.root, key)) is not None:
        problems.extend(f"plan: {p}" for p in plan_problems(plan, item.value, None))
    for flag_key in ruled_flags(context, key):
        ruling = record.rulings.get(flag_key)
        if not _ruling_current(record, flag_key, item):
            problems.append(f"flag {flag_key}: needs a checker's ruling")
        elif ruling.provenance not in {"fresh", "user", "code"}:
            problems.append(f"flag {flag_key}: ruled by the author; needs a fresh checker")
    return problems


def gate(context: Context, scope: tuple[str, ...]) -> dict[str, list[str]]:
    result = {key: item_gate(context, key) for key in scope if key in context.items}
    # Course-wide coverage (sources no requirement records yet) is not one item's defect: it
    # holds the gate and publishing apart from the items, so a scoped section can pass.
    course = sorted(
        {
            f"flag {flag['flag']}: {str(flag['detail'])[:120]}"
            for key in scope
            for flag in context.flags_by_item.get(key, [])
            if str(flag["flag"]) in COURSE_WIDE_FLAGS
        }
    )
    if course:
        result["course"] = course
    if context.preparation and context.preparation.problems:
        result["preparation"] = list(context.preparation.problems)
    if not context.media_passed:
        result["media"] = ["media review incomplete: see study report --section review"]
    return result


def close_round(root: Path, *, incomplete: bool = False) -> dict[str, JsonValue]:
    context = load(root)
    state = read_state(context.root)
    if state is None or not state.rounds or state.rounds[-1].closed is not None:
        raise CampusError(Code.ACTION_REQUIRED, "No open round to close.")
    pending = state.rounds[-1].pending_packets
    if pending and not incomplete:
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"The round still has unanswered packets ({', '.join(pending)}). "
            "Record them, or use --incomplete to end the round with these gaps.",
        )
    _bind_preparation(context, state)
    number = state.round
    blocked = {key: problems for key, problems in gate(context, state.scope).items() if problems}
    passed = not blocked
    for key in state.scope:
        if key not in context.items:
            continue
        record = context.record(key)
        dims = registry.dimensions(context.items[key].profile)
        entry = RoundEntry(
            round=number,
            scores=record.scores(dims),
            opened=sum(f.opened == number for f in record.findings),
            closed=sum(f.closed == number for f in record.findings),
        )
        history = tuple(h for h in record.history if h.round != number) + (entry,)
        context.records[key] = record.model_copy(update={"history": history})
    log = state.rounds[-1].model_copy(update={"closed": _now(), "gate": passed})
    status = "passed" if passed else "budget_spent" if number >= state.budget else "running"
    updated = state.model_copy(update={"rounds": (*state.rounds[:-1], log), "status": status})
    card = scorecard(context, updated, blocked)
    markdown = private_name(Path("."), "loop/scorecard.md")
    apply(
        context.root,
        (
            *(record_write(context.root, rec) for rec in context.records.values()),
            _state_write(context.root, updated),
            Write(markdown, read_bytes(confined(context.root, markdown)), _markdown(card).encode()),
        ),
    )
    return card


def scorecard(
    context: Context, state: LoopState, blocked: dict[str, list[str]] | None = None
) -> dict[str, JsonValue]:
    if context.preparation is None:
        _bind_preparation(context, state)
    blocked = (
        blocked
        if blocked is not None
        else {k: v for k, v in gate(context, state.scope).items() if v}
    )
    in_scope = [key for key in state.scope if key in context.items]
    rows = []
    failing: Counter[str] = Counter()
    finding_status: Counter[str] = Counter()
    provenance: Counter[str] = Counter()
    eye = []
    late = 0
    for key in in_scope:
        record = context.record(key)
        item = context.items[key]
        profile = item.profile
        current = {
            verdict.provenance
            for check in registry.judged(profile)
            if (verdict := record.checks.get(check.id)) and is_current(verdict, check, item)
        }
        independently_checked = "fresh" in current
        provisional = bool(current & {"same", "provisional"})
        provenance["fresh"] += independently_checked
        provenance["provisional"] += provisional
        provenance["unreviewed"] += not (independently_checked or provisional)
        finding_status.update(finding.status for finding in record.findings)
        fully_scored = all(
            (verdict := record.checks.get(check.id)) and is_current(verdict, check, item)
            for check in registry.judged(profile)
        )
        scores = record.scores(registry.dimensions(profile)) if fully_scored else {}
        live = [f for f in record.findings if f.status in LIVE]
        failing.update(f.check for f in live)
        late += sum(f.late for f in record.findings)
        eye.extend(
            {"item": key, "check": check, "reason": v.closest.reason if v.closest else ""}
            for check, v in record.checks.items()
            if v.verdict == "uncertain"
        )
        eye.extend(
            {"item": key, "check": f.check, "reason": f"reopened {f.reopens} times: {f.why}"}
            for f in live
            if f.reopens >= 3
        )
        rows.append(
            {
                "item": key,
                "scores": scores,
                "reviews": len(record.history),
                "last_round": max((v.round for v in record.checks.values()), default=0),
                "open": len(live),
                "fresh": independently_checked,
                "provisional": provisional,
                "passed": key not in blocked,
            }
        )
    workspaces: dict[str, dict[str, int]] = {}
    for row in rows:
        space = str(row["item"]).split("/", 1)[0]
        bucket = workspaces.setdefault(space, {"items": 0, "passed": 0})
        bucket["items"] += 1
        bucket["passed"] += int(bool(row["passed"]))
    averages: dict[str, float] = {}
    for name in sorted({d for row in rows for d in row["scores"]}):
        values = [row["scores"][name] for row in rows if name in row["scores"]]
        averages[name] = round(sum(values) / len(values), 2)
    return {
        "gate": not blocked,
        "scope_type": "batch" if state.batch else "prepared" if state.preparation else "ad_hoc",
        "preparation": (
            {
                "identifier": context.preparation.identifier,
                "mode": context.preparation.mode,
                "cutoff": context.preparation.cutoff,
                "ready": context.preparation.ready,
                "problems": list(context.preparation.problems),
                "provisional_plans": list(context.preparation.provisional_plans),
            }
            if context.preparation
            else None
        ),
        "status": state.status,
        "round": state.round,
        "budget": state.budget,
        "verified": f"{sum(bool(r['passed']) for r in rows)}/{len(rows)}",
        "workspaces": workspaces,
        "below_bar": [{"item": key, "problems": problems[:8]} for key, problems in blocked.items()],
        "open_findings_by_check": dict(failing.most_common()),
        "findings_by_status": dict(finding_status),
        "items_by_provenance": dict(provenance),
        "answer_keys": {
            "checked": sum(result["item"] in in_scope for result in context.answer_keys),
            "failed": sum(
                result["item"] in in_scope and not result["passed"]
                for result in context.answer_keys
            ),
        },
        "needs_your_eye": eye,
        "late_findings": late,
        # Fixes made after their item's last check: only another round can verify them.
        "fixes_to_verify": sum(
            f.status == "fixed" for key in in_scope for f in context.record(key).findings
        ),
        "structural_repairs": list(state.structural_repairs),
        "rounds": [
            {
                "round": log.round,
                "opened": log.opened,
                "resolved": log.resolved,
                "packets": len(log.packets),
                "answered_packets": len(log.answered) if log.answered is not None else None,
                "gate": log.gate,
                "minutes": round((log.closed - log.started).total_seconds() / 60, 1)
                if log.closed
                else None,
            }
            for log in state.rounds
        ],
        "averages": averages,
        "score_coverage": {
            "scored_items": sum(bool(row["scores"]) for row in rows),
            "in_scope_items": len(rows),
            "complete": bool(rows) and all(bool(row["scores"]) for row in rows),
        },
        "items": rows,
    }


def _markdown(card: dict[str, JsonValue]) -> str:
    lines = [
        f"# Review scorecard, round {card['round']} of {card['budget']}",
        "",
        f"Gate: {'passed' if card['gate'] else 'not passed'} · verified {card['verified']}"
        f" · late findings {card['late_findings']} · fixes to verify {card['fixes_to_verify']}",
        "Current score coverage: "
        f"{card['score_coverage']['scored_items']}/{card['score_coverage']['in_scope_items']} "
        "items. Averages cover these items only; "
        "changed or incomplete reviews have no current score.",
        "",
        *(
            f"Course: {problem}"
            for row in card["below_bar"]
            if row["item"] == "course"
            for problem in row["problems"]
        ),
        "Current verdicts by item · "
        + ", ".join(f"{name} {count}" for name, count in card["items_by_provenance"].items()),
        "",
        "Findings · "
        + (
            ", ".join(f"{name} {count}" for name, count in card["findings_by_status"].items())
            or "none recorded"
        ),
        "",
        "| Item | Scores | Last round | Open | Evidence | Passed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in card["items"]:
        ratings = row["scores"]
        scores = " ".join(f"{k[:5]} {v}" for k, v in ratings.items() if v < 3)
        if not scores:
            scores = "all 3" if ratings else "—"
        evidence = ", ".join(label for label in ("fresh", "provisional") if row[label])
        lines.append(
            f"| {row['item']} | {scores} | {row['last_round']} | "
            f"{row['open']} | {evidence or 'unreviewed'} | {'yes' if row['passed'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def status(root: Path) -> dict[str, JsonValue]:
    context = load(root)
    state = read_state(context.root)
    if state is None:
        return {"loop": None, "next": "tum-mcp review start PROJECT"}
    card = scorecard(context, state)
    open_round = bool(state.rounds) and state.rounds[-1].closed is None
    pending = list(state.rounds[-1].pending_packets) if open_round else []
    if state.status == "passed":
        action = (
            "The gate passed. Report the scorecard."
            if card["gate"]
            else "The last loop passed, but current evidence changed. See the scorecard."
        )
    elif state.status == "budget_spent":
        action = "The budget is spent. Report the scorecard. Extend only if requested."
        if card["fixes_to_verify"]:
            action += (
                f" {card['fixes_to_verify']} fix(es) wait for a check: "
                "tum-mcp review extend PROJECT --rounds 1 verifies them."
            )
    elif open_round:
        if pending:
            action = "Record the pending packets, fix findings, then run review verify."
        elif card["fixes_to_verify"] and not state.rounds[-1].verified:
            action = "tum-mcp review verify PROJECT"
        else:
            action = "Fix the recorded findings, then close the round."
    else:
        action = "tum-mcp review next PROJECT"
    return {
        "round": state.round,
        "budget": state.budget,
        "status": state.status,
        "gate": card["gate"],
        "scope_type": card["scope_type"],
        "preparation": card["preparation"],
        "verified": card["verified"],
        "fixes_to_verify": card["fixes_to_verify"],
        "open_round": open_round,
        "pending_packets": pending,
        "next": action,
    }


def extend(root: Path, rounds: int) -> LoopState:
    root = root.expanduser().resolve()
    state = read_state(root)
    if state is None:
        raise CampusError(Code.ACTION_REQUIRED, "No loop to extend.")
    updated = state.model_copy(
        update={
            "budget": state.budget + rounds,
            "status": "running" if state.status == "budget_spent" else state.status,
        }
    )
    apply(root, (_state_write(root, updated),))
    return updated


def review_overview(root: Path) -> dict[str, JsonValue]:
    """The review state for the course report: the loop, or every item when none runs."""
    context = load(root)
    state = read_state(context.root) or LoopState(budget=1, scope=tuple(context.items))
    card = scorecard(context, state)
    return {key: card[key] for key in ("gate", "status", "round", "budget", "verified")} | {
        "below_bar": card["below_bar"],
        "open_findings_by_check": card["open_findings_by_check"],
        "needs_your_eye": card["needs_your_eye"],
        "items_by_provenance": card["items_by_provenance"],
        "course": {"blocks": context.items["course"].blocks} if "course" in context.items else None,
        "media": context.media,
    }
