"""Build a static study app while checking its exact local source revisions."""

import json
import shutil
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from filelock import FileLock
from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course_app_paths import app_folder, app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.exercise_data import (
    check_prerequisites,
    read_exercises,
    render_exercises,
    stale_exercises,
)
from tum_mcp.extensions import require_lecture
from tum_mcp.lecture_assets import asset_writes
from tum_mcp.lecture_content import LectureContent
from tum_mcp.lecture_data import read_lectures, render_lectures, stale_lectures
from tum_mcp.settings import Frozen
from tum_mcp.study_content import (
    StudyContent,
    Unit,
    render_blocks,
)
from tum_mcp.study_math import INLINE_MATH, compile_latex
from tum_mcp.study_models import Digest, StudyState
from tum_mcp.study_publish_models import PublishReport
from tum_mcp.study_store import (
    END,
    START,
    Write,
    apply,
    confined,
    digest,
    load_state,
    private_name,
    private_path,
    read_bytes,
    replace_agents,
)

TEMPLATE_FILES = (
    "index.html",
    "styles.css",
    "app.mjs",
    "start.mjs",
    "exercises.mjs",
    "lectures.mjs",
    "exercise-state.mjs",
    "exercise-response.mjs",
    "graph-response.mjs",
    "plot.mjs",
    "dom.mjs",
    "mathml.mjs",
    "reading.mjs",
    "formulas.mjs",
    "learning.mjs",
    "question-review.mjs",
    "navigation.mjs",
    "flashcards.mjs",
    "revision.mjs",
    "anchors.mjs",
    "comments.mjs",
    "comment-ui.mjs",
    "comment-store.mjs",
    "comment-popover.mjs",
    "font-sans-latin.woff2",
    "font-sans-latin-ext.woff2",
    "font-serif-latin.woff2",
    "font-serif-latin-ext.woff2",
    "font-serif-greek.woff2",
    "fonts-license.txt",
)


class BuildRecord(Frozen):
    schema_version: int = 1
    files: dict[str, Digest] = Field(default_factory=dict, max_length=len(TEMPLATE_FILES) + 1)


@dataclass(frozen=True, slots=True)
class BuildReport:
    units: int
    preserved_templates: tuple[str, ...]
    generation: str
    publication: PublishReport | None = None
    exercises: int = 0
    lectures: int = 0
    lecture_coverage: tuple[dict[str, JsonValue], ...] = ()


def read_content(root: Path) -> StudyContent:
    path = app_path(root, "content.json")
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.ACTION_REQUIRED, "Prepare app/content.json (maximum 8 MiB) first.")
    try:
        return StudyContent.model_validate_json(path.read_bytes())
    except ValidationError as error:
        locations = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)]
        raise CampusError(
            Code.INVALID_RESPONSE,
            "Invalid study content at: " + ", ".join(locations[:5]) + ". See study schema content.",
        ) from None


def stale_units(root: Path, state: StudyState, content: StudyContent) -> tuple[str, ...]:
    if content.course_key != state.course.key:
        raise CampusError(Code.SCOPE_DENIED, "Study content belongs to a different course.")
    resources = {item.resource.key: item for item in state.resources}
    stale: list[str] = []
    for unit in content.units:
        for source in unit.sources:
            current = resources.get(source.key)
            if current is None or current.status != "current" or current.sha256 != source.sha256:
                stale.append(unit.key)
                break
            path = confined(root, current.path) if current.path else None
            if path is None or not path.is_file() or digest(path.read_bytes()) != source.sha256:
                stale.append(unit.key)
                break
    return tuple(stale)


def unit_revision(unit: Unit) -> str:
    return digest(unit.model_dump_json(exclude={"path"}, exclude_none=True).encode())


