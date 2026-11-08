"""Trusted local commands supporting the study skills. Campus access stays in read tools."""

import json
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.course.app.comment_cli import app as comments_app
from tum_mcp.course.app.publish_cli import app as publish_app
from tum_mcp.course.content.store import document_writes, index_name, present, read_document
from tum_mcp.course.memory.cli import register as register_knowledge
from tum_mcp.course.output import emit
from tum_mcp.course.workflow.cli import app as task_app
from tum_mcp.errors import CampusError, Code

app = typer.Typer(invoke_without_command=True, pretty_exceptions_show_locals=False)
register_knowledge(app)
app.add_typer(task_app, name="task", help="Track a complete local course request.")
app.add_typer(
    comments_app,
    name="comments",
    help="Read and address local passage comments.",
    rich_help_panel="Author",
)
app.add_typer(
    publish_app,
    name="publish",
    help="Publish a study website in a private GitHub repository.",
    rich_help_panel="Publish",
)


@app.callback()
def launch(
    context: typer.Context,
    port: Annotated[int, typer.Option(min=0, max=65535, help="Local app port.")] = 8765,
) -> None:
    """Open this course's study app, or run a study management command."""
    if context.invoked_subcommand is None:
        from tum_mcp.course.app.preview import serve as preview

        preview(Path.cwd(), port, open_browser=True)


@app.command(rich_help_panel="Setup")
def template() -> None:
    """Describe the packaged study starter; build installs it without overwriting edits."""
    from tum_mcp.course.app.build import TEMPLATE_FILES
    from tum_mcp.course.project.store import digest

    source = files("tum_mcp") / "bundled/course_app/site"
    hashes = {name: digest((source / name).read_bytes()) for name in TEMPLATE_FILES}
    typer.echo(
        json.dumps(
            {
                "template": "course_app/site",
                "revision": digest(json.dumps(hashes, sort_keys=True).encode()),
                "files": list(TEMPLATE_FILES),
                "author": "app/study/course.json and app/study/units/<unit>.json",
                "exercise_author": "app/exercises/sets.json and app/exercises/<set>/<problem>.json",
                "lecture_author": "app/lectures/ (optional Lecture extension)",
                "install": "tum-mcp study build PROJECT",
                "synthetic_preview": "tum-mcp study demo PROJECT",
            },
            indent=2,
        )
    )


@app.command(rich_help_panel="Setup")
def init(
    project: Path,
    course: Annotated[str, typer.Option(help="Required, explicitly chosen course title.")],
    snapshot: Annotated[Path, typer.Option(help="Validated source snapshot JSON.")],
) -> None:
    """Bind one chosen course and initialize its local study inventory."""
    from tum_mcp.course.project.sync import sync

    if not course.strip():
        raise CampusError(Code.ACTION_REQUIRED, "An explicit course input is required.")
    report = sync(project, snapshot, course_input=course)
    typer.echo(json.dumps(asdict(report), indent=2))
    if report.conflicts:
        raise typer.Exit(2)


@app.command(name="sync", rich_help_panel="Setup")
def synchronize(project: Path, snapshot: Annotated[Path, typer.Option()]) -> None:
    """Reconcile one course snapshot; preserve edits and incomplete source checks."""
    from tum_mcp.course.project.sync import sync

    report = sync(project, snapshot)
    typer.echo(json.dumps(asdict(report), indent=2))
    if report.conflicts:
        raise typer.Exit(2)


@app.command(rich_help_panel="Setup")
def status(project: Path) -> None:
    """Choose initialization, synchronization or local recovery without writing files."""
    from tum_mcp.course.project.status import project_status

    typer.echo(project_status(project).model_dump_json(indent=2))


