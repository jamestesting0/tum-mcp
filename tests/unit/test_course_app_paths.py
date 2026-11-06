from pathlib import Path

import pytest

from tum_mcp.course.content.store import index_name, present
from tum_mcp.course.project.paths import app_path
from tum_mcp.errors import CampusError


def test_app_paths_resolve_without_writes(tmp_path: Path) -> None:
    # Given a new root with no prepared app, resolving a path creates nothing.
    assert app_path(tmp_path, "study/course.json") == tmp_path / index_name("study")
    assert not present(tmp_path, "study")
    assert not (tmp_path / "app").exists()


def test_template_paths_cannot_escape_through_a_symlink(tmp_path: Path) -> None:
    # Given an app path redirected outside this course project.
    project = tmp_path / "course"
    project.mkdir()
    (project / "app").symlink_to(tmp_path, target_is_directory=True)
    # When the shared resolver inspects the path, confinement is enforced.
    with pytest.raises(CampusError):
        app_path(project, "study/course.json")
