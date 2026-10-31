"""Trusted local commands supporting the study skills. Campus access stays in read tools."""

import json
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, assert_never

import typer

from tum_mcp.course_app_paths import app_folder, app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_comment_cli import app as comments_app
from tum_mcp.study_publish_cli import app as publish_app

app = typer.Typer(invoke_without_command=True, pretty_exceptions_show_locals=False)
app.add_typer(comments_app, name="comments", help="Read and address local passage comments.")
app.add_typer(
    publish_app, name="publish", help="Publish a study website in a private GitHub repository."
)


@app.callback()
def launch(
    context: typer.Context,
    port: Annotated[int, typer.Option(min=0, max=65535, help="Local app port.")] = 8765,
) -> None:
    """Open this course's study app, or run a study management command."""
    if context.invoked_subcommand is None:
        from tum_mcp.study_preview import serve as preview

        preview(Path.cwd(), port, open_browser=True)


@app.command()
def template() -> None:
    """Describe the packaged study starter; build installs it without overwriting edits."""
    from tum_mcp.study_build import TEMPLATE_FILES
    from tum_mcp.study_store import digest

    source = files("tum_mcp") / "bundled/course_app/site"
    hashes = {name: digest((source / name).read_bytes()) for name in TEMPLATE_FILES}
    typer.echo(
        json.dumps(
            {
                "template": "course_app/site",
                "revision": digest(json.dumps(hashes, sort_keys=True).encode()),
                "files": list(TEMPLATE_FILES),
                "author": "app/content.json",
                "exercise_author": "app/exercises.json",
                "lecture_author": "app/lectures.json (optional Lecture extension)",
                "install": "tum-mcp study build PROJECT",
                "synthetic_preview": "tum-mcp study demo PROJECT",
            },
            indent=2,
        )
    )


@app.command()
def init(
    project: Path,
    course: Annotated[str, typer.Option(help="Required, explicitly chosen course title.")],
    snapshot: Annotated[Path, typer.Option(help="Validated source snapshot JSON.")],
) -> None:
    """Bind one chosen course and initialize its local study inventory."""
    from tum_mcp.study_sync import sync

    if not course.strip():
        raise CampusError(Code.ACTION_REQUIRED, "An explicit course input is required.")
    report = sync(project, snapshot, course_input=course)
    typer.echo(json.dumps(asdict(report), indent=2))
    if report.conflicts:
        raise typer.Exit(2)


@app.command(name="sync")
def synchronize(project: Path, snapshot: Annotated[Path, typer.Option()]) -> None:
    """Reconcile one course snapshot; preserve edits and incomplete source checks."""
    from tum_mcp.study_sync import sync

    report = sync(project, snapshot)
    typer.echo(json.dumps(asdict(report), indent=2))
    if report.conflicts:
        raise typer.Exit(2)


@app.command()
def status(project: Path) -> None:
    """Choose initialization, synchronization or local recovery without writing files."""
    from tum_mcp.study_status import project_status

    typer.echo(project_status(project).model_dump_json(indent=2))


@app.command()
def upgrade(project: Path) -> None:
    """Move legacy state to .tum-mcp and refresh the AGENTS.md guide; the website is kept."""
    from tum_mcp.study_store import private_folder, upgrade_private

    root = project.expanduser().resolve()
    refreshed = upgrade_private(root)
    typer.echo(
        json.dumps(
            {
                "private_folder": private_folder(root),
                "agent_guide": "refreshed" if refreshed else "current",
                "preserved": "state, comments, publication settings and user files",
            }
        )
    )


@app.command()
def inspect(project: Path) -> None:
    """Show course identity, source coverage and units that need regeneration."""
    from tum_mcp.course_context import context_review
    from tum_mcp.exercise_data import read_exercises, stale_exercises
    from tum_mcp.lecture_data import lecture_health, read_lectures, stale_lectures
    from tum_mcp.study_build import read_content, stale_units
    from tum_mcp.study_duplicates import exact_groups
    from tum_mcp.study_store import load_state, private_folder

    root = project.expanduser().resolve()
    state = load_state(root)
    stale = (
        stale_units(root, state, read_content(root))
        if app_path(root, "content.json").is_file()
        else ()
    )
    exercises = read_exercises(root)
    lectures = read_lectures(root)
    from tum_mcp.exam_data import read_exam, stale_exam

    exam = read_exam(root)
    typer.echo(
        json.dumps(
            {
                "course": state.course.model_dump(mode="json"),
                "generation": state.generation,
                "private_folder": private_folder(root),
                "course_context": context_review(root, state).model_dump(mode="json"),
                "coverage": [item.model_dump(mode="json") for item in state.coverage],
                "resources": len(state.resources),
                "duplicate_sources": [
                    group.model_dump(mode="json") for group in exact_groups(state)
                ],
                "content_path": f"{app_folder(root)}/content.json",
                "exercises_path": f"{app_folder(root)}/exercises.json",
                "lectures_path": f"{app_folder(root)}/lectures.json",
                "lectures": len(lectures.lectures) if lectures else 0,
                "stale_lectures": stale_lectures(root, state, lectures) if lectures else (),
                "lecture_evidence": lecture_health(root, lectures) if lectures else (),
                "stale_units": stale,
                "stale_exercises": stale_exercises(root, state, exercises) if exercises else (),
                "exam_path": f"{app_folder(root)}/exam.json",
                "stale_exam": stale_exam(root, state, exam) if exam else (),
            },
            indent=2,
        )
    )


