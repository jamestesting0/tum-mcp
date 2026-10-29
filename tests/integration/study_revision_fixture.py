"""Revision selection and shared-progress checks for the installed study app."""

import re

from playwright.sync_api import Page, expect


def expand_topic_categories(page: Page) -> None:
    """Open visible disclosure buttons in parent-before-child order."""
    picker = page.locator(".revision-topics")
    picker.wait_for()
    if picker.get_attribute("open") is None:
        picker.locator("summary").first.click()
    for control in page.locator("[data-topic-toggle]").all():
        if control.is_visible() and control.get_attribute("aria-expanded") == "false":
            control.click()


def topic_alignment_checks(page: Page, content: dict) -> None:
    """A leaf at one level lines up with a category at that same level."""
    first, nested = content["units"][:2]
    leaf = page.get_by_role("checkbox", name=first["title"], exact=True).bounding_box()
    category = page.get_by_role(
        "checkbox", name=f"Category: {' / '.join(nested['path'])}", exact=True
    ).bounding_box()
    parent = page.get_by_role(
        "checkbox", name=f"Category: {' / '.join(first['path'])}", exact=True
    ).bounding_box()
    assert leaf and category and parent
    assert abs(leaf["x"] - category["x"]) <= 1
    assert leaf["x"] > parent["x"]


def feedback_style_checks(page: Page) -> None:
    """Retry is visibly outlined; alternatives do not leave a blank disclosure gap."""
    retry = page.get_by_role("button", name="Try again", exact=True)
    border = retry.evaluate(
        "el => ({style:getComputedStyle(el).borderTopStyle,"
        "color:getComputedStyle(el).borderTopColor,height:el.getBoundingClientRect().height})"
    )
    assert border["style"] != "none" and border["color"] not in ("transparent", "rgba(0, 0, 0, 0)")
    assert border["height"] >= 44
    details = page.locator(".other-options")
    was_open = details.get_attribute("open") is not None
    if not was_open:
        details.locator("summary").click()
    gap = details.evaluate(
        "el => {const text=document.createRange();"
        'text.selectNodeContents(el.querySelector("summary"));'
        'return el.querySelector("li").getBoundingClientRect().top-'
        "text.getBoundingClientRect().bottom;}"
    )
    assert 0 <= gap <= 20
    if not was_open:
        details.locator("summary").click()


def practice_navigation_checks(page: Page, question_count: int) -> None:
    """Controls stay together beside the position and retain answers across moves."""
    feedback_style_checks(page)
    previous = page.get_by_role("button", name="Previous question", exact=True)
    following = page.get_by_role("button", name="Next question", exact=True)
    assert previous.is_disabled()
    legend = page.locator(".practice-question legend")
    legend.scroll_into_view_if_needed()
    before, after, prompt = previous.bounding_box(), following.bounding_box(), legend.bounding_box()
    assert before and after and prompt
    assert max(before["y"] + before["height"], after["y"] + after["height"]) <= prompt["y"]
    assert 0 <= after["x"] - before["x"] - before["width"] <= 12
    for _ in range(question_count - 1):
        following.click()
        assert page.evaluate("document.activeElement.matches('.practice-question legend')")
    assert following.is_disabled()
    for _ in range(question_count - 1):
        previous.click()
    assert previous.is_disabled()
    assert page.get_by_role("heading", name="Correct", exact=True).is_visible()


def option_order_checks(page: Page, content: dict) -> None:
    """Options keep one shuffled order per question, so authored position gives nothing away."""
    moved = False
    for unit in content["units"]:
        page.goto(f"https://study.invalid/#{unit['key']}/practice")
        for index, question in enumerate(unit["questions"]):
            expect(page.locator(".practice-meta p.small").first).to_have_text(
                re.compile(rf"^{index + 1} / ")
            )
            radios = page.locator(".practice-question input[type=radio]")
            rendered = radios.evaluate_all("inputs => inputs.map(input => input.value)")
            authored = [option["key"] for option in question["options"]]
            assert sorted(rendered) == sorted(authored)
            moved |= rendered != authored
            if index == 0:
                page.reload()
                expect(radios).to_have_count(len(authored))
                again = radios.evaluate_all("inputs => inputs.map(input => input.value)")
                assert again == rendered
            if index < len(unit["questions"]) - 1:
                page.get_by_role("button", name="Next question", exact=True).click()
    assert moved


