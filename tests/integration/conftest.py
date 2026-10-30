import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers


@pytest.fixture(scope="module")
def course_browser() -> Iterator[Browser]:
    """Keep Playwright's event loop out of later async MCP tests; isolate each context."""
    choices = discover_browsers()
    assert choices, "The requested browser QA requires an existing Chromium browser."
    with browser_driver(choices[0]), sync_playwright() as playwright:
        args = (
            ["--disable-features=TcpPortRandomizationWin"]
            if sys.platform == "win32" or choices[0].windows_host
            else []
        )
        browser = playwright.chromium.launch(
            executable_path=choices[0].executable, headless=True, args=args
        )
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    example = Path(__file__).parents[1] / "fixtures/course_app"
    path = tmp_path / "incoming.json"
    path.write_bytes((example / "snapshot.json").read_bytes())
    return path


@pytest.fixture(scope="session")
def built_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the private rich regression fixture once; each test gets a copy."""
    root = tmp_path_factory.mktemp("study-starter") / "Course space Ω"
    example = Path(__file__).parents[1] / "fixtures/course_app"
    result = CliRunner().invoke(
        app,
        [
            "study",
            "init",
            str(root),
            "--course",
            "Algorithms & Graphs",
            "--snapshot",
            str(example / "snapshot.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    (root / "app").mkdir()
    shutil.copyfile(example / "content.json", root / "app/content.json")
    from tum_mcp.study_build import build

    build(root, publish=False)
    # Keep the established fixture a legacy project to protect its supported contracts.
    (root / "app").rename(root / "study")
    return root


@pytest.fixture
def project(tmp_path: Path, built_project: Path) -> Path:
    return Path(shutil.copytree(built_project, tmp_path / "Course space Ω"))


@pytest.fixture
def exercise_project(project: Path, request: pytest.FixtureRequest) -> Path:
    """Reuse one source-bound exercise fixture across build and browser scenarios."""
    from tum_mcp.study_build import read_content
    from tum_mcp.study_store import load_state

    content = read_content(project)
    source = next(unit for unit in content.units if unit.key == "weighted").sources[0]
    name = "exercise-responses" if getattr(request, "param", None) == "responses" else "exercises"
    payload = json.loads((Path(__file__).parents[1] / f"fixtures/{name}.json").read_bytes())
    payload["course_key"] = load_state(project).course.key
    for exercise in payload["sets"][0]["exercises"]:
        exercise["sources"] = [source.model_dump(mode="json")]
        for block in (
            *exercise["statement"],
            *(b for a in exercise["solution"]["answers"] for b in a["blocks"]),
        ):
            block["sources"] = [source.key]
        for step in exercise["steps"]:
            for block in step.get("blocks", []):
                block["sources"] = [source.key]
            if step.get("check", {}).get("kind") == "plot":
                step["check"]["plot"]["sources"] = [source.key]
            if step.get("check", {}).get("kind") == "graph":
                step["check"]["graph"]["sources"] = [source.key]
    (project / "study/exercises.json").write_text(json.dumps(payload))
    return project
