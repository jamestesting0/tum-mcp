import io
import json
import os
import shutil
import zipfile
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import httpx2
import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.preview import Handler, PreviewServer
from tum_mcp.course.media import audio_project
from tum_mcp.course.media.audio import AudioManifest
from tum_mcp.errors import CampusError

SPEECH = Path(__file__).parents[1] / "fixtures/video/speech.wav"
# Made by `audio-notes publish` from one-second clips of speech.wav for script(); 10.45 s.
TRACK = Path(__file__).parents[1] / "fixtures/audio/structures.m4a"
browser_only = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    assert CliRunner().invoke(app, ["study", "demo", str(project)]).exit_code == 0
    (project / "audio").mkdir()
    (project / "audio/voice.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "narrator": {
                        "provider": "kokoro",
                        "route": "local",
                        "voice": "af_heart",
                        "language": "en-us",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return project


def script(project: Path, **changes: object) -> dict:
    found = audio_project.sources(project)
    concepts = {item["unit"]: item for item in found["exam"]["concepts"]}
    pattern = found["exam"]["patterns"][0]
    first, second = list(concepts)[:2]
    value = {
        "key": "structures",
        "stem": "01_structures",
        "title": "Structures",
        "voice": "narrator",
        "units": [
            {"kind": "concept", "unit": first},
            {"kind": "concept", "unit": second},
            {"kind": "pattern", "unit": pattern["unit"]},
        ],
        "chapters": [
            {
                "key": key,
                "title": f"Chapter {key}",
                "covers": [{"kind": kind, "unit": key, "locator": locator}],
                "sentences": [f"The first idea of {key} names its condition.", "Then it applies."],
            }
            for key, kind, locator in (
                (first, "concept", concepts[first]["locator"]),
                (second, "concept", concepts[second]["locator"]),
                (pattern["unit"], "pattern", pattern["locator"]),
            )
        ],
    }
    value.update(changes)
    folder = project / "audio/categories"
    folder.mkdir(exist_ok=True)
    (folder / "01_structures.json").write_text(json.dumps(value), encoding="utf-8")
    return value


class FakeWorker:
    def __init__(
        self, loudness: float = -16.2, output: Path = SPEECH, seconds: float = 1.5
    ) -> None:
        self.loudness, self.output, self.seconds = loudness, output, seconds
        self.track: dict = {}

    def __call__(self, request: dict, **_: object) -> dict:
        if request["action"] == "measure":
            return {"ok": True, "durations": {name: self.seconds for name in request["files"]}}
        self.track = request
        shutil.copyfile(self.output, request["output"])
        return {
            "ok": True,
            "probe": {
                "container": "mov,mp4,m4a,3gp,3g2,mj2",
                "audio_codec": "aac",
                "sample_rate": 48000,
                "channels": 1,
                "decoded_samples": int(request["total"] * 48000),
                "audio_duration": request["total"],
                "loudness_lufs": self.loudness,
                "true_peak_dbtp": -2.5,
                "chapters": request["chapters"],
                "tags": request["tags"],
            },
        }


def synthesize(project: Path) -> None:
    for item in audio_project.narration(project, "01_structures"):
        target = project / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SPEECH, target)


def test_check_reports_stale_missing_and_unspeakable_script(demo: Path) -> None:
    value = script(demo)
    assert audio_project.check(demo, "01_structures")["errors"] == []
    value["chapters"][0]["covers"][0]["locator"]["fingerprint"] = "1" * 64
    value["chapters"][1]["sentences"] = [r"It costs \(O(n)\) time, as the prepared example shows."]
    value["chapters"].pop()
    script(demo, **{key: value[key] for key in ("chapters",)})
    report = audio_project.check(demo, "01_structures")
    rules = {error.split(" ")[0] for error in report["errors"]}
    assert {"cover.changed", "speech.symbols", "coverage.missing"} <= rules
    assert any(w.startswith("speech.meta") for w in report["warnings"])
    assert any(w.startswith("reentry.pronoun") for w in report["warnings"])