@app.command(rich_help_panel="Setup")
def inspect(project: Path) -> None:
    """Show course identity, source coverage and units that need regeneration."""
    from tum_mcp.course.app.build import read_content, stale_units
    from tum_mcp.course.content.exercise_data import read_exercises, stale_exercises
    from tum_mcp.course.lecture.data import lecture_health, read_lectures, stale_lectures
    from tum_mcp.course.project.context import context_review
    from tum_mcp.course.project.store import PRIVATE, load_state
    from tum_mcp.course.sources.duplicates import exact_groups

    root = project.expanduser().resolve()
    state = load_state(root)
    stale = stale_units(root, state, read_content(root)) if present(root, "study") else ()
    exercises = read_exercises(root)
    lectures = read_lectures(root)
    from tum_mcp.course.content.exam_data import read_exam, stale_exam

    exam = read_exam(root)
    typer.echo(
        json.dumps(
            {
                "course": state.course.model_dump(mode="json"),
                "generation": state.generation,
                "private_folder": PRIVATE,
                "course_context": context_review(root, state).model_dump(mode="json"),
                "coverage": [item.model_dump(mode="json") for item in state.coverage],
                "resources": len(state.resources),
                "duplicate_sources": [
                    group.model_dump(mode="json") for group in exact_groups(state)
                ],
                "content_path": index_name("study"),
                "exercises_path": index_name("exercises"),
                "lectures_path": index_name("lectures"),
                "lectures": len(lectures.lectures) if lectures else 0,
                "stale_lectures": stale_lectures(root, state, lectures) if lectures else (),
                "lecture_evidence": lecture_health(root, lectures) if lectures else (),
                "stale_units": stale,
                "stale_exercises": stale_exercises(root, state, exercises) if exercises else (),
                "exam_path": index_name("exam"),
                "stale_exam": stale_exam(root, state, exam) if exam else (),
            },
            indent=2,
        )
    )


@app.command(name="exam-report", rich_help_panel="Check")
def exam_report_command(
    project: Path,
    section: Annotated[
        Literal["stats", "blueprint", "review", "targets", "stale", "duplicates"] | None,
        typer.Option(help="Only this part; duplicates also compares exam and exercise text."),
    ] = None,
    full: Annotated[bool, typer.Option("--json", help="Print the whole result.")] = False,
) -> None:
    """Report Exam statistics, blueprint, review items, targets and stale items as JSON."""
    from tum_mcp.course.content.exam_data import exam_report, read_exam, stale_exam
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.sources.duplicates import exact_groups, near_candidates

    root = project.expanduser().resolve()
    state = load_state(root)
    exam = read_exam(root)
    materials: dict[str, list[str]] = {}
    for item in state.resources:
        if item.status == "current":
            materials.setdefault(item.resource.kind, []).append(item.resource.key)
    result: dict = {"exam_path": index_name("exam"), "prepared": exam is not None}
    if section is None:
        result["materials"] = {key: sorted(value) for key, value in sorted(materials.items())}
        result["duplicates"] = {"exact": [g.model_dump() for g in exact_groups(state)]}
    if section == "duplicates":
        result["duplicates"] = near_candidates(root, state).model_dump()
    if exam is not None:
        report = exam_report(exam)
        parts = {
            "stats": report["statistics"],
            "blueprint": report["blueprint"],
            "review": report["review"],
            "targets": {"flags": report["targets"], "uncovered_core": report["uncovered_core"]},
            "stale": list(stale_exam(root, state, exam)),
        }
        result.update(
            parts if section is None else {k: v for k, v in parts.items() if k == section}
        )
    emit(root, "exam-report", result, full=full or section is not None)


