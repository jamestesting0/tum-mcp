import json
import os
import shutil
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
        assert client.get(server + "/videos/index.json").json() == {"videos": {}, "exercises": {}}
        (demo / "videos/manifest.json").write_text("{not json", encoding="utf-8")
        response = client.get(server + "/videos/index.json")
        assert response.status_code == 200 and response.json() == {"videos": {}, "exercises": {}}
        (demo / "videos/manifest.json").unlink()
        assert client.get(server + "/videos/index.json").json() == {"videos": {}, "exercises": {}}


@pytest.fixture(scope="module")
def browsers() -> Iterator[dict]:
    from playwright.sync_api import sync_playwright

    from tum_mcp.moodle.browser_runtime import browser_driver, launch_loopback_browser
    from tum_mcp.moodle.browsers import discover_browsers

    choices = discover_browsers()
    assert choices, "The requested browser QA requires an existing Chromium browser."
    with browser_driver(choices[0]), sync_playwright() as playwright:
        found = {"chromium": launch_loopback_browser(playwright.chromium, choices[0])}
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


@pytest.fixture
def walkthrough_server(
    demo: Path,
    exercise_project: Path,
) -> Iterator[str]:
    from tum_mcp import video_project
    from tum_mcp.course_app_paths import app_path
    from tum_mcp.study_build import build
    from tum_mcp.study_store import load_state
    from tum_mcp.video_content import Manifest

    path = app_path(exercise_project, "exercises.json")
    content = json.loads(path.read_bytes())
    exercise = content["sets"][0]["exercises"][1]
    exercise["parts"] = ["(a)", "(b)"]
    exercise["part_blocks"] = {"(a)": "premise", "(b)": "conclusion"}
    original_statement = exercise["statement"][0]
    exercise["statement"] = [
        {**original_statement, "key": "premise", "title": "(a) Relaxation boundary"},
        {**original_statement, "key": "conclusion", "title": "(b) Minimum choice"},
    ]
    step = exercise["steps"][0]
    exercise["steps"] = [
        {**step, "key": "premise", "part": "(a)"},
        {**step, "key": "conclusion", "part": "(b)"},
    ]
    answer = exercise["solution"]["answers"][0]
    exercise["solution"]["answers"] = [
        {**answer, "label": "(a)"},
        {**answer, "label": "(b)"},
    ]
    path.write_text(json.dumps(content), encoding="utf-8")
    base = json.loads((demo / "videos/manifest.json").read_bytes())["videos"][STEM]
    receipts = {}
    for i, exercise in enumerate(content["sets"][0]["exercises"], 2):
        identity = f"sheet-1/{exercise['key']}"
        info = video_project.exercise_locators(exercise_project, identity)
        stem = f"{i:02d}_{exercise['key']}"
        fields = {
            key: value
            for key, value in base.items()
            if key not in {"unit", "unit_hash", "objectives"}
        }
        fields.update(
            stem=stem,
            exercise=info["exercise"],
            exercise_hash=info["exercise_hash"],
            made_for_revision=info["exercise_hash"],
            title=info["title"],
            answers=info["answers"],
            solution_origin=exercise["solution"]["origin"],
            source_references=exercise["sources"],
            prerequisites=[],
            chapters=[
                {**chapter, "answer": info["answers"][min(j, len(info["answers"]) - 1)]}
                for j, chapter in enumerate(base["chapters"])
            ],
        )
        fields["files"] = {}
        for kind, file in base["files"].items():
            relative = file["path"].replace(STEM, stem)
            target = exercise_project / "videos" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(demo / "videos" / file["path"], target)
            fields["files"][kind] = {**file, "path": relative}
        receipts[stem] = fields
    manifest = Manifest.model_validate(
        {
            "course_key": load_state(exercise_project).course.key,
            "videos": receipts,
        }
    )
    (exercise_project / "videos/manifest.json").write_text(manifest.model_dump_json())
    build(exercise_project, publish=False)
    handler = partial(Handler, directory=str(app_path(exercise_project, "index.html").parent))
    with PreviewServer(("127.0.0.1", 0), handler) as running:
        thread = Thread(target=running.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{running.server_port}"
        finally:
            running.shutdown()


@browser_only
@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_walkthrough_disclosure_never_autoplays_or_reveals_written_parts(
    browsers: dict,
    walkthrough_server: str,
    tmp_path: Path,
    width: int,
    theme: str,
) -> None:
    context = browsers["chromium"].new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    with page.expect_response("**/videos/index.json"):
        page.goto(walkthrough_server + "/#exercises/sheet-1/sample-minimum-proof")
    disclosure = (
        page.locator("details")
        .filter(has=page.locator("summary", has_text="Video solution (all parts)"))
        .last
    )
    disclosure.wait_for()
    page.evaluate("(theme) => { document.documentElement.dataset.theme = theme; }", theme)
    assert page.locator(".video-note video, .video-note source, .video-note a").count() == 0
    baseline = page.evaluate("JSON.stringify(localStorage)")
    disclosure.locator("summary").click()
    video = disclosure.locator("video")
    video.wait_for()
    assert video.evaluate("(v) => v.paused && v.currentTime === 0 && !v.autoplay")
    assert page.locator(".exercise-solution[open]").count() == 0
    assert page.evaluate("JSON.stringify(localStorage)") == baseline
    video.evaluate("(v) => { v.muted = true; }")
    page.evaluate("""() => {
      const v = document.querySelector('.video-note video');
      window.walkthroughSeek = new Promise(resolve =>
        v.addEventListener('seeked', resolve, {once:true}));
    }""")
    disclosure.locator(".video-chapters button").nth(1).click()
    page.evaluate("() => window.walkthroughSeek.then(() => true)")
    assert video.evaluate("(v) => v.currentTime >= 13 && !v.error")
    captions = page.evaluate("""() => new Promise(resolve => {
      const t = document.querySelector('.video-note track'); t.track.mode = 'hidden';
      const done = () => resolve(t.track.cues?.length || 0);
      if (t.readyState === 2) done(); else t.addEventListener('load', done, {once:true});
    })""")
    assert captions > 0
    screenshot = tmp_path / f"exercise-{width}-{theme}.png"
    video.scroll_into_view_if_needed()
    page.screenshot(path=str(screenshot))
    print(f"SCREENSHOT {screenshot}")
    paused = disclosure.evaluate("""d => new Promise(resolve => {
      const paused = () => queueMicrotask(() => resolve(d.querySelector('video').paused));
      d.addEventListener('toggle', paused, {once:true});
      d.open = false;
    })""")
    assert paused
    assert page.evaluate("JSON.stringify(localStorage)") == baseline
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    context.close()


@browser_only
def test_single_solution_mounts_lazily_and_unselected_problem_has_no_player(
    browsers: dict,
    walkthrough_server: str,
) -> None:
    context = browsers["chromium"].new_context()
    page = context.new_page()
    with page.expect_response("**/videos/index.json"):
        page.goto(walkthrough_server + "/#exercises/sheet-1/sample-relaxation")
    solution = page.locator("details").filter(has=page.locator("summary", has_text="Solution")).last
    solution.wait_for()
    assert solution.locator("video, source").count() == 0
    solution.locator("summary").click()
    solution.locator("video").wait_for()
    assert solution.locator("video").evaluate("(v) => v.paused && v.currentTime === 0")
    context.close()


@browser_only
def test_bare_exercise_keys_cannot_supply_another_targets_video(
    browsers: dict,
    walkthrough_server: str,
) -> None:
    context = browsers["chromium"].new_context()
    page = context.new_page()

    def wrong_target(route) -> None:
        response = route.fetch()
        data = response.json()
        entry = data["exercises"]["sheet-1/sample-relaxation"]
        route.fulfill(json={"videos": {}, "exercises": {"sample-relaxation": entry}})

    page.route("**/videos/index.json", wrong_target)
    with page.expect_response("**/videos/index.json"):
        page.goto(walkthrough_server + "/#exercises/sheet-1/sample-relaxation")
    solution = page.locator("details").filter(has=page.locator("summary", has_text="Solution")).last
    solution.locator("summary").click()
    assert solution.locator("video, source, .video-note").count() == 0
    context.close()


@browser_only
def test_exam_guided_solution_never_requests_video_index(
    browsers: dict,
    tmp_path: Path,
) -> None:
    from material_fixture import exam_document, exam_project, with_guided_paper

    from tum_mcp.study_build import build

    root = exam_project(tmp_path)
    (root / "app").mkdir()
    (root / "app/exam.json").write_text(json.dumps(with_guided_paper(exam_document(root))))
    build(root, publish=False)
    handler = partial(Handler, directory=str(root / "app"))
    with PreviewServer(("127.0.0.1", 0), handler) as running:
        thread = Thread(target=running.serve_forever, daemon=True)
        thread.start()
        try:
            context = browsers["chromium"].new_context()
            page = context.new_page()
            requests = []
            page.on("request", lambda request: requests.append(request.url))
            page.goto(f"http://127.0.0.1:{running.server_port}/#exam/paper/ws23-a")
            page.locator(".exam-card", has_text="Guided").click()
            page.get_by_role("heading", name="Question 1", exact=True).first.wait_for()
            page.locator("summary", has_text="Solution").last.click()
            assert page.locator(".video-note").count() == 0
            assert not any("/videos/" in url for url in requests)
            context.close()
        finally:
            running.shutdown()
