"""One declared request must be fully drafted before its combined review starts."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import Field, TypeAdapter, ValidationError

from tum_mcp.course.app.build import current_data
from tum_mcp.course.app.visuals import _exam_visuals
from tum_mcp.course.checks.plans import gate_status, plan_problems, read_plan
from tum_mcp.course.checks.preparation import PreparedScope, Readiness, _browser_problems, assess
from tum_mcp.course.content.exam_data import read_exam, stale_exam
from tum_mcp.course.content.study import Text
from tum_mcp.course.lecture.check import check_highlights
from tum_mcp.course.lecture.data import read_lectures, stale_lectures
from tum_mcp.course.lecture.selection import selection_problems
from tum_mcp.course.ledger.coverage import read_ledger
from tum_mcp.course.project.models import Key
from tum_mcp.course.project.store import digest as source_digest
from tum_mcp.course.project.store import load_state, private_path, read_bytes
from tum_mcp.course.review.items import digest
from tum_mcp.course.review.models import INVARIANT_FLAGS
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

if TYPE_CHECKING:
    from tum_mcp.course.review.loop import Context

Item = Annotated[
    str,
    Field(
        pattern=r"^(study/[a-z0-9-]+|exercises/[a-z0-9-]+/[a-z0-9-]+|exam/(pattern/[a-z0-9-]+|mock/[a-z0-9-]+/[a-z0-9-]+|sheet)|lecture/[a-z0-9-]+)$"
    ),
]


class Batch(Frozen):
    course_key: Key
    request: Text
    items: tuple[Item, ...] = Field(min_length=1, max_length=5000)
    preparations: tuple[Key, ...] = Field(default=(), max_length=100)


def require_batch_plans(root: Path, pending: set[str]) -> None:
    """Check a declared batch together rather than starting a host for each new plan."""
    for path in sorted(private_path(root, "batches").glob("*.json")):
        try:
            batch = Batch.model_validate_json(path.read_bytes())
        except ValidationError as error:
            raise CampusError(
                Code.INVALID_RESPONSE, f"Invalid batch request: {path.name}."
            ) from error
        if not pending.intersection(batch.items):
            continue
        planned = [
            key for key in batch.items if key.startswith(("study/", "exercises/", "exam/pattern/"))
        ]
        missing = [key for key in planned if read_plan(root, key) is None]
        if missing:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Write the complete batch plans before starting the fresh checker. "
                "Missing: " + ", ".join(missing) + ". Then check the pending plans together.",
            )


def assess_batch(root: Path, identifier: str, context: "Context | None" = None) -> Readiness:
    from tum_mcp.course.review.loop import load

    root = root.expanduser().resolve()
    state = load_state(root)
    try:
        key = TypeAdapter(Key).validate_python(identifier)
        body = read_bytes(private_path(root, f"batches/{key}.json"))
        if body is None:
            return Readiness(identifier=identifier, problems=("Record the batch request first.",))
        batch = Batch.model_validate_json(body)
    except ValidationError as error:
        raise CampusError(
            Code.INVALID_RESPONSE, "Invalid batch request. Use study schema batch."
        ) from error
    if batch.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "The batch belongs to another course.")
    context = context or load(root)
    items = {key: [{"request": batch.request}] for key in batch.items if key in context.items}
    problems = [f"{key}: requested draft is missing." for key in batch.items if key not in items]
    if len({key.split("/", 1)[0] for key in batch.items}) > 1 and "course" in context.items:
        items["course"] = [{"request": batch.request}]
    covered: set[str] = set()
    fingerprints = {}
    dispositions = [{"request": batch.request, "items": list(batch.items)}]
    provisional: list[str] = []
    for scope in batch.preparations:
        readiness = assess(root, scope, context)
        problems.extend(readiness.problems)
        covered.update(readiness.items)
        fingerprints.update(readiness.fingerprints)
        provisional.extend(readiness.provisional_plans)
        dispositions.extend(readiness.dispositions)
        for key in items.keys() & readiness.items.keys():
            items[key].extend(readiness.items[key])
    for key in items:
        if key.startswith(("study/", "exercises/")):
            plan = read_plan(root, key)
            if plan is None or plan.preparation not in batch.preparations:
                problems.append(f"{key}: bind its plan to the source preparation before drafting.")
    required = {key for key in items if key.startswith(("study/", "exercises/"))}
    problems.extend(f"{key}: missing prepared demand mappings." for key in required - covered)
    problems.extend(f"{key}: preparation is outside this batch." for key in covered - items.keys())
    ledger = read_ledger(root)
    outcomes = (
        {outcome.key for source in ledger.sources for outcome in source.outcomes}
        if ledger
        else set()
    )
    verified = {answer["item"]: answer for answer in context.answer_keys}
    routes: list[str] = []
    visuals: set[str] = set()
    exam = read_exam(root)
    if exam and exam.concepts and any(key.startswith("exam/pattern/") for key in items):
        items["exam/sheet"] = [{"request": batch.request}]
    if exam:
        stale = set(stale_exam(root, state, exam))
        problems.extend(
            f"{key}: cited source bytes or revisions changed."
            for key in items
            if key.startswith("exam/pattern/") and f"pattern:{key.rsplit('/', 1)[-1]}" in stale
        )
    for key in items:
        if key.startswith("exam/pattern/"):
            plan = read_plan(root, key)
            if plan is None or gate_status(plan) != "approved":
                problems.append(f"{key}: approve the current pattern plan.")
            else:
                problems.extend(
                    f"{key}: {p}" for p in plan_problems(plan, context.items[key].value, outcomes)
                )
            routes.append("#exam/patterns/" + key.rsplit("/", 1)[-1])
        if key == "exam/sheet":
            routes.append("#exam/sheet")
        if key.startswith("exam/mock/"):
            mock = key.split("/")[2]
            routes.append(f"#exam/mock/{mock}")
            if f"mock:{mock}" in stale:
                problems.append(f"{key}: cited source bytes or revisions changed.")
        problems.extend(
            f"{key}: {flag['detail']}"
            for flag in context.flags_by_item.get(key, [])
            if flag["flag"] in INVARIANT_FLAGS
        )
        if key in verified and not verified[key]["passed"]:
            problems.append(f"{key}: computed answers do not match.")
    if exam and any(key.startswith("exam/") for key in items) and _exam_visuals(exam):
        visuals.add("exam")
    lectures = read_lectures(root)
    stale = set(stale_lectures(root, state, lectures)) if lectures else set()
    for lecture in lectures.lectures if lectures else ():
        selection_key = f"lecture/{lecture.key}"
        if selection_key in items:
            if lecture.key in stale:
                problems.append(f"{selection_key}: cited source bytes or revisions changed.")
            problems.extend(
                f"{selection_key}: {p}"
                for p in selection_problems(root, lecture, lectures.evidence)
            )
            if check_highlights(root, lectures, lecture.key)["errors"]:
                problems.append(f"{selection_key}: fix the lecture check's evidence or boundaries.")
            routes.append(f"#lectures/{lecture.key}")
            for entry in lecture.entries:
                entry_key = f"{selection_key}/{entry.key}"
                items[entry_key] = [{"request": batch.request}]
    # New content in a workspace reopens the link decisions of items elsewhere that could point
    # to it (an exercise or cheatsheet entry and a new lesson), so they are decided now.
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.checks.links import undecided
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.content.store import present

    prefixes = {"study": "study/", "exercises": "exercises/", "cheatsheet": "exam/"}
    added = {
        target for target, prefix in prefixes.items() if any(k.startswith(prefix) for k in items)
    }
    added |= {"lectures"} if any(key.startswith("lecture/") for key in items) else set()
    study = read_content(root) if present(root, "study") else None
    problems.extend(
        f"{pair.item}: decide its link to the {pair.target} content (tum-mcp study links)."
        for pair in undecided(root, study, read_exercises(root), exam, lectures)
        if pair.target in added and pair.item not in items
    )
    if read_bytes(root / "app/data.mjs") != current_data(root):
        problems.append("Build the complete current draft.")
    elif not problems and routes:
        problems.extend(_browser_problems(root, routes, visuals))
    signature = source_digest(batch.model_dump_json().encode())
    contract = source_digest(batch.model_dump_json(exclude={"items"}).encode())
    return Readiness(
        identifier=identifier,
        scope=PreparedScope(identifier=identifier, fingerprint=signature),
        mode="selected_sources",
        problems=tuple(problems),
        dispositions=tuple(dispositions),
        items=items,
        fingerprints={
            key: digest({"batch": contract, "scope": fingerprints.get(key)}) for key in items
        },
        provisional_plans=tuple(provisional),
    )