def _app_data(
    state: StudyState,
    content: StudyContent | None,
    exercises: ExerciseContent | None = None,
    lectures: LectureContent | None = None,
    root: Path | None = None,
) -> dict[str, JsonValue]:
    units: list[JsonValue] = []
    for unit in content.units if content else ():
        value = unit.model_dump(mode="json", exclude_none=True)
        value["blocks"] = render_blocks(unit.blocks)
        value["revision"] = unit_revision(unit)
        units.append(value)
    referenced = (
        {source.key for unit in content.units for source in unit.sources} if content else set()
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
    sources: dict[str, JsonValue] = {
        item.resource.key: {
            "title": item.resource.title,
            "url": item.resource.url,
            "locator": item.resource.locator,
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
        else "Lecture notes from course recordings.",
        "organization": content.organization if content else "topics",
        "units": units,
        "sources": sources,
        "inlineMath": _inline_math(content.model_dump(mode="json")) if content else {},
        "incompleteSources": sum(item.status != "complete" for item in state.coverage),
    }
    payload["workspaces"] = (["study"] if content else []) + (["exercises"] if exercises else [])
    if lectures:
        if root is None:
            raise CampusError(Code.ACTION_REQUIRED, "Lecture projection needs its bound project.")
        value = render_lectures(root, lectures)
        payload["lectures"] = value
        payload["workspaces"].append("lectures")
        payload["inlineMath"] = {**payload["inlineMath"], **_inline_math(value)}
    if exercises:
        value = render_exercises(exercises)
        payload["exercises"] = value
        payload["inlineMath"] = {
            **payload["inlineMath"],
            **_inline_math(value),
        }
    return payload


def _inline_math(value: JsonValue) -> dict[str, str]:
    """Compile each distinct inline expression once, excluding literal payloads."""
    match value:
        case str():
            return {item[1]: compile_latex(item[1]) for item in INLINE_MATH.finditer(value)}
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


def _upgrade_layout(root: Path, writes: tuple[Write, ...], state: StudyState) -> None:
    """Stage one checked layout change; keep the original tree as its backup."""
    original = confined(root, "study")
    backup = private_path(root, "layout-backup")
    if backup.exists():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Layout backup is occupied; nothing moved.")
    for path in original.rglob("*"):
        confined(root, path.relative_to(root).as_posix())
    agents_path = confined(root, "AGENTS.md")
    agents_before = read_bytes(agents_path)
    try:
        existing = (agents_before or b"").decode()
    except UnicodeError:
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Non-UTF8 instructions were preserved."
        ) from None
    start, end = existing.find(START), existing.find(END)
    block = existing[start : end + len(END)]
    updated = block.replace(
        "| Local interactive study app | `study/` |", "| Local interactive study app | `app/` |"
    )
    agents = replace_agents(existing, updated, state).encode()
    new_state = state.model_copy(update={"agents_block_sha256": digest(updated.encode())})
    state_before = read_bytes(private_path(root, "state.json"))
    with tempfile.TemporaryDirectory(prefix="layout-", dir=private_path(root, ".")) as temporary:
        stage = Path(temporary)
        shutil.copytree(original, stage / "app")
        apply(
            stage,
            tuple(
                Write("app/" + item.relative.removeprefix("study/"), item.before, item.after)
                for item in writes
            ),
        )
        if (
            confined(root, "app").exists()
            or backup.exists()
            or any(read_bytes(confined(root, item.relative)) != item.before for item in writes)
        ):
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Layout changed during staging; nothing moved."
            )
        moved = False
        try:
            original.rename(backup)
            moved = True
            (stage / "app").rename(root / "app")
            apply(
                root,
                (
                    Write("AGENTS.md", agents_before, agents),
                    Write(
                        private_name(root, "state.json"),
                        state_before,
                        new_state.model_dump_json(indent=2).encode(),
                    ),
                ),
            )
        except (OSError, CampusError):
            try:
                if moved:
                    if (root / "app").exists():
                        (root / "app").rename(stage / "app")
                    backup.rename(original)
            except OSError:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "Layout recovery needs local review. "
                    "Original files remain in .tum-mcp/layout-backup/.",
                ) from None
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Layout upgrade failed; original study/ was restored."
            ) from None


def build(root: Path, *, publish: bool = True, upgrade_layout: bool = False) -> BuildReport:
    root = root.expanduser().resolve()
    load_state(root)
    with FileLock(str(private_path(root, "update.lock"))):
        state = load_state(root)
        content = read_content(root) if app_path(root, "content.json").exists() else None
        exercises = read_exercises(root)
        if app_path(root, "lectures.json").exists():
            require_lecture()
        lectures = read_lectures(root)
        if content is None and exercises is None and lectures is None:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Prepare app/content.json, app/exercises.json or app/lectures.json.",
            )
        stale = stale_units(root, state, content) if content else ()
        if exercises:
            stale += stale_exercises(root, state, exercises)
            check_prerequisites(exercises, content)
        if lectures:
            stale += stale_lectures(root, state, lectures)
        if stale:
            raise CampusError(
                Code.STALE_RESULT, "Refresh content for changed source units: " + ", ".join(stale)
            )
        folder = app_folder(root)
        upgrading = upgrade_layout and folder == "study"
        record_path = confined(root, f"{folder}/.managed.json")
        previous = read_bytes(record_path)
        try:
            record = BuildRecord.model_validate_json(previous) if previous else BuildRecord()
        except ValidationError:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Edited study build record needs review."
            ) from None
        if upgrading and previous is None:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Build ownership is missing; nothing moved.")
        if not set(record.files) <= {*TEMPLATE_FILES, "data.mjs"}:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Unknown generated site files were preserved."
            )
        source = files("tum_mcp") / "bundled/course_app/site"
        desired = {name: (source / name).read_bytes() for name in TEMPLATE_FILES}
        payload = _app_data(state, content, exercises, lectures, root)
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        desired["data.mjs"] = ("export default " + data + ";\n").encode()
        writes: list[Write] = []
        owned = dict(record.files)
        preserved: list[str] = []
        for name, after in desired.items():
            before = read_bytes(confined(root, f"{folder}/{name}"))
            if before is not None and before != after and digest(before) != record.files.get(name):
                if name == "data.mjs":
                    raise CampusError(
                        Code.WORKSPACE_CONFLICT,
                        "Edited generated data preserved. Edit content.json instead.",
                    )
                preserved.append(name)
                continue
            writes.append(Write(f"{folder}/{name}", before, after))
            owned[name] = digest(after)
        updated = BuildRecord(files=owned).model_dump_json(indent=2).encode()
        if (exercises or lectures or upgrading) and preserved:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Customized templates were preserved; review workspace support before building.",
            )
        writes.append(Write(f"{folder}/.managed.json", previous, updated))
        writes.extend(asset_writes(root, lectures))
        if upgrading:
            try:
                _upgrade_layout(root, tuple(writes), state)
            except OSError:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "Layout staging failed; original study/ was preserved."
                ) from None
        else:
            apply(root, tuple(writes))
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
        )
    if publish:
        from tum_mcp.study_publish import after_build

        return BuildReport(
            report.units,
            report.preserved_templates,
            report.generation,
            publication=after_build(root),
            exercises=report.exercises,
            lectures=report.lectures,
            lecture_coverage=report.lecture_coverage,
        )
    return report