@app.command(rich_help_panel="Check")
def report(
    project: Path,
    section: Annotated[
        Literal[
            "quality",
            "structure",
            "coverage",
            "review",
            "render",
            "knowledge",
            "readiness",
            "coverage-plan",
        ]
        | None,
        typer.Option(help="Only this part."),
    ] = None,
    full: Annotated[bool, typer.Option("--json", help="Print the whole result.")] = False,
    preparation: Annotated[
        str | None, typer.Option(help="Preparation scope ID for readiness.")
    ] = None,
    batch: Annotated[
        str | None, typer.Option(help="Batch ID for combined draft readiness.")
    ] = None,
) -> None:
    """Report review flags, the course map, uncovered sources, scorecard and render check."""
    from functools import cache

    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.app.visuals import render_report
    from tum_mcp.course.checks.report import quality_flags
    from tum_mcp.course.checks.structure import course_map
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.lecture.data import read_lectures
    from tum_mcp.course.ledger.coverage import coverage_report, read_ledger
    from tum_mcp.course.media.inventory import discover
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review.loop import review_overview

    root = project.expanduser().resolve()
    if section == "coverage-plan":
        from tum_mcp.course.checks.coverage_plan import assess_plan

        if not preparation or batch:
            raise CampusError(
                Code.ACTION_REQUIRED, "Use --preparation ID for a source coverage plan."
            )
        emit(
            root,
            "coverage-plan",
            {"coverage_plan": assess_plan(root, preparation).report()},
            full=True,
        )
        return
    if section == "readiness":
        from tum_mcp.course.checks.preparation import assess

        if batch and preparation:
            raise CampusError(Code.ACTION_REQUIRED, "Choose --batch or --preparation.")
        if batch:
            from tum_mcp.course.checks.batch import assess_batch

            reading = assess_batch(root, batch)
        elif preparation:
            reading = assess(root, preparation)
        else:
            raise CampusError(Code.ACTION_REQUIRED, "Name --batch ID or --preparation ID.")
        emit(root, "readiness", {"readiness": reading.report()}, full=True)
        return
    if preparation is not None or batch is not None:
        raise CampusError(Code.ACTION_REQUIRED, "Use scope selectors with --section readiness.")
    if section == "knowledge":
        from tum_mcp.course.memory.report import knowledge_report

        typer.echo(json.dumps({"knowledge": knowledge_report(root)}, ensure_ascii=False, indent=2))
        return
    state = load_state(root)
    content = read_content(root) if present(root, "study") else None
    exercises = read_exercises(root)
    exam = cache(lambda: read_exam(root))
    lectures = cache(lambda: read_lectures(root))
    ledger = cache(lambda: read_ledger(root))
    from tum_mcp.course.memory.report import knowledge_revision

    semantics = cache(lambda: knowledge_revision(root))
    media = cache(lambda: discover(root, state, content))
    quality = cache(lambda: quality_flags(content, exercises))
    parts = {
        "quality": quality,
        "structure": lambda: course_map(
            content,
            exercises,
            exam(),
            lectures(),
            ledger=ledger(),
            knowledge_revision=semantics(),
            media=media().structure,
        ),
        "coverage": lambda: coverage_report(state, content, exercises, ledger(), exam()),
        "review": lambda: review_overview(root),
        "render": lambda: render_report(root, content, exercises, exam()),
    }
    result = {name: build() for name, build in parts.items() if section in {None, name}}
    emit(root, "report", result, full=full or section is not None)


@app.command(rich_help_panel="Sources")
def duplicates(
    project: Path,
    near: Annotated[
        bool, typer.Option(help="Also compare exam and exercise text for near-duplicate copies.")
    ] = False,
) -> None:
    """Report identical and likely duplicate materials across providers; nothing is merged."""
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.sources.duplicates import DuplicateReport, exact_groups, near_candidates

    root = project.expanduser().resolve()
    state = load_state(root)
    report = near_candidates(root, state) if near else DuplicateReport(exact=exact_groups(state))
    typer.echo(report.model_dump_json(indent=2))


@app.command(name="import", rich_help_panel="Sources")
def import_material(
    project: Path,
    file: Annotated[Path, typer.Option(help="A file you already hold (PDF, text or image).")],
    kind: Annotated[
        Literal["exam", "content", "exercise", "other"], typer.Option(help="Material folder.")
    ],
    title: Annotated[str, typer.Option(help="Short descriptive title.")],
) -> None:
    """Add a file you hold as a private local source; it is never published."""
    from tum_mcp.course.sources.imports import import_file

    typer.echo(import_file(project, file, kind, title).model_dump_json(indent=2))


