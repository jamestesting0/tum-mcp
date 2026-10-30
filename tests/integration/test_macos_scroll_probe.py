"""Temporary hosted macOS table keyboard diagnostic."""

import os
from pathlib import Path

import pytest
import study_browser_fixture
from playwright.sync_api import Browser, Page

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_MACOS_SCROLL_PROBE") != "1", reason="Explicit diagnostic only."
)


def test_repeated_table_keyboard_scrolling(
    course_browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = study_browser_fixture.table_layout_checks

    class ProbeDone(Exception):
        pass

    def repeat(page: Page, project: Path) -> None:
        page.context.add_init_script("""
          window.tableKeys = [];
          addEventListener('keydown', event => {
            if (event.key !== 'ArrowRight') return;
            const r = document.querySelector('.table-region');
            const item = {target:event.target.className, focus:document.hasFocus(),
              active:document.activeElement?.className, ctrl:event.ctrlKey,
              alt:event.altKey, meta:event.metaKey, shift:event.shiftKey};
            tableKeys.push(item);
            queueMicrotask(() => { item.prevented = event.defaultPrevented; });
            requestAnimationFrame(() => { item.nextFrameLeft = r?.scrollLeft;
              item.nextFrameActive = document.activeElement?.className;
              item.nextFrameWidth = r?.scrollWidth; item.nextFrameClient = r?.clientWidth; });
          });
        """)
        for index in range(100):
            print(f"macOS table probe {index + 1}/100", flush=True)
            original(page, project)
        raise ProbeDone

    monkeypatch.setattr(study_browser_fixture, "table_layout_checks", repeat)
    with pytest.raises(ProbeDone):
        study_browser_fixture.study_website(course_browser)
