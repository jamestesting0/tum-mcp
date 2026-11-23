"""One declared request must be fully drafted before its combined review starts."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from tum_mcp.course.app.build import current_data
from tum_mcp.course.app.visuals import _exam_visuals, lecture_routes, shell_workspace
from tum_mcp.course.checks.plans import gate_status, plan_problems, read_plan
from tum_mcp.course.checks.preparation import (
    BrowserProblem,
    PreparedScope,
    Readiness,
    _browser_problems,
    assess,
    browser_owner,
    record_browser_problems,
)
from tum_mcp.course.content.exam_data import exam_surface_sources, read_exam, stale_exam_sources
from tum_mcp.course.content.study import Text
from tum_mcp.course.lecture.check import SUMMARY_META, TITLE_DATE, check_highlights
from tum_mcp.course.lecture.data import read_lectures, stale_lectures
from tum_mcp.course.lecture.scope import LectureScope, accounting, cached_recordings
from tum_mcp.course.lecture.selection import selection_problems
from tum_mcp.course.ledger.coverage import read_ledger
from tum_mcp.course.project.models import KEY_SEGMENT, PLAN_ROUTES, Key
from tum_mcp.course.project.store import digest as source_digest
from tum_mcp.course.project.store import load_state, private_path, read_bytes
from tum_mcp.course.review.items import digest
from tum_mcp.course.review.models import INVARIANT_FLAGS, SHEET
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

if TYPE_CHECKING:
    from tum_mcp.course.review.loop import Context

Item = Annotated[
    str,
    Field(
        pattern=rf"^({PLAN_ROUTES}|exam/(mock/{KEY_SEGMENT}/{KEY_SEGMENT}|sheet)|lecture/{KEY_SEGMENT})$"
    ),
]


class Batch(Frozen):
    course_key: Key
    request: Text
    items: tuple[Item, ...] = Field(min_length=1, max_length=5000)
    preparations: tuple[Key, ...] = Field(default=(), max_length=100)
    lecture_scope: LectureScope | None = None


def checker_batch(root: Path, items: set[str], selector: str | None) -> tuple[str, Batch] | None:
    """Resolve one course-owned batch for plan checking."""
    paths = sorted(private_path(root, "batches").glob("*.json"))
    if selector is not None:
        try:
            key = TypeAdapter(Key).validate_python(selector)
        except ValidationError as error:
            raise CampusError(Code.ACTION_REQUIRED, "Use a valid project batch key.") from error
        paths = [path for path in paths if path.stem == key]
        if not paths:
            raise CampusError(Code.ACTION_REQUIRED, f"No batch request for {key}.")
    if not paths or (selector is None and not items):
        return None
    course = load_state(root).course.key
    matches: list[tuple[str, Batch]] = []
    for path in paths:
        try:
            key = TypeAdapter(Key).validate_python(path.stem)
            batch = Batch.model_validate_json(path.read_bytes())
        except ValidationError as error:
            raise CampusError(
                Code.INVALID_RESPONSE, f"Invalid batch request: {path.name}."
            ) from error
        if batch.course_key != course:
            if selector is not None:
                raise CampusError(Code.SCOPE_DENIED, "The batch belongs to another course.")
        elif selector is not None or items.intersection(batch.items):
            matches.append((key, batch))
    if len(matches) > 1:
        choices = ", ".join(key for key, _ in matches)
        raise CampusError(Code.ACTION_REQUIRED, f"Choose a plan scope with --batch: {choices}.")
    return matches[0] if matches else None


def _batch_browser(
    root: Path,
    routes: list[str],
    visuals: set[str],
    problems: list[str],
    workspace_problems: dict[str, list[str]],
) -> list[BrowserProblem]:
    assigned = {problem for issues in workspace_problems.values() for problem in issues}
    if any(
        problem not in assigned
        and not problem.startswith(("study/", "exercises/", "exam/", "lecture/"))
        for problem in problems
    ):
        return []
    selected = [
        route for route in routes if not workspace_problems[browser_owner(shell_workspace(route))]
    ]
    if not selected:
        return []
    owners = {browser_owner(shell_workspace(route)) for route in selected}
    return _browser_problems(
        root, selected, {item for item in visuals if item.partition("/")[0] in owners}
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
    context = context or load(root, answer_scope=batch.items, batch_dependencies=True)
    items = {key: [{"request": batch.request}] for key in batch.items if key in context.items}
    problems = [f"{key}: requested draft is missing." for key in batch.items if key not in items]
    if len({key.split("/", 1)[0] for key in batch.items}) > 1 and "course" in context.items:
        items["course"] = [{"request": batch.request}]
    covered: set[str] = set()
    fingerprints = {}
    dispositions = [{"request": batch.request, "items": list(batch.items)}]
    provisional: list[str] = []
    preparations: list[dict[str, JsonValue]] = []
    browser_commands: dict[str, str] = {}
    workspace_problems: dict[str, list[str]] = {
        key.partition("/")[0]: [] for key in batch.items if key != "course"
    }
    if batch.lecture_scope:
        rows, gaps = accounting(
            root,
            cached_recordings(root, state),
            batch.lecture_scope.through,
            batch.items,
            batch.lecture_scope,
        )
        dispositions.extend(row.model_dump(mode="json") for row in rows)
        problems.extend(gaps)
        workspace_problems.setdefault("lecture", []).extend(gaps)
        browser_commands.update({gap: f"tum-mcp lecture inspect . --batch {key}" for gap in gaps})
    for scope in batch.preparations:
        readiness = assess(root, scope, context)
        problems.extend(readiness.problems)
        browser_commands.update(readiness.browser_commands)
        for workspace, issues in readiness.workspace_problems.items():
            workspace_problems.setdefault(workspace, []).extend(issues)
        covered.update(readiness.items)
        fingerprints.update(readiness.fingerprints)
        provisional.extend(readiness.provisional_plans)
        preparations.append(
            {
                "identifier": scope,
                "mode": readiness.mode,
                "cutoff": readiness.cutoff,
                "cutoff_verified": readiness.cutoff_verified,
                "provisional_sources": list(readiness.provisional_sources),
                "unresolved_sources": list(readiness.unresolved_sources),
                "partial_providers": list(readiness.partial_providers),
            }
        )
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
    if exam and any(key.startswith("exam/") for key in items):
        if SHEET in context.items and any(key.startswith("exam/pattern/") for key in items):
            items.setdefault(SHEET, [{"request": batch.request}])
        dependencies = exam_surface_sources(exam, set(items))
        stale_records = stale_exam_sources(root, state, exam, set().union(*dependencies.values()))
        problems.extend(
            f"{key}: {owner} cited source bytes or revisions changed: {', '.join(sources)}."
            for key, owners in dependencies.items()
            for owner, sources in stale_records.items()
            if owner in owners
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
        if key == SHEET:
            routes.append("#exam/sheet")
        if key.startswith("exam/mock/"):
            mock = key.split("/")[2]
            routes.append(f"#exam/mock/{mock}")
        problems.extend(
            f"{key}: {flag['detail']}"
            for flag in context.flags_by_item.get(key, [])
            if flag["flag"] in INVARIANT_FLAGS
        )
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
            if TITLE_DATE.search(lecture.title):
                problems.append(
                    f"{selection_key}: the title repeats a date; name the topic only, "
                    "the app shows the recording date."
                )
            if SUMMARY_META.search(lecture.summary):
                problems.append(
                    f"{selection_key}: the summary describes the recording or its notes; say "
                    "what the lecture teaches."
                )
            if not lecture.chapters:
                problems.append(
                    f"{selection_key}: add chapters, the lecture's topics in recording order "
                    "(study schema --example lecture-chapter)."
                )
            if "#lectures" not in routes:
                routes.append("#lectures")
            routes.extend(lecture_routes(lecture))
            visuals.update(("lecture", selection_key))
            for entry in lecture.entries:
                entry_key = f"{selection_key}/{entry.key}"
                items[entry_key] = [{"request": batch.request}]
    problems.extend(
        f"{key}: computed answers do not match."
        for key in items
        if key in verified and verified[key]["status"] != "passed"
    )
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
    for problem in problems:
        workspace = problem.partition("/")[0]
        if workspace in workspace_problems:
            workspace_problems[workspace].append(problem)

    pending_check = None
    if read_bytes(root / "app/data.mjs") != current_data(root):
        problem = "Build the complete current draft."
        problems.append(problem)
        pending_check = (problem, "tum-mcp study build . --local-only")
    elif routes:
        browser = _batch_browser(root, routes, visuals, problems, workspace_problems)
        browser_commands.update(record_browser_problems(browser, problems, workspace_problems))
    excluded = {"lecture_scope"} if batch.lecture_scope is None else set()
    signature = source_digest(batch.model_dump_json(exclude=excluded).encode())
    contract = source_digest(batch.model_dump_json(exclude=excluded | {"items"}).encode())
    lecture_cutoff = (
        batch.lecture_scope.through.isoformat()
        if batch.lecture_scope and set(workspace_problems) == {"lecture"}
        else None
    )
    return Readiness(
        identifier=identifier,
        scope=PreparedScope(identifier=identifier, fingerprint=signature),
        mode="through_date" if lecture_cutoff else "selected_sources",
        cutoff=lecture_cutoff,
        problems=tuple(problems),
        dispositions=tuple(dispositions),
        items=items,
        fingerprints={
            key: digest({"batch": contract, "scope": fingerprints.get(key)}) for key in items
        },
        provisional_plans=tuple(provisional),
        preparations=tuple(preparations),
        pending_check=pending_check,
        browser_commands=browser_commands,
        workspace_problems={
            workspace: tuple(dict.fromkeys(issues))
            for workspace, issues in workspace_problems.items()
        },
    )
