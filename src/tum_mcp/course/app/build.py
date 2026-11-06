"""Build a static study app while checking its exact local source revisions."""

import json
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from filelock import FileLock
from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.app.publish_models import PublishReport
from tum_mcp.course.content.exam import ExamContent
from tum_mcp.course.content.exercise_data import (
    check_prerequisites,
    read_exercises,
    render_exercises,
    stale_exercises,
)
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.figures import figure_bytes, figure_images
from tum_mcp.course.content.latex import compile_latex, inline_math
from tum_mcp.course.content.store import locate, present, read_json
from tum_mcp.course.content.study import (
    ExploreMaterial,
    StudyContent,
    Unit,
    compile_formulas,
    resolve_meanings,
)
from tum_mcp.course.lecture.assets import asset_writes
from tum_mcp.course.lecture.content import LectureContent
from tum_mcp.course.lecture.data import read_lectures, render_lectures, stale_lectures
from tum_mcp.course.project.models import Digest, StudyState
from tum_mcp.course.project.paths import APP, app_path
from tum_mcp.course.project.store import (
    Write,
    apply,
    confined,
    digest,
    load_state,
    private_path,
    read_bytes,
)
from tum_mcp.errors import CampusError, Code
from tum_mcp.extensions import require_lecture
from tum_mcp.settings import Frozen

TEMPLATE_FILES = (
    "index.html",
    "styles.css",
    "assets/elk/elk-license.txt",
    "assets/elk/elk.bundled.js",
    "assets/fonts/font-sans-latin-ext.woff2",
    "assets/fonts/font-sans-latin.woff2",
    "assets/fonts/fonts-license.txt",
    "assets/katex/katex-AMS-Regular.woff2",
    "assets/katex/katex-Caligraphic-Regular.woff2",
    "assets/katex/katex-Main-Bold.woff2",
    "assets/katex/katex-Main-BoldItalic.woff2",
    "assets/katex/katex-Main-Italic.woff2",
    "assets/katex/katex-Main-Regular.woff2",
    "assets/katex/katex-Math-BoldItalic.woff2",
    "assets/katex/katex-Math-Italic.woff2",
    "assets/katex/katex-Size1-Regular.woff2",
    "assets/katex/katex-Size2-Regular.woff2",
    "assets/katex/katex-Size3-Regular.woff2",
    "assets/katex/katex-Size4-Regular.woff2",
    "assets/katex/katex-license.txt",
    "assets/katex/katex.min.css",
    "assets/katex/katex.min.js",
    "runtime/comments/anchors.mjs",
    "runtime/comments/comment-popover.mjs",
    "runtime/comments/comment-store.mjs",
    "runtime/comments/comment-ui.mjs",
    "runtime/comments/comments.mjs",
    "runtime/exam/exam-entry.mjs",
    "runtime/exam/exam-map.mjs",
    "runtime/exam/exam-mock.mjs",
    "runtime/exam/exam-patterns.mjs",
    "runtime/exam/exam-sheet.mjs",
    "runtime/exam/exam-state.mjs",
    "runtime/exam/exam.mjs",
    "runtime/exercises/exercise-response.mjs",
    "runtime/exercises/exercise-state.mjs",
    "runtime/exercises/exercises.mjs",
    "runtime/exercises/graph-response.mjs",
    "runtime/lecture/lectures.mjs",
    "runtime/lecture/video.mjs",
    "runtime/reading/code.mjs",
    "runtime/reading/derivation.mjs",
    "runtime/reading/formulas.mjs",
    "runtime/reading/mathml.mjs",
    "runtime/reading/reading.mjs",
    "runtime/reading/symbols.mjs",
    "runtime/reading/walkthrough.mjs",
    "runtime/shell/app.mjs",
    "runtime/shell/completion.mjs",
    "runtime/shell/dom.mjs",
    "runtime/shell/files.mjs",
    "runtime/shell/navigation.mjs",
    "runtime/shell/reference-panel.mjs",
    "runtime/shell/search.mjs",
    "runtime/shell/start.mjs",
    "runtime/study/explore.mjs",
    "runtime/study/flashcards.mjs",
    "runtime/study/learning.mjs",
    "runtime/study/question-review.mjs",
    "runtime/study/recall.mjs",
    "runtime/study/revision.mjs",
    "runtime/visuals/graph.mjs",
    "runtime/visuals/plot.mjs",
    "runtime/visuals/uml-layout.mjs",
    "runtime/visuals/uml.mjs",
)
# Earlier templates installed these unused files. Builds remove unedited copies and
# stop managing edited ones; publication removes them from previously managed sites.
LEGACY_FLAT_FILES = tuple(name.rsplit("/", 1)[-1] for name in TEMPLATE_FILES if "/" in name)
RETIRED_TEMPLATE_FILES = (
    "font-serif-latin.woff2",
    "font-serif-latin-ext.woff2",
    "font-serif-greek.woff2",
    *LEGACY_FLAT_FILES,
)