def outline_position_checks(page: Page, content: dict) -> None:
    """Choosing a lesson low in a long outline keeps the outline where the student left it."""
    last = content["units"][-1]
    page.goto(f"https://study.invalid/#{content['units'][0]['key']}/content")
    page.locator("h1").wait_for()
    body = page.locator(".sidebar-body")
    page.evaluate(
        "document.querySelectorAll('.sidebar .unit-group').forEach(g => { g.open = true; })"
    )
    assert body.evaluate("el => el.scrollHeight > el.clientHeight")
    body.evaluate("el => { el.scrollTop = el.scrollHeight; }")
    before = body.evaluate("el => el.scrollTop")
    page.locator(f'a.unit-link[href="#{last["key"]}/content"]').click()
    page.get_by_role("heading", name=last["title"], exact=True).wait_for()
    # Only the nudge that keeps the chosen entry fully visible may move it.
    assert body.evaluate("el => el.scrollTop") > before / 2
    current = page.locator('.sidebar-body [aria-current="page"]').bounding_box()
    frame = body.bounding_box()
    assert current and frame
    assert (
        frame["y"] <= current["y"]
        and current["y"] + current["height"] <= frame["y"] + frame["height"]
    )


def revision_checks(page: Page, content: dict) -> None:
    """Selection pools existing items without inventing a second progress namespace."""
    units = content["units"][:2]
    if not page.get_by_role("link", name="Revision", exact=True).is_visible():
        page.get_by_role("button", name="Expand course outline", exact=True).click()
    page.get_by_role("link", name="Revision", exact=True).click()
    page.get_by_role("heading", name="Revision", exact=True).wait_for()
    assert page.get_by_role("tab").count() == 2
    # Revision covers every topic until the student chooses; an explicit clear is kept.
    assert page.locator('[data-selection="topic"]:checked').count() == len(content["units"])
    expand_topic_categories(page)
    page.get_by_role("button", name="Clear", exact=True).click()
    assert page.get_by_text("Select topics to start revising.", exact=True).is_visible()
    topic_alignment_checks(page, content)
    for unit in units:
        page.get_by_role("checkbox", name=unit["title"], exact=True).check()
    assert page.evaluate("document.activeElement.type") == "checkbox"
    category = page.get_by_role("checkbox", name="Category: Algorithms / Traversals", exact=True)
    parent = page.get_by_role("checkbox", name="Category: Algorithms", exact=True)
    assert category.evaluate("input => input.indeterminate")
    category.check()
    other_group = any(
        unit.get("path", [])[:1] == ["Algorithms"]
        and unit.get("path", [])[:2] != ["Algorithms", "Traversals"]
        for unit in content["units"]
    )
    assert parent.is_checked() != other_group
    assert parent.evaluate("input => input.indeterminate") == other_group
    last_topic = page.get_by_role("checkbox", name=content["units"][2]["title"], exact=True)
    last_topic.uncheck()
    assert parent.evaluate("input => input.indeterminate")
    parent.check()
    parent.uncheck()
    assert not page.get_by_role("checkbox", name=units[1]["title"], exact=True).is_checked()
    assert page.get_by_role("checkbox", name=units[0]["title"], exact=True).is_checked()
    category.press("Space")
    assert parent.is_checked() != other_group
    last_topic.uncheck()
    cards = sum(len(unit["flashcards"]) for unit in units)
    questions = sum(len(unit["questions"]) for unit in units)
    assert page.get_by_role("tab", name=f"Flashcards · {cards}", exact=True).is_visible()
    page.locator(".flashcard").click()
    page.get_by_role("button", name="Got it", exact=True).click()
    page.get_by_role("tab", name=f"Practice · {questions}", exact=True).click()
    question = units[0]["questions"][0]
    correct = next(o for o in question["options"] if o["key"] == question["correct"])
    page.get_by_role("radio", name=correct["text"], exact=True).check()
    page.get_by_role("button", name="Check answer", exact=True).click()
    practice_navigation_checks(page, questions)
    # The same answer remains checked in the original unit, including after retry.
    page.goto("https://study.invalid/#" + units[0]["key"] + "/practice")
    assert page.get_by_role("heading", name="Correct", exact=True).is_visible()
    page.get_by_role("button", name="Try again", exact=True).click()
    assert page.evaluate("document.activeElement.matches('.practice-question legend')")
    page.goto("https://study.invalid/#revision?view=practice")
    assert page.get_by_role("button", name="Check answer", exact=True).is_disabled()
    page.get_by_role("tab", name="Flashcards", exact=False).click()
    # The earlier rating advanced the pooled deck; return to the rated first card.
    page.get_by_role("button", name="Previous card (Left arrow)", exact=True).click()
    if page.locator(".flashcard").get_attribute("data-revealed") != "true":
        page.locator(".flashcard").click()
    assert (
        page.get_by_role("button", name="Got it", exact=True).get_attribute("aria-pressed")
        == "true"
    )
    for _ in units[0]["flashcards"]:
        page.get_by_role("button", name="Next card (Right arrow)", exact=True).click()
    prompt = page.locator(".card-front .recall-prompt")
    assert prompt.inner_text() == units[1]["flashcards"][0]["front"]
    page.locator(".flashcard").click()
    page.get_by_role("button", name="Again", exact=True).click()
    assert page.get_by_role("radio", name="To review · 1", exact=True).is_visible()
    # Deselect from beyond the new deck's bounds: reset position and hide the answer.
    page.locator(".revision-topics > summary").click()
    page.get_by_role("checkbox", name=units[0]["title"], exact=True).uncheck()
    assert page.locator(".flashcard").get_attribute("data-revealed") == "false"
    assert page.locator("[data-flashcards] .recall-meta").inner_text().startswith("1 /")
    page.reload()
    page.get_by_role("heading", name="Revision", exact=True).wait_for()
    page.locator(".revision-topics > summary").click()
    expand_topic_categories(page)
    assert not page.get_by_role("checkbox", name=units[0]["title"], exact=True).is_checked()
    assert page.get_by_role("checkbox", name=units[1]["title"], exact=True).is_checked()
    page.get_by_role("button", name="Clear", exact=True).click()
    assert not page.locator(".flashcard").count()
    page.get_by_role("button", name="Select all", exact=True).click()
    assert page.locator('[data-selection="topic"]').count() == len(content["units"])
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # Reset lives on the course home and needs an explicit choice in the app dialog.
    reset_dialog = page.get_by_role("dialog", name="Reset progress?", exact=True)
    page.goto("https://study.invalid/#home")
    page.get_by_role("button", name="Reset progress", exact=True).click()
    reset_dialog.get_by_role("button", name="Cancel", exact=True).click()
    page.goto("https://study.invalid/#revision?view=flashcards")
    page.locator(".flashcard").click()
    assert (
        page.get_by_role("button", name="Got it", exact=True).get_attribute("aria-pressed")
        == "true"
    )
    page.goto("https://study.invalid/#home")
    page.get_by_role("button", name="Reset progress", exact=True).click()
    reset_dialog.get_by_role("button", name="Reset", exact=True).click()
    page.goto("https://study.invalid/#revision?view=flashcards")
    assert page.locator('[data-selection="topic"]:checked').count() == len(content["units"])
    page.locator(".flashcard").click()
    assert (
        page.get_by_role("button", name="Got it", exact=True).get_attribute("aria-pressed")
        == "false"
    )


