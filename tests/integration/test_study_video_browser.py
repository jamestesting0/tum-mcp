import json
import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import httpx2
import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.study_preview import Handler, PreviewServer

STEM = "01_reusable-components"


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "extensions.json").write_text(
        '{"schema_version":1,"video_notes":true}', encoding="utf-8"
    )
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(config))
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "demo course"
    result = CliRunner().invoke(app, ["study", "demo", str(root), "--videos"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    return root


@pytest.fixture
def server(demo: Path) -> Iterator[str]:
    handler = partial(Handler, directory=str(demo / "app"))
    with PreviewServer(("127.0.0.1", 0), handler) as running:
        thread = Thread(target=running.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{running.server_port}"
        finally:
            running.shutdown()


def test_preview_serves_videos_with_ranges_and_keeps_records_private(
    demo: Path, server: str
) -> None:
    track = demo / f"videos/tracks/{STEM}.mp4"
    size = track.stat().st_size
    with httpx2.Client(trust_env=False, timeout=5) as client:
        index = client.get(server + "/videos/index.json").json()["videos"]
        assert index["components"]["track"] == f"videos/tracks/{STEM}.mp4"
        assert not index["components"]["narrated"]
        url = f"{server}/videos/tracks/{STEM}.mp4"
        whole = client.get(url)
        assert whole.status_code == 200 and whole.content == track.read_bytes()
        assert whole.headers["accept-ranges"] == "bytes"
        assert "media-src 'self'" in whole.headers["content-security-policy"]
        cases = {
            "bytes=0-9": (206, f"bytes 0-9/{size}", 10),
            "bytes=-4": (206, f"bytes {size - 4}-{size - 1}/{size}", 4),
            f"bytes={size - 2}-": (206, f"bytes {size - 2}-{size - 1}/{size}", 2),
            f"bytes=0-{size * 2}": (206, f"bytes 0-{size - 1}/{size}", size),
            f"bytes={size}-": (416, f"bytes */{size}", 0),
            "bytes=9-2": (200, None, size),
            "bytes=0-1,4-5": (200, None, size),
        }
        for header, (status, content_range, length) in cases.items():
            response = client.get(url, headers={"Range": header})
            assert response.status_code == status, header
            assert response.headers.get("content-range") == content_range, header
            assert len(response.content) == length, header
        head = client.head(url, headers={"Range": "bytes=0-9"})
        assert head.status_code == 206 and head.content == b""
        caption = client.get(f"{server}/videos/captions/{STEM}.vtt")
        assert caption.headers["content-type"] == "text/vtt; charset=utf-8"
        for path in (
            "/videos/manifest.json",
            "/videos/.build/video.lock",
            "/videos/storyboards/x.json",
            f"/videos/tracks/{STEM.upper()}.mp4",
            "/videos/tracks/%2e%2e/manifest.json",
            "/videos/tracks/a/b.mp4",
            "/videos/scenes/x.py",
        ):
            assert client.get(server + path).status_code == 404, path


def test_index_omits_missing_or_changed_files_and_survives_bad_manifests(
    demo: Path, server: str
) -> None:
    with httpx2.Client(trust_env=False, timeout=5) as client:
        poster = demo / f"videos/posters/{STEM}.jpg"
        poster.write_bytes(poster.read_bytes() + b"x")
        assert client.get(server + "/videos/index.json").json() == {"videos": {}}
        (demo / "videos/manifest.json").write_text("{not json", encoding="utf-8")
        response = client.get(server + "/videos/index.json")
        assert response.status_code == 200 and response.json() == {"videos": {}}
        (demo / "videos/manifest.json").unlink()
        assert client.get(server + "/videos/index.json").json() == {"videos": {}}


@pytest.fixture(scope="module")
def browsers() -> Iterator[dict]:
    from playwright.sync_api import sync_playwright

    from tum_mcp.moodle.browser_runtime import browser_driver
    from tum_mcp.moodle.browsers import discover_browsers

    choices = discover_browsers()
    assert choices, "The requested browser QA requires an existing Chromium browser."
    with browser_driver(choices[0]), sync_playwright() as playwright:
        found = {"chromium": playwright.chromium.launch(executable_path=choices[0].executable)}
        if Path(playwright.webkit.executable_path).exists():
            found["webkit"] = playwright.webkit.launch()
        try:
            yield found
        finally:
            for browser in found.values():
                browser.close()


browser_only = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def check_page(page, server: str) -> None:  # noqa: ANN001 - Playwright page
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(server + "/#components")
    panel = page.locator("section.video-note")
    panel.get_by_role("heading", name="Video explainer").wait_for()
    # The outline follows the late panel on its next refresh.
    entry = page.locator(".page-outline a", has_text="Video explainer")
    entry.wait_for(state="attached")
    assert entry.count() == 1
    chapters = panel.locator(".video-chapters button")
    assert chapters.count() == 2
    page.evaluate("document.querySelector('.video-note video').muted = true")
    chapters.nth(1).click()
    page.wait_for_function(
        "() => { const v = document.querySelector('.video-note video');"
        " return v.readyState >= 2 && v.currentTime >= 13 && !v.error; }",
        timeout=15000,
    )
    cues = page.evaluate(
        "() => new Promise(resolve => { const track = document.querySelector('.video-note track');"
        " track.track.mode = 'hidden';"
        " const done = () => resolve(track.track.cues ? track.track.cues.length : 0);"
        " if (track.readyState === 2) done(); else track.addEventListener('load', done); })"
    )
    assert cues > 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []


@browser_only
def test_chromium_plays_seeks_and_shows_captions(browsers: dict, demo: Path, server: str) -> None:
    for width in (390, 1440):
        context = browsers["chromium"].new_context(viewport={"width": width, "height": 900})
        check_page(context.new_page(), server)
        context.close()


@browser_only
def test_webkit_plays_through_range_requests(browsers: dict, demo: Path, server: str) -> None:
    if "webkit" not in browsers:
        pytest.skip("Playwright WebKit is not installed on this host.")
    context = browsers["webkit"].new_context(viewport={"width": 390, "height": 844})
    check_page(context.new_page(), server)
    context.close()


@browser_only
def test_a_slow_video_index_never_holds_back_the_page(browsers: dict, server: str) -> None:
    context = browsers["chromium"].new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    held: list = []
    page.route("**/videos/index.json", lambda route: held.append(route))
    page.goto(server + "/#components")
    page.get_by_role("heading", name="Reusable components").wait_for()
    # The page is readable while the index is still pending; the panel follows it.
    assert held and page.locator("section.video-note").count() == 0
    held[0].continue_()
    page.locator("section.video-note").wait_for()
    context.close()


@browser_only
def test_stale_videos_warn_and_hosted_sites_never_ask(
    browsers: dict, demo: Path, server: str
) -> None:
    course_browser = browsers["chromium"]
    manifest = json.loads((demo / "videos/manifest.json").read_text(encoding="utf-8"))
    manifest["videos"][STEM]["made_for_revision"] = "0" * 64
    (demo / "videos/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    context = course_browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.goto(server + "/#components")
    page.get_by_text("made for an earlier version of this topic").wait_for()
    context.close()
    data = demo / "app/data.mjs"
    original = data.read_bytes()
    data.write_bytes(
        original.replace(b"export default ", b"const data = ", 1)
        + b"data.hosted = true;\nexport default data;\n"
    )
    requests: list[str] = []
    context = course_browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.on("request", lambda request: requests.append(request.url))
    page.goto(server + "/#components")
    page.get_by_role("heading", name="Reusable components").wait_for()
    assert page.locator("section.video-note").count() == 0
    assert not any("/videos/" in url for url in requests)
    context.close()