@app.command(name="exam-report")
def exam_report_command(
    project: Path,
    section: Annotated[
        Literal["stats", "blueprint", "review", "targets", "stale", "duplicates"] | None,
        typer.Option(help="Only this part; duplicates also compares exam and exercise text."),
    ] = None,
) -> None:
    """Report Exam statistics, blueprint, review items, targets and stale items as JSON."""
    from tum_mcp.exam_data import exam_report, read_exam, stale_exam
    from tum_mcp.study_duplicates import exact_groups, near_candidates
    from tum_mcp.study_store import load_state

    root = project.expanduser().resolve()
    state = load_state(root)
    exam = read_exam(root)
    materials: dict[str, list[str]] = {}
    for item in state.resources:
        if item.status == "current":
            materials.setdefault(item.resource.kind, []).append(item.resource.key)
    result: dict = {"exam_path": f"{app_folder(root)}/exam.json", "prepared": exam is not None}
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
    typer.echo(json.dumps(result, indent=2))


@app.command()
def report(
    project: Path,
    section: Annotated[
        Literal["quality", "structure", "coverage", "review", "render"] | None,
        typer.Option(help="Only this part."),
    ] = None,
) -> None:
    """Report review flags, the course map, uncovered sources, scorecard and render check."""
    from functools import cache

    from tum_mcp.exam_data import read_exam
    from tum_mcp.exercise_data import read_exercises
    from tum_mcp.lecture_data import read_lectures
    from tum_mcp.study_build import read_content
    from tum_mcp.study_coverage import coverage_report, read_ledger
    from tum_mcp.study_report import quality_flags
    from tum_mcp.study_review import read_scorecard, review_report
    from tum_mcp.study_store import load_state
    from tum_mcp.study_structure import course_map
    from tum_mcp.study_visuals import render_report

    root = project.expanduser().resolve()
    state = load_state(root)
    content = read_content(root) if app_path(root, "content.json").is_file() else None
    exercises = read_exercises(root)
    exam = cache(lambda: read_exam(root))
    lectures = cache(lambda: read_lectures(root))
    ledger = cache(lambda: read_ledger(root))
    parts = {
        "quality": lambda: quality_flags(content, exercises),
        "structure": lambda: course_map(content, exercises, exam(), lectures(), ledger=ledger()),
        "coverage": lambda: coverage_report(state, content, exercises, ledger()),
        "review": lambda: review_report(
            state, content, exercises, read_scorecard(root), exam(), lectures(), ledger=ledger()
        ),
        "render": lambda: render_report(root, content, exercises, exam()),
    }
    result = {name: build() for name, build in parts.items() if section in {None, name}}
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@app.command()
def duplicates(
    project: Path,
    near: Annotated[
        bool, typer.Option(help="Also compare exam and exercise text for near-duplicate copies.")
    ] = False,
) -> None:
    """Report identical and likely duplicate materials across providers; nothing is merged."""
    from tum_mcp.study_duplicates import DuplicateReport, exact_groups, near_candidates
    from tum_mcp.study_store import load_state

    root = project.expanduser().resolve()
    state = load_state(root)
    report = near_candidates(root, state) if near else DuplicateReport(exact=exact_groups(state))
    typer.echo(report.model_dump_json(indent=2))


@app.command(name="import")
def import_material(
    project: Path,
    file: Annotated[Path, typer.Option(help="A file you already hold (PDF, text or image).")],
    kind: Annotated[
        Literal["exam", "content", "exercise", "other"], typer.Option(help="Material folder.")
    ],
    title: Annotated[str, typer.Option(help="Short descriptive title.")],
) -> None:
    """Add a file you hold as a private local source; it is never published."""
    from tum_mcp.study_import import import_file

    typer.echo(import_file(project, file, kind, title).model_dump_json(indent=2))