def learning_flow_checks(page: Page, content: dict) -> None:
    """A phone student resumes from home, finishes a practice set and reviews misses."""
    unit, following = content["units"][:2]
    page.goto("https://study.invalid/")
    page.get_by_role("link", name=f"Start: {unit['title']}", exact=True).click()
    page.get_by_role("heading", name=unit["title"], exact=True).wait_for()
    page.get_by_role("button", name="Expand course outline", exact=True).click()
    for folder in following.get("path", []):
        page.locator(".unit-group:not([open]) > summary", has_text=folder).first.click()
    page.locator(f'a.unit-link[href="#{following["key"]}/content"]').click()
    page.get_by_role("heading", name=following["title"], exact=True).wait_for()
    assert page.locator("html").get_attribute("data-outline") == "collapsed"
    heading = page.locator("h1").bounding_box()
    assert heading and heading["y"] < 200
    page.goto(f"https://study.invalid/#{unit['key']}/flashcards")
    page.locator(".flashcard").click()
    page.get_by_role("button", name="Again", exact=True).click()
    page.goto(f"https://study.invalid/#{unit['key']}/practice")
    questions = unit["questions"]
    for index, question in enumerate(questions):
        choice = next(
            option
            for option in question["options"]
            if (option["key"] == question["correct"]) == (index > 0)
        )
        page.get_by_role("radio", name=choice["text"], exact=True).check()
        page.get_by_role("button", name="Check answer", exact=True).click()
        assert page.get_by_role("button", name="Check answer", exact=True).count() == 0
        if index == 0:
            # Retrying with the revealed answer is practice; the first miss stays for review.
            page.get_by_role("button", name="Try again", exact=True).click()
            right = next(o for o in question["options"] if o["key"] == question["correct"])
            page.get_by_role("radio", name=right["text"], exact=True).check()
            page.get_by_role("button", name="Check answer", exact=True).click()
            assert page.get_by_role("heading", name="Correct", exact=True).is_visible()
        if index < len(questions) - 1:
            page.get_by_role("button", name="Continue", exact=True).click()
            assert page.evaluate("document.activeElement.matches('.practice-question legend')")
    summary = page.locator(".practice-summary")
    correct = f"{len(questions) - 1} of {len(questions)} correct"
    assert summary.get_by_text(correct, exact=True).is_visible()
    review_row = summary.get_by_role("button").first
    assert review_row.get_by_text("Missed", exact=True).is_visible()
    assert review_row.get_by_text("Review", exact=True).is_visible()
    assert review_row.locator(".summary-action svg").is_visible()
    boundary = review_row.evaluate("el => getComputedStyle(el).borderTopColor")
    assert boundary not in ("transparent", "rgba(0, 0, 0, 0)")
    before_url = page.url
    review_row.click()
    review = page.get_by_role("dialog", name=questions[0]["prompt"], exact=True)
    assert review.is_visible()
    # The list keeps the first miss; the dialog shows the corrected retry the student just made.
    assert review.get_by_text("Your answer · Correct", exact=True).is_visible()
    assert page.locator(".practice-meta").inner_text().startswith(f"{len(questions)} /")
    assert page.url == before_url
    page.keyboard.press("Escape")
    assert not review.count()
    assert review_row.evaluate("element => element === document.activeElement")
    page.goto("https://study.invalid/#home")
    page.get_by_role("link", name="Review 2 items", exact=True).click()
    expand_topic_categories(page)
    page.get_by_role("checkbox", name=unit["title"], exact=True).check()
    assert page.get_by_role("radio", name="To review · 2", exact=True).is_checked()
    assert page.get_by_role("tab", name="Flashcards · 1", exact=True).is_visible()
    page.get_by_role("tab", name="Practice · 1", exact=True).click()
    assert page.get_by_role("button", name="Check answer", exact=True).is_disabled()
    page.get_by_text("All items", exact=True).click()
    pooled = sum(len(item["questions"]) for item in content["units"])
    assert page.get_by_role("tab", name=f"Practice · {pooled}", exact=True).is_visible()


