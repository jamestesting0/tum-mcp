"""Read-only lifecycle routing; incomplete projects must not be mistaken for new ones."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from tum_mcp.errors import CampusError
from tum_mcp.extension_selection import course_memory_enabled
from tum_mcp.lecture_data import read_lectures
from tum_mcp.settings import Frozen
from tum_mcp.study_store import END, START, confined, load_state, private_path, replace_agents


class CourseSummary(Frozen):
    key: str
    title: str
    semester: str
    synthetic: bool


class ProjectStatus(Frozen):
    schema_version: Literal[1] = 1
    mode: Literal["initialize", "sync", "recover"]
    reason: str
    course: CourseSummary | None = None
    generation: str | None = None
    resources: int = 0
    course_memory: bool = Field(default_factory=course_memory_enabled)
    lecture_notes: Literal["absent", "authored", "invalid"] = "absent"
    lectures: int = 0


def _instructions(root: Path) -> str:
    path = confined(root, "AGENTS.md")
    if not path.exists():
        return ""
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise OSError("Study instructions need review.")
    return path.read_text(encoding="utf-8")


def project_status(project: Path) -> ProjectStatus:
    """Inspect only known local state paths, without creating files or contacting campus."""
    root = project.expanduser().absolute()
    try:
        if root.is_symlink() or root.is_junction():
            return ProjectStatus(mode="recover", reason="symbolic_project_path")
        if root.exists() and not root.is_dir():
            return ProjectStatus(mode="recover", reason="project_path_occupied")
        if any(parent.exists() and not parent.is_dir() for parent in root.parents):
            return ProjectStatus(mode="recover", reason="project_parent_occupied")
        root = root.resolve()
        state_path = private_path(root, "state.json")
        if not state_path.exists():
            artifacts = any(
                confined(root, name).exists()
                for name in (".tum-mcp", ".study", "materials", "study", "app")
            )
            instructions = _instructions(root)
            if artifacts or START in instructions or END in instructions:
                return ProjectStatus(mode="recover", reason="existing_study_files_without_state")
            return ProjectStatus(mode="initialize", reason="no_study_state")
        state = load_state(root)
    except CampusError:
        return ProjectStatus(mode="recover", reason="invalid_or_unsafe_state")
    except (OSError, UnicodeError):
        return ProjectStatus(mode="recover", reason="unreadable_project_files")

    course = CourseSummary(
        key=state.course.key,
        title=state.course.title,
        semester=state.course.semester,
        synthetic=state.course.synthetic,
    )
    bindings = {item.key for item in state.course.bindings}
    coverage = [item.binding for item in state.coverage]
    resources = [item.resource.key for item in state.resources]
    if (
        len(coverage) != len(set(coverage))
        or set(coverage) != bindings
        or len(resources) != len(set(resources))
        or any(item.resource.binding not in bindings for item in state.resources)
    ):
        return ProjectStatus(mode="recover", reason="inconsistent_inventory", course=course)
    try:
        # Reuse the sync writer's integrity check without applying its returned text.
        replace_agents(_instructions(root), "", state)
    except (CampusError, OSError, UnicodeError):
        return ProjectStatus(
            mode="recover",
            reason="managed_instructions_need_review",
            course=course,
            generation=state.generation,
            resources=len(state.resources),
        )
    try:
        lectures = read_lectures(root)
        lecture_notes = "authored" if lectures else "absent"
    except CampusError:
        lectures, lecture_notes = None, "invalid"
    return ProjectStatus(
        mode="sync",
        reason="bound_course",
        course=course,
        generation=state.generation,
        resources=len(state.resources),
        lecture_notes=lecture_notes,
        lectures=len(lectures.lectures) if lectures else 0,
    )
