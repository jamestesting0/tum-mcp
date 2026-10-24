"""Structural skill checks. Activation quality requires separate host/model trials."""

import re

import anyio
from pydantic import Field

from tum_mcp.settings import Frozen
from tum_mcp.skills import bundled, legacy_overrides, metadata, selected


class ValidationReport(Frozen):
    checked_skills: tuple[str, ...]
    errors: tuple[str, ...]
    characters: int
    reference_characters: int = 0
    activation_evaluated: bool = False
    precision: float | None = None
    recall: float | None = None


def validate_skills() -> ValidationReport:
    from tum_mcp.server import server

    registered = {tool.name for tool in anyio.run(server.list_tools)}
    checked: list[str] = []
    errors: list[str] = []
    characters = 0
    reference_characters = 0
    for source in sorted(bundled().iterdir()):
        if not source.is_dir():
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
            for reference in re.findall(r"\]\((references/[^)]+)\)", text):
                target = (chosen / reference).resolve()
                if not target.is_relative_to(chosen.resolve()) or not target.is_file():
                    errors.append(f"{info.name}: missing or invalid reference {reference}")
    if legacy_overrides():
        errors.append(
            "Legacy skill customizations need review before exporting the consolidated pack."
        )
    if set(checked) != {"tum-moodle", "tum-artemis", "tum-zulip"}:
        errors.append("Expected exactly one skill per website: Moodle, Artemis and Zulip.")
    if {"artemis_submit", "artemis_start_exercise"} & registered:
        errors.append("Unverified remote action tools must remain unavailable.")
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