@app.command(rich_help_panel="Sources")
def text(
    project: Path,
    key: Annotated[str, typer.Option(help="Inventory resource key.")],
    pages: Annotated[
        str | None, typer.Option(help="Page N, FIRST-LAST or a list such as 3,7-9.")
    ] = None,
    images: Annotated[
        bool, typer.Option(help="Also render each page to a PNG to look at (12 pages at most).")
    ] = False,
) -> None:
    """Print a stored material's page text, extracted once per content hash."""
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.sources.text import document_text, page_images, text_view

    root = project.expanduser().resolve()
    state = load_state(root)
    view = text_view(document_text(root, key, state), key, pages)
    view["path"] = next(item.path for item in state.resources if item.resource.key == key)
    if images:
        rendered = page_images(root, key, [page["number"] for page in view["pages"]], state)
        for page in view["pages"]:
            page["image"] = rendered[page["number"]]
    typer.echo(json.dumps(view, indent=2))


@app.command(rich_help_panel="Sources")
def find(
    project: Path,
    query: Annotated[
        str | None, typer.Argument(help="Words that must all appear on one page.")
    ] = None,
    kind: Annotated[
        Literal["exam", "content", "exercise", "other"] | None,
        typer.Option(help="Only this material folder."),
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=100, help="Most pages to list.")] = 10,
) -> None:
    """List stored sources, or find the pages that contain every query word."""
    from tum_mcp.course.sources.text import find_sources

    result = find_sources(project, query, kind, limit)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@app.command(rich_help_panel="Author")
def links(
    project: Path,
    none: Annotated[
        str | None, typer.Option(help="Record that ITEM has no fitting link in --target.")
    ] = None,
    target: Annotated[
        str | None, typer.Option(help="study, cheatsheet, exercises or lectures.")
    ] = None,
    reason: Annotated[str | None, typer.Option(help="Why no link fits, for --none.")] = None,
) -> None:
    """List items without a link to each existing workspace, or record why none fits."""
    from tum_mcp.course.app.build import read_content
    from tum_mcp.course.checks.links import record_none, report
    from tum_mcp.course.content.exam_data import read_exam
    from tum_mcp.course.content.exercise_data import read_exercises
    from tum_mcp.course.content.store import present
    from tum_mcp.course.lecture.data import read_lectures

    root = project.expanduser().resolve()
    study = read_content(root) if present(root, "study") else None
    documents = (study, read_exercises(root), read_exam(root), read_lectures(root))
    if none is None:
        typer.echo(json.dumps(report(root, *documents), indent=2))
        return
    if not target or not reason:
        raise CampusError(Code.ACTION_REQUIRED, "Give --target and --reason with --none.")
    typer.echo(json.dumps(record_none(root, *documents, none, target, reason), indent=2))


@app.command(rich_help_panel="Author")
def build(
    project: Path,
    local_only: Annotated[
        bool, typer.Option(help="Skip configured GitHub publishing for this build.")
    ] = False,
) -> None:
    """Validate current source-linked content and build the local study app."""
    from tum_mcp.course.app.build import build as build_site

    result = build_site(project, publish=not local_only)
    typer.echo(json.dumps(asdict(result), indent=2))
    if result.publication is not None and result.publication.status in {"pending", "failed"}:
        raise typer.Exit(2)