def identity_checks(page: Page, units: list[dict]) -> None:
    """Identical item IDs in different topics must not share ratings or checked answers."""
    page.goto("https://study.invalid/#revision?view=flashcards")
    page.locator(".flashcard").click()
    page.get_by_role("button", name="Got it", exact=True).click()
    for _ in units[0]["flashcards"][1:]:
        page.get_by_role("button", name="Next card (Right arrow)", exact=True).click()
    page.locator(".flashcard").click()
    page.get_by_role("button", name="Again", exact=True).click()
    for unit, rating in zip(units[:2], ("Got it", "Again"), strict=True):
        page.goto(f"https://study.invalid/#{unit['key']}/flashcards")
        page.locator(".flashcard").click()
        assert (
            page.get_by_role("button", name=rating, exact=True).get_attribute("aria-pressed")
            == "true"
        )
        page.goto(f"https://study.invalid/#{unit['key']}/practice")
        assert page.get_by_role("button", name="Check answer", exact=True).is_disabled()
        question = unit["questions"][0]
        correct = next(o for o in question["options"] if o["key"] == question["correct"])
        page.get_by_role("radio", name=correct["text"], exact=True).check()
        page.get_by_role("button", name="Check answer", exact=True).click()
    page.goto("https://study.invalid/#revision?view=practice")
    assert page.get_by_role("heading", name="Correct", exact=True).is_visible()
    for _ in units[0]["questions"]:
        page.get_by_role("button", name="Next question", exact=True).click()
    assert page.get_by_role("heading", name="Correct", exact=True).is_visible()
