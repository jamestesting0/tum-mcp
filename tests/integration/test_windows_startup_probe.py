"""Temporary hosted-runner probe: fail on the first broken course startup."""

import os
import shutil
from pathlib import Path

import pytest
from playwright.sync_api import Browser
from test_exercise_browser import (
    test_static_exercises_under_a_project_prefix as static_exercise,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_WINDOWS_STARTUP_PROBE") != "1",
    reason="Temporary Windows startup diagnosis requires explicit selection.",
)


def test_repeated_exercise_only_startup(
    course_browser: Browser, exercise_project: Path, tmp_path: Path
) -> None:
    for index in range(100):
        case = tmp_path / f"startup-{index:03d}"
        project = Path(shutil.copytree(exercise_project, case / "project"))
        print(f"Windows startup probe {index + 1}/100", flush=True)
        static_exercise(course_browser, project, case, True)