class BuildRecord(Frozen):
    schema_version: int = 1
    files: dict[str, Digest] = Field(
        default_factory=dict, max_length=len(TEMPLATE_FILES) + len(RETIRED_TEMPLATE_FILES) + 1
    )


@dataclass(frozen=True, slots=True)
class BuildReport:
    units: int
    preserved_templates: tuple[str, ...]
    generation: str
    publication: PublishReport | None = None
    exercises: int = 0
    lectures: int = 0
    lecture_coverage: tuple[dict[str, JsonValue], ...] = ()
    exam: dict[str, int] = field(default_factory=dict)
    comments_removed: int = 0


def read_content(root: Path) -> StudyContent:
    body = read_json(root, "study")
    if body is None:
        raise CampusError(Code.ACTION_REQUIRED, "Prepare app/study/course.json first.")
    try:
        return StudyContent.model_validate_json(body)
    except ValidationError as error:
        document = json.loads(body)
        locations = [
            locate("study", document, item["loc"])
            + f" ({item['msg'].removeprefix('Value error, ')})"
            for item in error.errors(include_input=False)
        ]
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Invalid study content: " + "; ".join(locations[:5]) + ". See study schema content.",
        ) from None


def stale_units(root: Path, state: StudyState, content: StudyContent) -> tuple[str, ...]:
    if content.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "Study content belongs to a different course.")
    resources = {item.resource.key: item for item in state.resources}
    stale: list[str] = []
    for unit in content.units:
        for source in (*unit.sources, *(s for item in unit.explore for s in item.sources)):
            current = resources.get(source.key)
            if current is None or current.status != "current" or current.sha256 != source.sha256:
                stale.append(unit.key)
                break
            relative = current.path
            path = confined(root, relative) if relative else None
            if path is None or not path.is_file() or digest(path.read_bytes()) != source.sha256:
                stale.append(unit.key)
                break
    return tuple(stale)


def unit_revision(unit: Unit) -> str:
    return digest(
        unit.model_dump_json(exclude={"path", "lectures", "explore"}, exclude_none=True).encode()
    )


def explore_revision(material: ExploreMaterial) -> str:
    """Full optional passage identity, independent of core practice progress."""
    return digest(material.model_dump_json().encode())


def _app_data(
    state: StudyState,
    content: StudyContent | None,
    exercises: ExerciseContent | None = None,
    lectures: LectureContent | None = None,
    root: Path | None = None,
    exam: ExamContent | None = None,
) -> dict[str, JsonValue]:
    units: list[JsonValue] = []
    for unit in content.units if content else ():
        value = compile_formulas(unit.model_dump(mode="json", exclude_none=True))
        value["revision"] = unit_revision(unit)
        for item, rendered in zip(unit.explore, value.get("explore", []), strict=True):
            rendered["revision"] = explore_revision(item)
        resolve_meanings(value)
        units.append(value)
    referenced = (
        {source.key for unit in content.units for source in unit.sources} if content else set()
    )
    if content:
        referenced.update(
            source.key for unit in content.units for item in unit.explore for source in item.sources
        )
    if exercises:
        referenced.update(
            source.key
            for group in exercises.sets
            for ex in group.exercises
            for source in ex.sources
        )
    if lectures:
        referenced.update(source.key for lecture in lectures.lectures for source in lecture.sources)
    if exam:
        referenced.update(exam_source_keys(exam))
    local_bindings = {
        binding.key for binding in state.course.bindings if binding.provider == "local"
    }
    sources: dict[str, JsonValue] = {
        item.resource.key: {
            "title": item.resource.title
            + (" (local file)" if item.resource.binding in local_bindings else ""),
            "url": item.resource.url,
            "locator": item.resource.locator,
            # The stored copy the local preview can open; publication removes it.
            **({"file": item.path} if item.path and item.status == "current" else {}),
        }
        for item in state.resources
        if item.resource.key in referenced
    }
    payload: dict[str, JsonValue] = {
        "course": {
            "identity": digest(json.dumps([state.course.key, state.course.semester]).encode()),
            "key": state.course.key,
            "title": state.course.title,
            "semester": state.course.semester,
            "synthetic": state.course.synthetic,
        },
        "generation": state.generation,
        "introduction": content.introduction
        if content
        else "Course exercises with prepared guidance."
        if exercises
        else "Lecture highlights from course recordings."
        if lectures
        else "Exam preparation from past exams and course materials.",
        "organization": content.organization if content else "topics",
        "units": units,
        "sources": sources,
        "inlineMath": _inline_math(content.model_dump(mode="json")) if content else {},
        "definitions": {term.casefold(): item for term, item in content.definitions().items()}
        if content
        else {},
        "incompleteSources": sum(item.status != "complete" for item in state.coverage),
    }
    if content and content.annotations:
        payload["annotations"] = [entry.model_dump(mode="json") for entry in content.annotations]
    payload["workspaces"] = (["study"] if content else []) + (["exercises"] if exercises else [])
    if root is not None:
        from tum_mcp.course.ledger.coverage import pending_exercises, read_ledger, study_preparation

        ledger = read_ledger(root)
        payload["studyPreparation"] = {"pending": study_preparation(state, ledger)["pending"]}
        if exercises:
            payload["pending"] = pending_exercises(ledger, state, exercises)
    if lectures:
        if root is None:
            raise CampusError(Code.ACTION_REQUIRED, "Lecture projection needs its bound project.")
        value = render_lectures(root, lectures)
        payload["lectures"] = value
        payload["workspaces"].append("lectures")
        payload["inlineMath"] = {**payload["inlineMath"], **_inline_math(value)}
    if exam:
        from tum_mcp.course.content.exam_data import render_exam

        value = render_exam(exam)
        for context in _exam_contexts(value):
            resolve_meanings(context)
        payload["exam"] = value
        payload["workspaces"].append("exam")
        payload["inlineMath"] = {**payload["inlineMath"], **_inline_math(value)}
    if exercises:
        value = render_exercises(exercises)
        for exercise_set in value.get("sets", []):
            for exercise in exercise_set.get("exercises", []):
                resolve_meanings(exercise)
        payload["exercises"] = value
        payload["inlineMath"] = {
            **payload["inlineMath"],
            **_inline_math(value),
        }
    return payload