@app.command()
def text(
    project: Path,
    key: Annotated[str, typer.Option(help="Inventory resource key.")],
    pages: Annotated[str | None, typer.Option(help="Page N or FIRST-LAST.")] = None,
    images: Annotated[
        bool, typer.Option(help="Also render each page to a PNG to look at (12 pages at most).")
    ] = False,
) -> None:
    """Print a stored material's page text, extracted once per content hash."""
    from tum_mcp.study_store import load_state
    from tum_mcp.study_text import document_text, page_images, text_view

    root = project.expanduser().resolve()
    state = load_state(root)
    view = text_view(document_text(root, key, state), key, pages)
    view["path"] = next(item.path for item in state.resources if item.resource.key == key)
    if images:
        rendered = page_images(root, key, [page["number"] for page in view["pages"]], state)
        for page in view["pages"]:
            page["image"] = rendered[page["number"]]
    typer.echo(json.dumps(view, indent=2))


@app.command()
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
    from tum_mcp.study_text import find_sources

    result = find_sources(project, query, kind, limit)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@app.command()
def build(
    project: Path,
    upgrade_layout: Annotated[
        bool,
        typer.Option(help="Explicitly upgrade a verified study/ layout to app/ with a backup."),
    ] = False,
    local_only: Annotated[
        bool, typer.Option(help="Skip configured GitHub publishing for this build.")
    ] = False,
) -> None:
    """Validate current source-linked content and build the local study app."""
    from tum_mcp.study_build import build as build_site

    result = build_site(project, publish=not local_only, upgrade_layout=upgrade_layout)
    typer.echo(json.dumps(asdict(result), indent=2))
    if result.publication is not None and result.publication.status in {"pending", "failed"}:
        raise typer.Exit(2)


@app.command()
def schema(
    kind: Literal["snapshot", "content", "exercises", "lectures", "exam", "coverage", "review"],
) -> None:
    """Print the machine-readable input schema for the calling agent."""
    from tum_mcp.study_content import StudyContent
    from tum_mcp.study_models import Snapshot

    match kind:
        case "snapshot":
            result = Snapshot.model_json_schema()
        case "content":
            result = StudyContent.model_json_schema()
        case "exercises":
            from tum_mcp.exercise_content import ExerciseContent

            result = ExerciseContent.model_json_schema()
        case "exam":
            from tum_mcp.exam_content import ExamContent

            result = ExamContent.model_json_schema()
        case "coverage":
            from tum_mcp.study_coverage import CoverageLedger

            result = CoverageLedger.model_json_schema()
        case "review":
            from tum_mcp.study_review import ReviewScorecard

            result = ReviewScorecard.model_json_schema()
        case "lectures":
            from tum_mcp.extensions import require_lecture
            from tum_mcp.lecture_content import LectureContent

            require_lecture()
            result = LectureContent.model_json_schema()
        case unreachable:
            assert_never(unreachable)
    typer.echo(json.dumps(result, indent=2))


@app.command()
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
) -> None:
    """Measure every drawn visual at phone, narrow and desktop width and draw contact sheets."""
    from tum_mcp.study_visuals import check_visuals

    result = check_visuals(
        project, tuple(unit or ()), tuple(exercise or ()), exam=exam, gallery=gallery
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@app.command()
def serve(project: Path, port: Annotated[int, typer.Option(min=0, max=65535)] = 8765) -> None:
    """Preview the prepared app and local comments without external hosting or logs."""
    from tum_mcp.study_preview import serve as preview

    preview(project, port)


@app.command()
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
    from tum_mcp.study_build import build as build_site
    from tum_mcp.study_store import Write, apply, private_name, private_path, read_bytes
    from tum_mcp.study_sync import read_snapshot, sync

    if lectures:
        from tum_mcp.extensions import require_lecture

        require_lecture()
    if videos:
        from tum_mcp.extension_selection import require_video_notes

        require_video_notes()
    root = project.expanduser().resolve()
    example = Path(str(files("tum_mcp") / "bundled/course_app/example"))
    writes = []
    for name in (
        "content.json",
        "exercises.json",
        "exam.json",
        *(("lectures.json",) if lectures else ()),
    ):
        desired = (example / name).read_bytes()
        before = read_bytes(app_path(root, name))
        if before is not None and before != desired:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Existing edited content was preserved.")
        writes.append(Write(f"{app_folder(root)}/{name}", before, desired))
    desired = (example / "coverage.json").read_bytes()
    before = read_bytes(private_path(root, "coverage.json"))
    if before is not None and before != desired:
        raise CampusError(Code.WORKSPACE_CONFLICT, "Existing edited coverage was preserved.")
    writes.append(Write(private_name(root, "coverage.json"), before, desired))
    if lectures:
        from tum_mcp.lecture_content import LectureContent

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
        from tum_mcp.video_project import install_demo

        install_demo(root, example / "videos")
    typer.echo(
        "Component template only; not necessarily a good teaching example. "
        "Run tum-mcp study to open it."
    )
