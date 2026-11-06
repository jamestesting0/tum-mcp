"""Where the course app lives inside a course project."""

from pathlib import Path

from tum_mcp.course.project.store import confined

APP = "app"


def app_path(root: Path, name: str) -> Path:
    return confined(root, f"{APP}/{name}")