@app.command(rich_help_panel="Author")
def schema(
    kind: Literal[
        "snapshot",
        "content",
        "exercises",
        "lectures",
        "exam",
        "coverage",
        "preparation",
        "batch",
        "lecture-selection",
        "review",
        "knowledge",
        "audio-manifest",
        "audio-plan",
        "media-review",
        "plan",
        "digest",
        "schedule",
    ],
    definition: Annotated[
        str | None, typer.Option(help="Only this definition, such as Unit or DiagramBlock.")
    ] = None,
) -> None:
    """Print the machine-readable input schema for the calling agent."""
    from tum_mcp.course.content.study import StudyContent
    from tum_mcp.course.project.models import Snapshot

    match kind:
        case "batch":
            from tum_mcp.course.checks.batch import Batch

            result = Batch.model_json_schema()
        case "lecture-selection":
            from tum_mcp.course.lecture.selection import Selection

            result = Selection.model_json_schema()
        case "knowledge":
            from tum_mcp.course.memory.models import KnowledgeRegistry

            result = KnowledgeRegistry.model_json_schema()
        case "snapshot":
            result = Snapshot.model_json_schema()
        case "content":
            result = StudyContent.model_json_schema()
        case "exercises":
            from tum_mcp.course.content.exercises import ExerciseContent

            result = ExerciseContent.model_json_schema()
        case "exam":
            from tum_mcp.course.content.exam import ExamContent

            result = ExamContent.model_json_schema()
        case "preparation":
            from tum_mcp.course.ledger.preparation import Preparation

            result = Preparation.model_json_schema()
        case "coverage":
            from tum_mcp.course.ledger.coverage import CoverageLedger

            result = CoverageLedger.model_json_schema()
        case "review":
            from tum_mcp.course.review.ledger import ItemRecord

            result = ItemRecord.model_json_schema()
        case "audio-manifest":
            from tum_mcp.course.media.audio import AudioManifest

            result = AudioManifest.model_json_schema()
        case "audio-plan":
            from tum_mcp.course.media.audio import AudioPlan

            result = AudioPlan.model_json_schema()
        case "media-review":
            from pydantic import TypeAdapter

            from tum_mcp.course.review.models import MediaReview

            result = TypeAdapter(list[MediaReview]).json_schema()
        case "plan":
            from tum_mcp.course.checks.plans import Plan

            result = Plan.model_json_schema()
        case "digest":
            from tum_mcp.course.sources.digests import SourceDigest

            result = SourceDigest.model_json_schema()
        case "schedule":
            from tum_mcp.course.project.schedule import Schedule

            result = Schedule.model_json_schema()
        case "lectures":
            from tum_mcp.course.lecture.content import LectureContent
            from tum_mcp.extensions import require_lecture

            require_lecture()
            result = LectureContent.model_json_schema()
        case unreachable:
            assert_never(unreachable)
    if definition is not None:
        definitions = result.get("$defs", {})
        if definition not in definitions:
            raise CampusError(
                Code.ACTION_REQUIRED,
                f"Unknown definition {definition}; choose from {', '.join(sorted(definitions))}.",
            )
        result = definitions[definition]
    elif kind in {"content", "exercises", "exam", "lectures"}:
        from tum_mcp.course.content.store import LAYOUTS, index_name

        workspace = "study" if kind == "content" else kind
        layout = LAYOUTS[workspace]
        paths = (
            "sets[].exercises lists keys stored in app/exercises/SET/KEY.json."
            if workspace == "exercises"
            else " ".join(
                f"{field} lists keys stored in app/{layout.folder}/{field}/KEY.json."
                for field in layout.collections
            )
        )
        result["$comment"] = (
            f"Assembled workspace schema. On disk the index is {index_name(workspace)}. "
            + paths
            + " Keep shared metadata in the index, and each item object in its own file."
        )
    typer.echo(json.dumps(result, indent=2))


