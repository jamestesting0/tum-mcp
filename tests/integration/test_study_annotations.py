import json
import os
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from documents import content_file
from playwright.sync_api import Browser, expect

from tum_mcp.course.app.build import build, current_data
from tum_mcp.course.app.preview import Handler, PreviewServer
from tum_mcp.course.checks.report import term_flags
from tum_mcp.course.content.study import StudyContent
from tum_mcp.course.content.terms import TermList
from tum_mcp.errors import CampusError

FIXTURES = Path(__file__).parents[1] / "fixtures"

MEANING = "A quick estimate that helps decide which option to try first."


def add_gloss(project: Path) -> tuple[Path, dict]:
    path = content_file(project, "study")
    payload = json.loads(path.read_bytes())
    (project / "app/terms.json").write_text(
        json.dumps(
            {
                "pairs": [{"en": "tentative distance", "de": "vorläufige Distanz"}],
                "glosses": [{"term": "rule of thumb", "meaning": MEANING}],
            }
        ),
        encoding="utf-8",
    )
    return path, payload


def app_data(project: Path) -> dict:
    module = current_data(project).decode()
    return json.loads(module.removeprefix("export default ").rstrip().removesuffix(";"))


def test_listed_terms_are_marked_once_per_unit_outside_code_and_math(project: Path) -> None:
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    # A course from before the term list keeps its glosses: they move into app/terms.json.
    content["annotations"] = [{"term": "rule of thumb", "meaning": MEANING}]
    first, second = content["units"][:2]
    first["blocks"][0]["paragraphs"].append(
        "A rule of thumb helps; `rule of thumb` stays code. Another Rule of thumb, "
        "then the chain rules, Kettenregel and \\(chain rule\\)."
    )
    second["blocks"][0]["paragraphs"].append("The chain rule again.")
    path.write_text(json.dumps(content), encoding="utf-8")
    (project / "app/terms.json").write_text(
        json.dumps({"pairs": [{"en": ["chain rule", "chain rules"], "de": "Kettenregel"}]}),
        encoding="utf-8",
    )

    data = app_data(project)

    assert "annotations" not in json.loads(path.read_bytes())
    terms = json.loads((project / "app/terms.json").read_bytes())
    assert terms["glosses"] == [{"term": "rule of thumb", "meaning": MEANING}]
    units = {unit["key"]: unit for unit in data["units"]}
    assert units[first["key"]]["blocks"][0]["paragraphs"][-1] == (
        "A {{rule of thumb}} helps; `rule of thumb` stays code. Another Rule of thumb, "
        "then the {{chain rules}}, Kettenregel and \\(chain rule\\)."
    )
    assert units[second["key"]]["blocks"][0]["paragraphs"][-1] == "The {{chain rule}} again."
    assert data["terms"]["kettenregel"] == {"pair": {"en": "chain rule"}}
    assert data["terms"]["chain rules"] == {"pair": {"de": "Kettenregel"}}
    assert data["terms"]["rule of thumb"] == {"meaning": MEANING}


def test_a_term_is_glossed_or_defined_not_both(project: Path) -> None:
    (project / "app/terms.json").write_text(
        json.dumps({"glosses": [{"term": "Tentative distance", "meaning": MEANING}]}),
        encoding="utf-8",
    )
    with pytest.raises(CampusError, match="not both"):
        build(project, publish=False)


def test_translated_exercise_statements_show_their_source_terms(exercise_project: Path) -> None:
    add_gloss(exercise_project)
    path = content_file(exercise_project, "exercises")
    exercises = json.loads(path.read_bytes())
    exercise = exercises["sets"][0]["exercises"][0]
    exercise["statement"].append(
        {
            "kind": "text",
            "paragraphs": ["Compare each tentative distance."],
            "sources": [exercise["sources"][0]["key"]],
        }
    )
    path.write_text(json.dumps(exercises), encoding="utf-8")
    statement = app_data(exercise_project)["exercises"]["sets"][0]["exercises"][0]["statement"]
    assert statement[-1]["paragraphs"] == ["Compare each {{tentative distance}}."]


def test_a_listed_term_no_prose_uses_is_flagged() -> None:
    terms = TermList.model_validate(
        {
            "pairs": [
                {"en": "chain rule", "de": "Kettenregel"},
                {"en": ["queue", "queues"], "de": "Warteschlange"},
            ]
        }
    )
    unit = StudyContent.model_validate(
        json.loads((FIXTURES / "course_app/content.json").read_bytes())
    )
    flags = term_flags(terms, unit)
    assert [flag["flag"] for flag in flags] == ["unused_term"]
    assert "chain rule" in str(flags[0]["detail"])


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
            # The definition shows its German form first; the trigger already names the term.
            definition = page.locator(".term-bubble").last
            expect(definition.locator(".term-source").first).to_have_text(
                "Germanvorläufige Distanz"
            )
            expect(definition.locator(":scope > :first-child")).to_have_class("term-source")
            assert page.url == url
        finally:
            page.close()
            server.shutdown()
            thread.join(timeout=3)
