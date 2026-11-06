import json
import os
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from documents import content_file
from playwright.sync_api import Browser, expect
from pydantic import ValidationError

from tum_mcp.course.app.build import build
from tum_mcp.course.app.preview import Handler, PreviewServer
from tum_mcp.course.content.study import StudyContent
from tum_mcp.errors import CampusError

MEANING = "A quick estimate that helps decide which option to try first."


def add_gloss(project: Path) -> tuple[Path, dict]:
    path = content_file(project, "study")
    payload = json.loads(path.read_bytes())
    payload["annotations"] = [{"term": "rule of thumb", "meaning": MEANING}]
    return path, payload


def test_annotation_validation_distinguishes_glosses_from_core_definitions(project: Path) -> None:
    _, content = add_gloss(project)
    content["units"][0]["blocks"][0]["paragraphs"].append("Use a {{Rule of thumb}}.")
    assert StudyContent.model_validate(content).annotation_names() == {"rule of thumb"}
    content["units"][0]["title"] = "{{rule of thumb}}"
    with pytest.raises(ValidationError, match="explanatory prose"):
        StudyContent.model_validate(content)
    content["units"][0]["title"] = "Graphs"
    content["annotations"].append({"term": "Tentative distance", "meaning": MEANING})
    with pytest.raises(ValidationError, match="each term once"):
        StudyContent.model_validate(content)


def test_exercises_keep_official_statements_free_of_new_annotations(exercise_project: Path) -> None:
    path, content = add_gloss(exercise_project)
    path.write_text(json.dumps(content), encoding="utf-8")
    path = content_file(exercise_project, "exercises")
    exercises = json.loads(path.read_bytes())
    exercise = exercises["sets"][0]["exercises"][0]
    exercise["steps"][0]["explanation"] += " Use a {{rule of thumb}}."
    path.write_text(json.dumps(exercises), encoding="utf-8")
    build(exercise_project, publish=False)
    exercise["statement"].append(
        {
            "kind": "text",
            "paragraphs": ["Use a {{rule of thumb}}."],
            "sources": [exercise["sources"][0]["key"]],
        }
    )
    path.write_text(json.dumps(exercises), encoding="utf-8")
    with pytest.raises(CampusError, match="guide or solution prose"):
        build(exercise_project, publish=False)


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Owned browser QA."
)
def test_gloss_opens_and_dismisses_in_place(
    project: Path, course_browser: Browser, tmp_path: Path
) -> None:
    path, content = add_gloss(project)
    unit = next(unit for unit in content["units"] if unit["key"] == "weighted")
    text = next(block for block in unit["blocks"] if block["kind"] == "text")
    text["paragraphs"].append("Use a {{rule of thumb}} after checking {{tentative distance}}.")
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = course_browser.new_page(viewport={"width": 390, "height": 600}, has_touch=True)
        try:
            url = f"http://127.0.0.1:{server.server_port}/#weighted/content"
            page.goto(url)
            term = page.get_by_role("button", name="rule of thumb", exact=True)
            term.tap()
            bubble = page.get_by_text(MEANING, exact=True)
            expect(bubble).to_be_visible()
            if os.environ.get("TUM_MCP_QA_CAPTURE") == "1":
                page.screenshot(path=tmp_path / "gloss.png")
            box = bubble.bounding_box()
            assert box and 0 <= box["x"] <= 390 - box["width"]
            assert 0 <= box["y"] <= 600 - box["height"]
            expect(page.get_by_role("link", name="Open in Study")).to_have_count(0)
            term.focus()
            term.press("Escape")
            expect(term).to_be_focused()
            expect(bubble).to_have_count(0)
            term.press("Enter")
            expect(bubble).to_be_visible()
            page.get_by_role("button", name="tentative distance", exact=True).last.click()
            expect(page.get_by_role("link", name="Open in Study")).to_be_visible()
            assert page.url == url
        finally:
            page.close()
            server.shutdown()
            thread.join(timeout=3)