@app.command(rich_help_panel="Check")
def visuals(
    project: Path,
    unit: Annotated[list[str] | None, typer.Option(help="Only this unit; repeatable.")] = None,
    exercise: Annotated[
        list[str] | None, typer.Option(help="Only this exercise, as SET/KEY; repeatable.")
    ] = None,
    exam: Annotated[bool, typer.Option("--exam", help="Only the Exam visuals.")] = False,
    gallery: Annotated[
        bool, typer.Option("--gallery", help="Draw review-course's calibration gallery instead.")
    ] = False,
    phone: Annotated[
        bool,
        typer.Option(
            "--phone", help="Also check phone and narrow widths (desktop only by default)."
        ),
    ] = False,
    interact: Annotated[
        bool,
        typer.Option(
            "--interact", help="Use every stepper, Guide | Solution pill and search instead."
        ),
    ] = False,
    full: Annotated[bool, typer.Option("--json", help="Print the whole result.")] = False,
) -> None:
    """Measure every drawn visual at desktop width (phone on request) and draw contact sheets."""
    from tum_mcp.course.app.visuals import check_interactions, check_visuals

    if interact:
        emit(
            project.expanduser().resolve(),
            "interact",
            check_interactions(
                project, tuple(unit or ()), tuple(exercise or ()), exam=exam, phone=phone
            ),
            full=full,
        )
        return
    result = check_visuals(
        project, tuple(unit or ()), tuple(exercise or ()), exam=exam, gallery=gallery, phone=phone
    )
    emit(project.expanduser().resolve(), "visuals", result, full=full)


@app.command(rich_help_panel="Check")
def verify(
    project: Path,
    item: Annotated[str | None, typer.Option(help="Only this item, such as study/dfs.")] = None,
    full: Annotated[bool, typer.Option("--json", help="Print the whole result.")] = False,
) -> None:
    """Run the answer keys in .tum-mcp/checks/ and compare them with the content."""
    from tum_mcp.course.review import loop

    root = project.expanduser().resolve()
    results = loop.load(root, answer_item=item).answer_keys
    emit(root, "verify", {"passed": all(r["passed"] for r in results), "items": results}, full=full)


@app.command(rich_help_panel="Check")
def lint(
    project: Path,
    item: Annotated[
        str | None,
        typer.Option(help="The item just written, such as study/dfs; every item when omitted."),
    ] = None,
    full: Annotated[bool, typer.Option("--json", help="Print the whole result.")] = False,
) -> None:
    """Check items in seconds: schema, report flags, plan links and answer keys."""
    from tum_mcp.course.ledger.coverage import read_ledger
    from tum_mcp.course.review import loop

    root = project.expanduser().resolve()
    from tum_mcp.course.review.items import resolve_item

    context = loop.load(root, answer_item=item)
    ledger = read_ledger(root)
    outcomes = (
        {outcome.key for source in ledger.sources for outcome in source.outcomes}
        if ledger
        else None
    )
    if item is None:
        results = {
            key: _lint_item(root, context, key, outcomes)
            for key in sorted(context.items)
            if key != "course"
        }
        result = {"passed": all(r["passed"] for r in results.values()), "items": results}
    else:
        result = _lint_item(root, context, resolve_item(context.items, item), outcomes)
    emit(root, "lint", result, full=full)


def _lint_item(root: Path, context, item: str, outcomes: set[str] | None) -> dict:
    from tum_mcp.course.checks.plans import gate_status, plan_problems, read_plan
    from tum_mcp.course.review.models import COURSE_WIDE_FLAGS, INVARIANT_FLAGS

    flags = context.flags_by_item.get(item, [])
    plan = read_plan(root, item)
    plan_state = (
        {
            "status": gate_status(plan, root),
            "problems": plan_problems(plan, context.items[item].value, outcomes),
        }
        if plan
        else {"status": "missing", "problems": []}
    )
    answers = [entry for entry in context.answer_keys if entry["item"] == item]
    blocking = [
        flag
        for flag in flags
        if flag["flag"] in INVARIANT_FLAGS and flag["flag"] not in COURSE_WIDE_FLAGS
    ]
    return {
        "item": item,
        "passed": not blocking
        and not plan_state["problems"]
        and all(entry["passed"] for entry in answers),
        "flags": [flag for flag in flags if flag["flag"] != "answer_key"],
        "plan": plan_state,
        "answer_key": answers[0] if answers else None,
    }


