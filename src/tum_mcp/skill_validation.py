"""Structural skill checks. Activation quality requires separate host/model trials."""

import posixpath
import re
from pathlib import PurePosixPath

import anyio
from pydantic import Field

from tum_mcp.extension_selection import ExtensionSelection
from tum_mcp.settings import Frozen
from tum_mcp.skill_catalog import BUNDLED_SKILLS, OPTIONAL_SKILLS, active_skills
from tum_mcp.skills import bundled, legacy_overrides, metadata, selected


class ValidationReport(Frozen):
    checked_skills: tuple[str, ...]
    errors: tuple[str, ...]
    characters: int
    reference_characters: int = 0
    activation_evaluated: bool = False
    precision: float | None = None
    recall: float | None = None


def validate_skills(
    *, include_optional: bool = False, extensions: ExtensionSelection | None = None
) -> ValidationReport:
    from tum_mcp.server import LECTURE_TOOLS, server

    registered = {tool.name for tool in anyio.run(server.list_tools)}
    names = BUNDLED_SKILLS if include_optional else active_skills(extensions=extensions)
    # Optional declarations are real packaged callables; listing them is not activation proof.
    registered.update(tool.__name__ for tool in LECTURE_TOOLS)
    checked: list[str] = []
    errors: list[str] = []
    characters = 0
    reference_characters = 0
    for source in sorted(bundled().iterdir()):
        if not source.is_dir() or source.name not in names:
            continue
        chosen = selected(source.name)
        info = metadata(chosen)
        checked.append(info.name)
        content = (chosen / "SKILL.md").read_text(encoding="utf-8")
        characters += len(content)
        resources = tuple(chosen.rglob("*.md"))
        for resource in resources:
            text = resource.read_text(encoding="utf-8")
            if resource.name != "SKILL.md":
                reference_characters += len(text)
            for tool in re.findall(r"`((?:moodle|tum|zulip|artemis)_[a-z0-9_]+)`", text):
                if tool not in registered:
                    errors.append(f"{info.name}: unregistered tool {tool}")
            for reference in re.findall(r"\]\(([^)]+)\)", text):
                if reference.startswith(("https://", "http://", "#")):
                    continue
                virtual = PurePosixPath(
                    posixpath.normpath(
                        str(
                            PurePosixPath(info.name)
                            / resource.relative_to(chosen).parent
                            / reference.split("#")[0]
                        )
                    )
                )
                if not virtual.parts or virtual.parts[0] not in BUNDLED_SKILLS:
                    errors.append(f"{info.name}: missing or invalid reference {reference}")
                    continue
                if (
                    virtual.parts[0] != info.name
                    and virtual.parts[0] in OPTIONAL_SKILLS
                    and info.name in OPTIONAL_SKILLS
                ):
                    # Exported packs omit inactive optional skills, so the link would break.
                    errors.append(f"{info.name}: links into optional {virtual.parts[0]}")
                    continue
                root = selected(virtual.parts[0]).resolve()
                target = root.joinpath(*virtual.parts[1:]).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    errors.append(f"{info.name}: missing or invalid reference {reference}")
    if legacy_overrides():
        errors.append(
            "Legacy skill customizations need review before exporting the consolidated pack."
        )
    if set(checked) != set(names):
        errors.append("Expected the registered content and study workflows.")
    if {
        "artemis_submit",
        "artemis_start_exercise",
        "artemis_prepare_workspace",
        "artemis_prepare_submission",
        "tum_run_tests",
    } & registered:
        errors.append("Exercise execution tools must remain unavailable.")
    return ValidationReport(
        checked_skills=tuple(checked),
        errors=tuple(errors),
        characters=characters,
        reference_characters=reference_characters,
    )


class Trial(Frozen):
    case_id: str
    expected_skill: str | None
    selected_skill: str | None
    forbidden_effects: tuple[str, ...] = ()
    host: str
    host_version: str
    model: str
    trace_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
