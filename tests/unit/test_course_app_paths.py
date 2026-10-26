from pathlib import Path

import pytest

from tum_mcp.course_app_paths import app_folder, app_path
from tum_mcp.errors import CampusError


def test_new_projects_and_existing_legacy_projects_resolve_without_writes(tmp_path: Path) -> None:
    # Given a new root with no prepared app.
    assert app_path(tmp_path, "content.json") == tmp_path / "app/content.json"
    assert not (tmp_path / "app").exists()
    # When an existing legacy layout is present.
    (tmp_path / "study").mkdir()
    # Then callers consistently retain it until an explicit upgrade.
    assert app_folder(tmp_path) == "study"


def test_template_paths_cannot_escape_through_a_symlink(tmp_path: Path) -> None:
    # Given an app path redirected outside this course project.
    project = tmp_path / "course"
    project.mkdir()
    (project / "app").symlink_to(tmp_path, target_is_directory=True)
    # When the shared resolver inspects the path, confinement is enforced.
    with pytest.raises(CampusError):
        app_path(project, "content.json")