def data_module(payload: dict[str, JsonValue]) -> bytes:
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return ("export default " + data + ";\n").encode()


def current_data(root: Path) -> bytes:
    """Project the current authoring inputs without writing or publishing the app."""
    from tum_mcp.course.content.exam_data import read_exam

    state = load_state(root)
    content = read_content(root) if present(root, "study") else None
    return data_module(
        _app_data(state, content, read_exercises(root), read_lectures(root), root, read_exam(root))
    )


def _exam_contexts(value: dict) -> list[object]:
    # Meanings stay within a pattern or one exam question.
    questions = [
        question
        for sitting in value.get("sittings", [])
        for variant in sitting.get("variants", [])
        for question in variant.get("questions", [])
    ] + [question for mock in value.get("mocks", []) for question in mock.get("questions", [])]
    return [*value.get("patterns", []), *questions]


def exam_source_keys(exam: ExamContent) -> set[str]:
    items = (*exam.concepts, *exam.patterns, *exam.mocks)
    return {
        *(source.key for item in items for source in item.sources),
        *(source.key for source in (exam.profile.sources if exam.profile else ())),
        *(source.key for s in exam.sittings for v in s.variants for source in v.sources),
    }


def _inline_math(value: JsonValue) -> dict[str, str]:
    """Compile each distinct inline expression once, excluding literal payloads."""
    match value:
        case str():
            return {expression: compile_latex(expression) for expression in inline_math(value)}
        case list():
            return {key: math for item in value for key, math in _inline_math(item).items()}
        case dict():
            return {
                key: math
                for field, item in value.items()
                if field not in {"code", "starter_code", "latex", "mathml"}
                for key, math in _inline_math(item).items()
            }
        case _:
            return {}


