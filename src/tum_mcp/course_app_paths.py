"""Resolve one course template output without moving files or changing identity."""

from pathlib import Path

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_store import confined


def app_folder(root: Path) -> str:
    """Keep existing study projects; new projects use app, and conflicts stop writes."""
    current = confined(root, "app")
    legacy = confined(root, "study")
    if current.exists() and legacy.exists():
        raise CampusError(
            Code.WORKSPACE_CONFLICT,
            "Both app/ and study/ exist. Preserve and reconcile the course folders first.",
        )
    return "study" if legacy.exists() else "app"


def app_path(root: Path, name: str) -> Path:
    return confined(root, f"{app_folder(root)}/{name}")