@app.command(rich_help_panel="Sources")
def digests(
    project: Path,
    full: Annotated[bool, typer.Option("--json", help="Print the whole result.")] = False,
) -> None:
    """Each current source's digest: missing, stale or current."""
    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.sources.digests import digest_status

    root = project.expanduser().resolve()
    rows = digest_status(root, load_state(root))
    emit(root, "digests", {"sources": rows}, full=full)


@app.command(rich_help_panel="Setup")
def schedule(
    project: Path,
    today: Annotated[str | None, typer.Option(help="The date to resolve, YYYY-MM-DD.")] = None,
) -> None:
    """This week's sessions, the sources taught so far and the next session."""
    import datetime

    from tum_mcp.course.project.schedule import read_schedule, week_of
    from tum_mcp.course.project.store import load_state

    root = project.expanduser().resolve()
    found = read_schedule(root, load_state(root))
    if found is None:
        raise CampusError(
            Code.ACTION_REQUIRED, "No schedule yet: sync-course records the session dates."
        )
    day = datetime.date.fromisoformat(today) if today else datetime.date.today()
    typer.echo(json.dumps(week_of(found, day), indent=2, ensure_ascii=False))


@app.command(rich_help_panel="Author")
def serve(project: Path, port: Annotated[int, typer.Option(min=0, max=65535)] = 8765) -> None:
    """Preview the prepared app and local comments without external hosting or logs."""
    from tum_mcp.course.app.preview import serve as preview

    preview(project, port)


@app.command(rich_help_panel="Setup")
def demo(
    project: Path,
    lectures: Annotated[
        bool,
        typer.Option("--lectures", help="Include the optional synthetic Lecture preview."),
    ] = False,
    videos: Annotated[
        bool,
        typer.Option("--videos", help="Include a synthetic Video Notes preview clip."),
    ] = False,
) -> None:
    """Create a minimal component-template preview, not a teaching example."""
    from tum_mcp.course.app.build import build as build_site
    from tum_mcp.course.project.store import Write, apply, private_name, private_path, read_bytes
    from tum_mcp.course.project.sync import read_snapshot, sync

    if lectures:
        from tum_mcp.extensions import require_lecture

        require_lecture()
    if videos:
        from tum_mcp.extension_selection import require_video_notes

        require_video_notes()
    root = project.expanduser().resolve()
    example = Path(str(files("tum_mcp") / "bundled/course_app/example"))
    writes = []
    for workspace, name in (
        ("study", "content.json"),
        ("exercises", "exercises.json"),
        ("exam", "exam.json"),
        *((("lectures", "lectures.json"),) if lectures else ()),
    ):
        document = json.loads((example / name).read_bytes())
        if present(root, workspace) and read_document(root, workspace) != document:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Existing edited content was preserved.")
        writes.extend(document_writes(root, workspace, document))
    desired = (example / "coverage.json").read_bytes()
    before = read_bytes(private_path(root, "coverage.json"))
    if before is not None and before != desired:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Existing edited coverage was preserved.")
    writes.append(Write(private_name(root, "coverage.json"), before, desired))
    if lectures:
        from tum_mcp.course.lecture.content import LectureContent

        notes = LectureContent.model_validate_json((example / "lectures.json").read_bytes())
        assets = {image.asset for lecture in notes.lectures for image in lecture.images}
        for asset in sorted(assets):
            desired = (example / asset).read_bytes()
            before = read_bytes(private_path(root, asset))
            if before is not None and before != desired:
                raise CampusError(Code.WORKSPACE_CONFLICT, "Edited demo thumbnail was preserved.")
            writes.append(Write(private_name(root, asset), before, desired))
    snapshot = example / "snapshot.json"
    sync(root, snapshot, course_input=read_snapshot(snapshot).course.title)
    apply(root, tuple(writes))
    typer.echo(json.dumps(asdict(build_site(root)), indent=2))
    if videos:
        from tum_mcp.course.media.video_project import install_demo

        install_demo(root, example / "videos")
    typer.echo(
        "Component template only; not necessarily a good teaching example. "
        "Run tum-mcp study to open it."
    )