def build(root: Path, *, publish: bool = True) -> BuildReport:
    root = root.expanduser().resolve()
    load_state(root)
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        content = read_content(root) if present(root, "study") else None
        exercises = read_exercises(root)
        if present(root, "lectures"):
            require_lecture()
        lectures = read_lectures(root)
        from tum_mcp.course.content.exam_data import check_unit_links, read_exam, stale_exam

        exam = read_exam(root)
        if content is None and exercises is None and lectures is None and exam is None:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Prepare Study, Exercises, Lecture or Exam content under app/ first.",
            )
        stale = stale_units(root, state, content) if content else ()
        if exercises:
            stale += stale_exercises(root, state, exercises)
            check_prerequisites(exercises, content)
        if lectures:
            stale += stale_lectures(root, state, lectures)
            known = {lecture.key for lecture in lectures.lectures}
            if content and (missing := {k for u in content.units for k in u.lectures} - known):
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    "Study links to unknown Lecture: " + ", ".join(sorted(missing)),
                )
            blocks = {
                (unit.key, block.key)
                for unit in (content.units if content else ())
                for block in unit.blocks
            }
            if unknown := sorted(
                f"{note.passage.unit}/{note.passage.block}"
                for lecture in lectures.lectures
                for note in lecture.entries
                if note.passage and (note.passage.unit, note.passage.block) not in blocks
            ):
                raise CampusError(
                    Code.INVALID_RESPONSE,
                    "Lecture entries link Study passages that do not exist: " + ", ".join(unknown),
                )
        if exam:
            stale += stale_exam(root, state, exam)
            check_unit_links(exam, content)
        from tum_mcp.course.ledger.coverage import check_ledger, read_ledger

        ledger = read_ledger(root)
        if ledger is not None:
            check_ledger(ledger, state, content, exercises, exam)
        elif content and any(unit.explore for unit in content.units):
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Record Explore classification in coverage.json before building. "
                "See study schema coverage.",
            )
        if stale:
            raise CampusError(
                Code.STALE_RESULT, "Refresh content for changed source units: " + ", ".join(stale)
            )
        folder = APP
        record_path = confined(root, f"{folder}/.managed.json")
        previous = read_bytes(record_path)
        try:
            record = BuildRecord.model_validate_json(previous) if previous else BuildRecord()
        except ValidationError:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Edited study build record needs review."
            ) from None
        if not set(record.files) <= {*TEMPLATE_FILES, *RETIRED_TEMPLATE_FILES, "data.mjs"}:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Unknown generated site files were preserved."
            )
        legacy = set(record.files).intersection(LEGACY_FLAT_FILES)
        if legacy:
            # A flat custom entry point may still import files in the old locations.
            changed = [
                name
                for name in sorted(legacy | {"index.html", "styles.css"})
                if (body := read_bytes(app_path(root, name))) is not None
                and digest(body) != record.files.get(name)
            ]
            if changed:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "The previous app layout has customized files. Preserve or port them "
                    "before migrating: " + ", ".join(changed),
                )
        source = files("tum_mcp") / "bundled/course_app/site"
        desired = {name: (source / name).read_bytes() for name in TEMPLATE_FILES}
        payload = _app_data(state, content, exercises, lectures, root, exam)
        for image in sorted(set(figure_images(payload))):
            figure_bytes(app_path(root, image))
        desired["data.mjs"] = data_module(payload)
        writes: list[Write] = []
        owned = {
            name: value
            for name, value in record.files.items()
            if name not in RETIRED_TEMPLATE_FILES
        }
        for name in RETIRED_TEMPLATE_FILES:
            before = read_bytes(confined(root, f"{folder}/{name}"))
            if before is not None and digest(before) == record.files.get(name):
                writes.append(Write(f"{folder}/{name}", before, None))
        preserved: list[str] = []
        for name, after in desired.items():
            before = read_bytes(confined(root, f"{folder}/{name}"))
            if before is not None and before != after and digest(before) != record.files.get(name):
                if name == "data.mjs":
                    raise CampusError(
                        Code.WORKSPACE_CONFLICT,
                        "Edited generated data preserved. Edit the content files instead.",
                    )
                preserved.append(name)
                continue
            writes.append(Write(f"{folder}/{name}", before, after))
            owned[name] = digest(after)
        updated = BuildRecord(files=owned).model_dump_json(indent=2).encode()
        if legacy and preserved:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "New app layout paths are already customized. The previous app was preserved: "
                + ", ".join(preserved),
            )
        if (exercises or lectures or exam) and preserved:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Customized templates were preserved; review workspace support before building.",
            )
        writes.append(Write(f"{folder}/.managed.json", previous, updated))
        writes.extend(asset_writes(root, lectures))
        apply(root, tuple(writes))
        from tum_mcp.course.app.comments import prune_comments

        workspaces = (
            ("content", content),
            ("exercises", exercises),
            ("lectures", lectures),
            ("exam", exam),
        )
        removed = prune_comments(
            root,
            {name: value.model_dump(mode="json") if value else {} for name, value in workspaces},
        )
        report = BuildReport(
            units=len(content.units) if content else 0,
            preserved_templates=tuple(preserved),
            generation=state.generation,
            exercises=sum(len(group.exercises) for group in exercises.sets) if exercises else 0,
            lectures=len(lectures.lectures) if lectures else 0,
            lecture_coverage=tuple(
                {"key": lecture.key, "status": lecture.coverage.status, "as_of": lecture.checked_at}
                for lecture in lectures.lectures
            )
            if lectures
            else (),
            exam={
                "concepts": len(exam.concepts),
                "patterns": len(exam.patterns),
                "past_papers": sum(len(sitting.variants) for sitting in exam.sittings),
                "practice_exams": len(exam.mocks),
            }
            if exam
            else {},
            comments_removed=removed,
        )
    if publish:
        from tum_mcp.course.app.publish import after_build

        return BuildReport(
            report.units,
            report.preserved_templates,
            report.generation,
            publication=after_build(root),
            exercises=report.exercises,
            lectures=report.lectures,
            lecture_coverage=report.lecture_coverage,
            exam=report.exam,
            comments_removed=report.comments_removed,
        )
    return report
