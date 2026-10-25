"""Build a static study app while checking its exact local source revisions."""

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import assert_never

from filelock import FileLock
from pydantic import Field, JsonValue, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.study_content import (
    CodeBlock,
    DiagramBlock,
    FormulaBlock,
    StudyContent,
    TableBlock,
    TextBlock,
    Unit,
)
from tum_mcp.study_math import INLINE_MATH, compile_latex
from tum_mcp.study_models import Digest, StudyState
from tum_mcp.study_publish_models import PublishReport
from tum_mcp.study_store import Write, apply, confined, digest, load_state, read_bytes

TEMPLATE_FILES = (
    "index.html",
    "styles.css",
    "app.mjs",
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


def read_content(root: Path) -> StudyContent:
    path = confined(root, "study/content.json")
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise CampusError(Code.ACTION_REQUIRED, "Prepare study/content.json (maximum 8 MiB) first.")
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


def _app_data(state: StudyState, content: StudyContent) -> dict[str, JsonValue]:
    units: list[JsonValue] = []
    for unit in content.units:
        value = unit.model_dump(mode="json", exclude_none=True)
        for block, rendered in zip(unit.blocks, value["blocks"], strict=True):
            match block:
                case FormulaBlock():
                    rendered["mathml"] = block.mathml or compile_latex(block.latex or "")
                case TextBlock() | TableBlock() | CodeBlock() | DiagramBlock():
                    pass
                case unreachable:
                    assert_never(unreachable)
        value["revision"] = unit_revision(unit)
        units.append(value)
    referenced = {source.key for unit in content.units for source in unit.sources}
    sources: dict[str, JsonValue] = {
        item.resource.key: {
            "title": item.resource.title,
            "url": item.resource.url,
            "locator": item.resource.locator,
        }
        for item in state.resources
        if item.resource.key in referenced
    }
    return {
        "course": {
            "identity": digest(json.dumps([state.course.key, state.course.semester]).encode()),
            "key": state.course.key,
            "title": state.course.title,
            "semester": state.course.semester,
            "synthetic": state.course.synthetic,
        },
        "generation": state.generation,
        "introduction": content.introduction,
        "organization": content.organization,
        "units": units,
        "sources": sources,
        "inlineMath": _inline_math(content.model_dump(mode="json")),
        "incompleteSources": sum(item.status != "complete" for item in state.coverage),
    }


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
                if field not in {"code", "latex", "mathml"}
                for key, math in _inline_math(item).items()
            }
        case _:
            return {}


def build(root: Path, *, publish: bool = True) -> BuildReport:
    root = root.expanduser().resolve()
    with FileLock(str(confined(root, ".study-update.lock"))):
        state, content = load_state(root), read_content(root)
        stale = stale_units(root, state, content)
        if stale:
            raise CampusError(
                Code.STALE_RESULT, "Refresh content for changed source units: " + ", ".join(stale)
            )
        record_path = confined(root, "study/.managed.json")
        previous = read_bytes(record_path)
        try:
            record = BuildRecord.model_validate_json(previous) if previous else BuildRecord()
        except ValidationError:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Edited study build record needs review."
            ) from None
        if not set(record.files) <= {*TEMPLATE_FILES, "data.mjs"}:
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Unknown generated site files were preserved."
            )
        source = files("tum_mcp") / "bundled/skills/prepare-study/assets/site"
        desired = {name: (source / name).read_bytes() for name in TEMPLATE_FILES}
        data = json.dumps(_app_data(state, content), ensure_ascii=True, separators=(",", ":"))
        desired["data.mjs"] = ("export default " + data + ";\n").encode()
        writes: list[Write] = []
        owned = dict(record.files)
        preserved: list[str] = []
        for name, after in desired.items():
            before = read_bytes(confined(root, "study/" + name))
            if before is not None and before != after and digest(before) != record.files.get(name):
                if name == "data.mjs":
                    raise CampusError(
                        Code.WORKSPACE_CONFLICT,
                        "Edited generated data preserved. Edit content.json instead.",
                    )
                preserved.append(name)
                continue
            writes.append(Write("study/" + name, before, after))
            owned[name] = digest(after)
        updated = BuildRecord(files=owned).model_dump_json(indent=2).encode()
        writes.append(Write("study/.managed.json", previous, updated))
        apply(root, tuple(writes))
        report = BuildReport(
            units=len(content.units),
            preserved_templates=tuple(preserved),
            generation=state.generation,
        )
    if publish:
        from tum_mcp.study_publish import after_build

        return BuildReport(
            report.units, report.preserved_templates, report.generation, after_build(root)
        )
    return report
