"""The optional detour in an actual generated course, without changing the core journey."""

import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, expect
from study_comments_fixture import select_passage
from study_explore_fixture import add_explore

from tum_mcp.study_build import build
from tum_mcp.study_comments import read_comments

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned synthetic browser checks require opt-in.",
)


@pytest.fixture
def explore_url(project: Path) -> Iterator[str]:
    from tum_mcp.study_preview import Handler, PreviewServer

    add_explore(project)
    build(project, publish=False)
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "study"))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.parametrize("width", [320, 390, 768, 1440])
def test_explore_is_a_conditional_keyboard_accessible_detour(
    course_browser: Browser, explore_url: str, width: int
) -> None:
    with course_browser.new_context(viewport={"width": width, "height": 900}) as context:
        page = context.new_page()
        page.set_default_timeout(4000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(explore_url + "#bfs/content")
        expect(page.get_by_role("tab")).to_have_count(4)
        explore = page.get_by_role("tab", name="Explore", exact=True)
        page.get_by_role("tab", name="Content", exact=True).focus()
        page.keyboard.press("End")
        expect(explore).to_be_focused()
        expect(explore).to_have_attribute("aria-selected", "true")
        expect(page.locator("#panel-explore").get_by_text("Optional", exact=True)).to_have_count(0)
        expect(page.get_by_role("tab", name="Practice", exact=False)).not_to_contain_text(
            "Optional"
        )
        expect(
            page.get_by_role("heading", name="Where the idea came from", exact=True)
        ).to_be_visible()
        expect(page.locator("#panel-explore video,.explore-reading .video-slot")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator(".next-step a").click()
        expect(page.get_by_role("tab", name="Content", exact=True)).to_have_attribute(
            "aria-selected", "true"
        )
        page.goto(explore_url + "#graphs/content")
        expect(page.get_by_role("tab")).to_have_count(3)
        expect(page.get_by_role("tab", name="Explore", exact=True)).to_have_count(0)
        page.goto(explore_url + "#graphs/explore")
        expect(page).to_have_url(explore_url + "#graphs/content")
        expect(
            page.get_by_text("Explore is no longer available for this topic.", exact=True)
        ).to_be_visible()
        page.goto(explore_url + "#bfs/explore/origin/history")
        expect(page.get_by_role("heading", name="Historical context", exact=True)).to_be_focused()
        page.reload()
        expect(explore).to_have_attribute("aria-selected", "true")
        page.goto(explore_url + "#revision?view=explore")
        expect(page.get_by_role("tab")).to_have_count(2)
        expect(page.get_by_role("tab", name="Explore", exact=True)).to_have_count(0)
        assert not errors


def test_explore_does_not_replace_core_resume_or_enter_the_core_next_step(
    course_browser: Browser, explore_url: str
) -> None:
    with course_browser.new_context() as context:
        page = context.new_page()
        page.set_default_timeout(4000)
        page.goto(explore_url + "#bfs/flashcards")
        page.get_by_role("tab", name="Explore", exact=True).click()
        page.goto(explore_url + "#home")
        expect(page.locator(".resume")).to_have_attribute("href", "#bfs/flashcards")
        page.goto(explore_url + "#bfs/practice")
        expect(page.locator(".next-step")).not_to_contain_text("Explore")
        page.get_by_role("tab", name="Explore", exact=True).click()
        expect(page.locator(".next-step")).to_contain_text("Back to Content")
        expect(page.locator(".page-outline")).to_have_count(1)
        expect(page.locator(".contents-toggle")).to_have_count(1)


def test_explore_comments_are_scoped_and_survive_reload(
    course_browser: Browser, explore_url: str, project: Path
) -> None:
    with course_browser.new_context() as context:
        page = context.new_page()
        page.set_default_timeout(4000)
        page.goto(explore_url + "#bfs/explore")
        quote = select_passage(page, ".explore-reading .reading-material p")
        page.get_by_role("button", name="Comment", exact=True).click()
        dialog = page.get_by_role("dialog", name="Comment", exact=True)
        dialog.get_by_label("Comment", exact=True).fill("Explain this optional origin.")
        dialog.get_by_role("button", name="Save", exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(page.get_by_text("Explain this optional origin.", exact=True)).to_be_visible()
        stored = read_comments(project)
        assert stored["schema_version"] == 4
        anchor = stored["comments"][0]["anchor"]
        assert (anchor["view"], anchor["unit_key"], anchor["item_key"], anchor["block_key"]) == (
            "explore",
            "bfs",
            "origin",
            "history",
        )
        assert anchor["quote"] == quote
        page.reload()
        page.locator(".comment-marker").first.click()
        expect(page.get_by_text("Explain this optional origin.", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Content", exact=True).click()
        expect(page.locator("#panel-content .comment-marker")).to_have_count(0)
        page.get_by_role("tab", name="Explore", exact=True).click()
        expect(page.locator(".comment-marker")).to_have_count(1)


def test_duplicate_quotes_and_untitled_continuations_keep_their_optional_owner(
    course_browser: Browser, explore_url: str, project: Path
) -> None:
    import copy
    import json

    from tum_mcp.study_store import private_path

    path = project / "study/content.json"
    payload = json.loads(path.read_bytes())
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    continuation = {
        "key": "continuation",
        "kind": "text",
        "sources": ["explore-source"],
        "paragraphs": ["The identical continuation is supporting context."],
    }
    first = unit["explore"][0]
    first["blocks"].append(continuation)
    second = copy.deepcopy(first)
    second.update(key="other", title="Another optional item")
    unit["explore"].append(second)
    unit["blocks"][0]["paragraphs"].append(continuation["paragraphs"][0])
    ledger_path = private_path(project, "coverage.json")
    ledger = json.loads(ledger_path.read_bytes())
    refs = ledger["sources"][0]["outcomes"][0]["explore"]
    refs.append({"unit": "bfs", "item": "other"})
    path.write_text(json.dumps(payload))
    ledger_path.write_text(json.dumps(ledger))
    build(project, publish=False)
    with course_browser.new_context() as context:
        page = context.new_page()
        page.set_default_timeout(4000)
        page.goto(explore_url + "#bfs/explore")
        select_passage(page, '[data-explore-key="origin"] [data-block="continuation"] p')
        page.get_by_role("button", name="Comment", exact=True).click()
        dialog = page.get_by_role("dialog", name="Comment", exact=True)
        dialog.get_by_label("Comment", exact=True).fill("Only the first optional passage.")
        dialog.get_by_role("button", name="Save", exact=True).click()
        expect(dialog).not_to_be_visible()
        assert read_comments(project)["comments"][0]["anchor"]["block_key"] == "history"
        expect(page.locator('[data-explore-key="origin"] .comment-marker')).to_have_count(1)
        expect(page.locator('[data-explore-key="other"] .comment-marker')).to_have_count(0)
        page.get_by_label("More actions", exact=True).click()
        page.get_by_role("button", name="Edit", exact=True).click()
        dialog.get_by_label("Comment", exact=True).fill("Edited optional note.")
        dialog.get_by_role("button", name="Save", exact=True).click()
        expect(dialog).not_to_be_visible()
        page.get_by_role("button", name="Resolve", exact=True).click()
        expect(page.locator('.comment-marker[data-open-count="0"]')).to_have_count(1)
        assert read_comments(project)["comments"][0]["status"] == "resolved"
        page.get_by_role("tab", name="Content", exact=True).click()
        expect(page.locator("#panel-content .comment-marker")).to_have_count(0)
        # Reordering preserves a stable item's note; removing it must not attach the note
        # to an identical quote/block key in another item.
        unit["explore"].reverse()
        path.write_text(json.dumps(payload))
        build(project, publish=False)
        page.goto(explore_url + "#bfs/explore")
        page.reload()
        expect(page.locator('[data-explore-key="origin"] .comment-marker')).to_have_count(1)
        unit["explore"] = [second]
        refs[:] = [{"unit": "bfs", "item": "other"}]
        path.write_text(json.dumps(payload))
        ledger_path.write_text(json.dumps(ledger))
        build(project, publish=False)
        page.reload()
        expect(page.locator('[data-explore-key="other"] .comment-marker')).to_have_count(0)
        page.locator(".comment-marker").click()
        page.get_by_role("button", name="Resolved", exact=True).click()
        expect(page.get_by_text("Passage unavailable.", exact=True)).to_be_visible()
        assert read_comments(project)["comments"][0]["text"] == "Edited optional note."


def test_matching_video_key_never_attaches_a_core_player_to_explore(
    course_browser: Browser, explore_url: str, project: Path
) -> None:
    import json

    from tum_mcp.study_store import private_path

    path = project / "study/content.json"
    payload = json.loads(path.read_bytes())
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    unit["explore"][0]["key"] = "bfs"
    path.write_text(json.dumps(payload))
    ledger_path = private_path(project, "coverage.json")
    ledger = json.loads(ledger_path.read_bytes())
    ledger["sources"][0]["outcomes"][0]["explore"][0]["item"] = "bfs"
    ledger_path.write_text(json.dumps(ledger))
    build(project, publish=False)
    with course_browser.new_context() as context:
        page = context.new_page()
        page.set_default_timeout(4000)
        page.route(
            "**/videos/index.json",
            lambda route: route.fulfill(
                json={
                    "videos": {
                        "bfs": {
                            "title": "Core-only explainer",
                            "duration": 60,
                            "madeForRevision": "old",
                            "poster": "poster.png",
                            "track": "demo.mp4",
                            "captions": "demo.vtt",
                            "language": "en",
                            "chapters": [],
                            "transcript": "transcript.txt",
                        }
                    }
                }
            ),
        )
        page.goto(explore_url + "#bfs/explore")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#panel-explore .video-slot,#panel-explore .video-note")).to_have_count(
            0
        )
        page.get_by_role("tab", name="Content", exact=True).click()
        expect(page.locator("#panel-content video")).to_have_count(1)
        page.get_by_role("tab", name="Explore", exact=True).click()
        expect(page.locator("#panel-explore .video-slot,#panel-explore video")).to_have_count(0)


def test_optional_only_edits_and_removal_preserve_saved_core_ratings(
    course_browser: Browser, explore_url: str, project: Path
) -> None:
    import json

    from tum_mcp.study_store import private_path

    with course_browser.new_context() as context:
        page = context.new_page()
        page.set_default_timeout(4000)
        page.goto(explore_url + "#bfs/flashcards")
        page.locator(".flashcard").click()
        page.locator('[data-card-action="got"]').click()
        path = project / "study/content.json"
        payload = json.loads(path.read_bytes())
        unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
        unit["explore"][0]["blocks"][0]["paragraphs"] = ["Reviewed, updated optional reading."]
        path.write_text(json.dumps(payload))
        build(project, publish=False)
        page.reload()
        page.locator(".flashcard").click()
        expect(page.locator('[data-card-action="got"]')).to_have_attribute("aria-pressed", "true")
        page.goto(explore_url + "#bfs/explore/missing/missing")
        expect(
            page.get_by_text(
                "That supporting passage is no longer here. Choose from the material below.",
                exact=True,
            )
        ).to_be_visible()
        unit.pop("explore")
        path.write_text(json.dumps(payload))
        private_path(project, "coverage.json").unlink()
        build(project, publish=False)
        page.reload()
        expect(page).to_have_url(explore_url + "#bfs/content")
        expect(page.get_by_role("tab")).to_have_count(3)
        page.get_by_role("tab", name="Flashcards", exact=False).click()
        page.locator(".flashcard").click()
        expect(page.locator('[data-card-action="got"]')).to_have_attribute("aria-pressed", "true")
