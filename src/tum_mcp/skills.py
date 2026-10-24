"""Versioned bundled skills and user-owned overrides, with conflict-safe export."""

import shutil
from difflib import unified_diff
from importlib.resources import files
from pathlib import Path
from typing import TypedDict

import yaml
from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen, config_dir


class SkillMetadata(Frozen):
    name: str
    description: str


class SkillInfo(TypedDict):
    name: str
    description: str
    customized: bool
    entry_lines: int


def bundled() -> Path:
    return Path(str(files("tum_mcp") / "bundled" / "skills"))


def selected(name: str) -> Path:
    if name not in {path.name for path in bundled().iterdir() if path.is_dir()}:
        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "Unknown bundled skill name.")
    override = config_dir() / "skills" / name
    return override if override.is_dir() else bundled() / name


def metadata(path: Path) -> SkillMetadata:
    if path.is_symlink() or any(item.is_symlink() for item in path.rglob("*")):
        raise CampusError(Code.SCOPE_DENIED, "Skill exports cannot contain symbolic links.")
    content = (path / "SKILL.md").read_text(encoding="utf-8")
    if len(content.encode()) > 1024 * 1024:
        raise CampusError(Code.INVALID_RESPONSE, "Skill entry exceeds the portable size limit.")
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise CampusError(Code.INVALID_RESPONSE, "Skill needs YAML frontmatter.")
    try:
        raw = yaml.safe_load(content.split("---", 2)[1])
        parsed = SkillMetadata.model_validate(raw)
    except (yaml.YAMLError, ValidationError):
        raise CampusError(Code.INVALID_RESPONSE, "Skill metadata is invalid.") from None
    if parsed.name != path.name:
        raise CampusError(Code.INVALID_RESPONSE, "Skill name must match its directory.")
    return parsed


def inspect_skills() -> list[SkillInfo]:
    result: list[SkillInfo] = []
    for source in sorted(bundled().iterdir()):
        if source.is_dir():
            path = selected(source.name)
            info = metadata(path)
            result.append(
                SkillInfo(
                    name=info.name,
                    description=info.description,
                    customized=path != source,
                    entry_lines=len((path / "SKILL.md").read_text(encoding="utf-8").splitlines()),
                )
            )
    return result


def customize_skill(name: str) -> Path:
    source = selected(name)
    destination = config_dir() / "skills" / name
    if not destination.exists():
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copytree(source, destination)
    return destination


def export_pack(destination: Path) -> None:
    if destination.exists():
        raise CampusError(Code.WORKSPACE_CONFLICT, "Export destination already exists.")
    chosen_sources: list[Path] = []
    for source in sorted(bundled().iterdir()):
        if source.is_dir():
            chosen = selected(source.name)
            metadata(chosen)
            chosen_sources.append(chosen)
    destination.mkdir(parents=True)
    for chosen in chosen_sources:
        shutil.copytree(chosen, destination / chosen.name)


def skill_diff(name: str) -> str:
    chosen = selected(name)
    metadata(chosen)
    original = bundled() / name / "SKILL.md"
    return "".join(
        unified_diff(
            original.read_text(encoding="utf-8").splitlines(keepends=True),
            (chosen / "SKILL.md").read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile=f"bundled/{name}/SKILL.md",
            tofile=f"selected/{name}/SKILL.md",
        )
    )