def test_publish_installs_a_track_the_course_report_reviews(
    demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.media import video_runtime

    worker = FakeWorker()
    monkeypatch.setattr(video_runtime, "call_worker", worker)
    script(demo)
    review = demo / "audio/.build/review.md"
    review.parent.mkdir(parents=True)
    review.write_text("Script checked against each entry.\n", encoding="utf-8")
    with pytest.raises(CampusError, match="narration file"):
        audio_project.publish(demo, "01_structures", review)
    synthesize(demo)
    result = audio_project.publish(demo, "01_structures", review)

    assert [mark["title"] for mark in worker.track["chapters"]][0].startswith("Chapter")
    assert worker.track["audio"][0]["start"] == audio_project.LEAD_IN
    manifest = AudioManifest.model_validate_json((demo / "audio/manifest.json").read_bytes())
    receipt = manifest.categories["structures"]
    assert {unit.kind for unit in receipt.units} == {"concept", "pattern"}
    assert (demo / "audio" / receipt.track.path).is_file() and result["track"].endswith(".m4a")
    assert (demo / "audio/playlist.m3u").read_text(encoding="utf-8").splitlines()[1] == (
        "tracks/01_structures.m4a"
    )
    report = CliRunner().invoke(app, ["study", "report", str(demo), "--section", "review"])
    media = json.loads(report.output)["review"]["media"]
    item = next(entry for entry in media["items"] if entry["item"] == "audio/structures")
    assert item["artifact_ready"] and all(t.startswith("exam/") for t in item["source_targets"])
    assert media["invalid"] == [] and media["pending"] == []


def test_listen_flags_only_sentences_a_listener_would_miss(
    demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.media import listening, video_runtime

    monkeypatch.setattr(video_runtime, "call_worker", FakeWorker())
    script(demo)
    synthesize(demo)
    review = demo / "audio/.build/review.md"
    review.write_text("Checked.\n", encoding="utf-8")
    audio_project.publish(demo, "01_structures", review)
    timeline = json.loads((demo / "audio/.build/01_structures/timeline.json").read_text())
    said = [sentence["text"] for sentence in timeline["sentences"]]
    said[0] = said[0].replace(" its", "")
    said[1] = "Then"
    heard = [
        {
            "word": word,
            "start": sentence["start"] + 0.1 * i,
            "end": sentence["start"] + 0.1 * i + 0.08,
        }
        for sentence, text in zip(timeline["sentences"], said, strict=True)
        for i, word in enumerate(text.split())
    ]
    monkeypatch.setattr(listening, "_recognize", lambda *_: (heard, timeline["total"]))
    monkeypatch.setattr(listening, "_recheck", lambda *_: None)

    result = listening.listen_audio(demo, "01_structures")

    first, second = (f"{s['chapter']}/{s['sentence']}" for s in timeline["sentences"][:2])
    assert [s["key"] for s in result["flagged_sentences"]] == [second]
    assert any(flag.startswith(f"unclear {second}") for flag in result["flags"])
    assert not any(first in flag for flag in result["flags"])
    [evidence] = result["evidence"]
    assert evidence["kind"] == "listening" and evidence["intervals"][0]["end"] == timeline["total"]
    assert (demo / evidence["path"]).is_file()


def test_publish_refuses_a_track_off_the_loudness_target(
    demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.media import video_runtime

    monkeypatch.setattr(video_runtime, "call_worker", FakeWorker(loudness=-21.0))
    script(demo)
    synthesize(demo)
    review = demo / "audio/.build/review.md"
    review.write_text("Checked.\n", encoding="utf-8")
    with pytest.raises(CampusError, match="loudness"):
        audio_project.publish(demo, "01_structures", review)
    assert not (demo / "audio/manifest.json").exists()
    assert not (demo / "audio/tracks/01_structures.m4a").exists()


@pytest.fixture
def published(demo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from tum_mcp.course.media import video_runtime

    monkeypatch.setattr(video_runtime, "call_worker", FakeWorker(output=TRACK, seconds=1.0))
    script(demo)
    synthesize(demo)
    review = demo / "audio/.build/review.md"
    review.write_text("Checked.\n", encoding="utf-8")
    audio_project.publish(demo, "01_structures", review)
    return demo


@pytest.fixture
def server(published: Path) -> Iterator[str]:
    handler = partial(Handler, directory=str(published / "app"))
    with PreviewServer(("127.0.0.1", 0), handler) as running:
        Thread(target=running.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{running.server_port}"
        finally:
            running.shutdown()


def test_preview_serves_tracks_their_index_and_the_playlist(published: Path, server: str) -> None:
    with httpx2.Client(trust_env=False, timeout=10) as client:
        [track] = client.get(server + "/audio/index.json").json()["tracks"]
        assert track["kind"] == "exam" and track["track"] == "audio/tracks/01_structures.m4a"
        assert [len(chapter["recall"]) for chapter in track["chapters"]] == [1, 1, 1]
        starts = [sentence["start"] for sentence in track["sentences"]]
        assert len(starts) == 6 and starts == sorted(starts)
        part = client.get(server + "/" + track["track"], headers={"Range": "bytes=0-9"})
        assert part.status_code == 206 and part.headers["content-type"] == "audio/mp4"
        download = client.get(server + "/audio/playlist.zip")
        assert "attachment" in download.headers["content-disposition"]
        archive = zipfile.ZipFile(io.BytesIO(download.content))
        assert archive.namelist() == ["01_structures.m4a", "playlist.m3u", "README.txt"]
        assert archive.read("01_structures.m4a") == TRACK.read_bytes()
        assert "#EXTINF:10,Structures" in archive.read("playlist.m3u").decode()
        for path in ("manifest.json", "categories/01_structures.json", "tracks/..%2Fmanifest.json"):
            assert client.get(f"{server}/audio/{path}").status_code == 404, path
        # A track changed outside publish leaves the index and the download.
        with (published / "audio/tracks/01_structures.m4a").open("ab") as stream:
            stream.write(b"0")
        assert client.get(server + "/audio/index.json").json() == {"tracks": []}
        assert client.get(server + "/audio/playlist.zip").status_code == 404


@pytest.fixture(scope="module")
def chromium() -> Iterator:
    from playwright.sync_api import sync_playwright

    from tum_mcp.moodle.browser_runtime import browser_driver, launch_loopback_browser
    from tum_mcp.moodle.browsers import discover_browsers

    choices = discover_browsers()
    assert choices, "The requested browser QA requires an existing Chromium browser."
    with browser_driver(choices[0]), sync_playwright() as playwright:
        browser = launch_loopback_browser(playwright.chromium, choices[0])
        try:
            yield browser
        finally:
            browser.close()


@browser_only
def test_audio_workspace_reads_along_and_keeps_playing_elsewhere(chromium, server: str) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(server + "/#audio")
    row = page.locator(".audio-shelf .topic-row", has_text="Structures")
    row.wait_for()
    expect(page.locator(".audio-download")).to_have_attribute("href", "audio/playlist.zip")
    row.locator("a").click()
    page.locator(".audio-player").get_by_role("button", name="Play").click()
    sentences = page.locator(".audio-sentence")
    expect(sentences.first).to_have_attribute("aria-current", "true", timeout=10000)
    dock = page.locator(".audio-dock")
    expect(dock).to_be_hidden()
    # A sentence plays from its own start, and its chapter becomes the current one.
    sentences.nth(2).click()
    expect(sentences.nth(2)).to_have_attribute("aria-current", "true", timeout=10000)
    expect(page.locator(".audio-chapter").nth(1)).to_have_attribute("aria-current", "true")
    # Elsewhere in the app the mini player keeps the track going.
    page.goto(server + "/#home")
    expect(dock).to_be_visible()
    expect(dock.locator(".audio-dock-name")).to_have_text("Structures")
    dock.get_by_role("button", name="Pause").click()
    expect(dock.get_by_role("button", name="Play")).to_be_visible()
    # A reload keeps it ready where it stopped; closing it keeps it closed.
    page.reload()
    expect(dock).to_be_visible()
    dock.get_by_role("button", name="Close player").click()
    expect(dock).to_be_hidden()
    page.reload()
    page.locator(".workspace-picker").wait_for()
    expect(dock).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    context.close()


@browser_only
def test_hosted_sites_never_ask_for_audio(chromium, published: Path, server: str) -> None:  # noqa: ANN001
    data = published / "app/data.mjs"
    original = data.read_bytes()
    data.write_bytes(
        original.replace(b"export default ", b"const data = ", 1)
        + b"data.hosted = true;\nexport default data;\n"
    )
    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(server + "/#audio")
    page.get_by_text("Audio notes play in the local app.").wait_for()
    assert not any(url.startswith(server + "/audio/") for url in requests)
    assert page.locator(".audio-dock").count() == 0
    context.close()
