import json
import shutil
import stat
from pathlib import Path

import pytest
from filelock import FileLock

from tum_mcp import video_project as project
from tum_mcp.errors import CampusError
from tum_mcp.video_content import Storyboard
from tum_mcp.video_runtime import RuntimeStatus

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLIP = FIXTURES / "video/clip.mp4"
TONE = FIXTURES / "video/tone.wav"
POSTER = FIXTURES / "video/poster.jpg"
STEM = "01_follow-the-frontier"
SCENE = """from manim import *
from vnotes import NotesScene


class C01(NotesScene):
    def construct(self):
        with self.beat("b01") as b:
            self.play(FadeIn(self.label("start")), run_time=b.share(0.5))
        with self.beat("b02") as b:
            self.wait(b.share(0.5))
"""


class FakeRuntime:
    def __init__(self) -> None:
        self.layout: list[dict] = []
        self.renders = 0

    def __call__(self, request: dict, **_: object) -> dict:
        action = request["action"]
        if action == "measure":
            return {"ok": True, "durations": {name: 1.6 for name in request["files"]}}
        if action == "render":
            run = Path(request["run"])
            timing = json.loads((run / "timing.json").read_text())
            beats = [b for b in timing["beats"] if b["chapter"] == request["chapter"]]
            fps = 15 if request["quality"] == "draft" else 30
            frames = round((beats[-1]["start"] + beats[-1]["duration"]) * fps) - round(
                beats[0]["start"] * fps
            )
            target = run / "chapters" / f"{request['chapter']}.mp4"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(CLIP, target)
            self.renders += 1
            board = json.loads((run / "storyboard.json").read_text())
            waived = {
                beat["key"]
                for chapter in board["chapters"]
                for beat in chapter["beats"]
                if beat.get("layout_waiver")
            }
            layout = [
                {**item, "rule": item["rule"] + (".waived" if item["beat"] in waived else "")}
                for item in self.layout
            ]
            return {
                "ok": True,
                "chapter": request["chapter"],
                "frames": frames,
                "duration": frames / fps,
                "layout": layout,
            }
        if action == "assemble":
            shutil.copyfile(CLIP, request["output"])
            shutil.copyfile(POSTER, request["poster"])
            final = request["quality"] == "final"
            fps = 30 if final else 15
            duration = sum(item["frames"] for item in request["chapters"]) / fps
            probe = {
                "container": "mov,mp4,m4a,3gp,3g2,mj2",
                "video_codec": "h264",
                "pix_fmt": "yuv420p",
                "width": 1920 if final else 854,
                "height": 1080 if final else 480,
                "fps": float(fps),
                "video_duration": duration,
            }
            if request["audio"]:
                probe.update(
                    audio_codec="aac",
                    sample_rate=48000,
                    channels=1,
                    audio_duration=duration,
                    loudness_lufs=-16.1,
                    true_peak_dbtp=-2.0,
                )
            return {"ok": True, "probe": probe}
        if action == "frames":
            Path(request["output"]).write_bytes(b"\x89PNG\r\n\x1a\n")
            return {"ok": True, "sheet": request["output"]}
        raise AssertionError(action)


@pytest.fixture
def course(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "course"
    (root / "app").mkdir(parents=True)
    shutil.copyfile(FIXTURES / "course_app/content.json", root / "app/content.json")
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    return root


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeRuntime:
    fake = FakeRuntime()
    ready = RuntimeStatus(supported=True, installed=True, profile="test", reason="ready")
    monkeypatch.setattr("tum_mcp.video_runtime.call_worker", fake)
    monkeypatch.setattr("tum_mcp.video_runtime.status", lambda: ready)
    monkeypatch.setattr("tum_mcp.video_runtime.python_path", lambda: tmp_path / "python")
    monkeypatch.setattr(
        "tum_mcp.video_runtime.render_profile", lambda: "test-0-aaaaaaaaaaaa-bbbbbbbbbbbb"
    )
    return fake


def content_json(root: Path) -> dict:
    return json.loads((root / "app/content.json").read_text(encoding="utf-8"))


def write_content(root: Path, value: dict) -> None:
    (root / "app/content.json").write_text(json.dumps(value), encoding="utf-8")


def prepare(root: Path, tmp_path: Path) -> None:
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit": "bfs",
                        "decision": "video",
                        "reason": "The traversal is a moving process.",
                    },
                    {
                        "unit": "dfs",
                        "decision": "text-first",
                        "reason": "Mostly a comparison table.",
                    },
                ]
            }
        )
    )
    plan = project.plan(root, selection)
    assert [item.stem for item in plan.videos] == [STEM, None]
    info = project.unit_locators(root, "bfs")
    refs = {item["ref"]: item for item in info["locators"]}
    question = next(item for item in info["locators"] if item["kind"] == "question")
    objective = content_json(root)["units"][1]["questions"][0]["objective"]
    board = {
        "video": STEM,
        "unit": "bfs",
        "unit_hash": info["unit_hash"],
        "title": "Breadth-first search",
        "language": "en",
        "objectives": [objective],
        "chapters": [
            {
                "key": "c01",
                "title": "Layers",
                "beats": [
                    {
                        "key": "b01",
                        "kind": "hook",
                        "narration": ["Where does the search go first?"],
                        "intent": "Start node.",
                        "locators": [
                            {k: refs["summary"][k] for k in ("kind", "ref", "fingerprint")}
                        ],
                        "on_screen": [{"key": "start", "kind": "label", "text": "s"}],
                    },
                    {
                        "key": "b02",
                        "kind": "question",
                        "narration": ["Pause and choose an answer."],
                        "pause_s": 2,
                        "question": question["ref"],
                        "intent": "Ask.",
                        "locators": [{k: question[k] for k in ("kind", "ref", "fingerprint")}],
                    },
                ],
            }
        ],
    }
    (root / "videos/storyboards").mkdir(parents=True)
    (root / f"videos/storyboards/{STEM}.json").write_text(json.dumps(board))
    (root / f"videos/scenes/{STEM}").mkdir(parents=True)
    (root / f"videos/scenes/{STEM}/chapters.py").write_text(SCENE)
    voice = json.loads((root / "videos/voice.json").read_text())
    voice["profiles"] = {
        "narrator": {"provider": "kokoro", "route": "local", "voice": "af_heart", "language": "en"}
    }
    (root / "videos/voice.json").write_text(json.dumps(voice))


def narrate(root: Path) -> None:
    for item in project.narration(root, STEM, "narrator"):
        target = root / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TONE, target)
    project.timing(root, STEM, profile="narrator", silent=False)


def review(tmp_path: Path) -> Path:
    path = tmp_path / "review.md"
    path.write_text("Every beat traced to its locator; no added claims.\n")
    return path


def test_full_flow_publishes_a_checked_final_video(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    prepare(course, tmp_path)
    assert project.check(course, STEM).errors == ()
    working = course / f"videos/.build/{STEM}/transcript.txt"
    assert working.read_text().startswith("Breadth-first search")
    assert not (course / f"videos/narration/{STEM}.txt").exists()
    narrate(course)
    draft = project.render(course, STEM, quality="draft", jobs=2, max_minutes=None, run=None)
    assert draft["ok"], draft
    with pytest.raises(CampusError, match="final-quality"):
        project.publish(
            course, STEM, draft["run"], teaching_review=review(tmp_path), visual_review="performed"
        )
    final = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert final["ok"] and "layout.clear" in final["check"]["passed"]
    receipt = project.publish(
        course, STEM, final["run"], teaching_review=review(tmp_path), visual_review="performed"
    )
    track = course / f"videos/tracks/{STEM}.mp4"
    assert track.read_bytes() == CLIP.read_bytes()
    assert stat.S_IMODE(track.stat().st_mode) == 0o600
    assert receipt.narrated and receipt.files["captions"].path == f"captions/{STEM}.vtt"
    state = project.inspect(course, verify=True)
    rows = {row["unit"]: row for row in state["units"]}
    assert rows["bfs"]["published"] == "current" and rows["dfs"]["decision"] == "text-first"
    assert f"tracks/{STEM}.mp4" in (course / "videos/playlist.m3u").read_text()
    assert "text-first (Mostly a comparison table.)" in (course / "videos/COVERAGE.md").read_text()
    before = runtime.renders
    again = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert again["ok"] and runtime.renders == before
    assert all(item["cached"] for item in again["chapters"].values())
    # Revising and checking the storyboard never touches the published transcript.
    board_path = course / f"videos/storyboards/{STEM}.json"
    board = json.loads(board_path.read_text())
    board["title"] = "Breadth-first search, revised"
    board_path.write_text(json.dumps(board))
    assert project.check(course, STEM).errors == ()
    row = project.inspect(course, stem=STEM, verify=True)["units"][0]
    assert row["published"] == "current" and row["edited_since_publication"]


def test_content_edits_are_classified_and_acknowledged(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    prepare(course, tmp_path)
    narrate(course)
    final = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    project.publish(
        course, STEM, final["run"], teaching_review=review(tmp_path), visual_review="not_performed"
    )
    data = content_json(course)
    data["units"][1]["minutes"] += 1
    write_content(course, data)
    row = project.inspect(course, stem=STEM)["units"][0]
    assert row["published"] == "revision_changed_acknowledge_or_render"
    updated = project.acknowledge(course, STEM, review(tmp_path))
    assert project.inspect(course, stem=STEM)["units"][0]["published"] == "current"
    assert updated.reviews
    data["units"][1]["summary"] = data["units"][1]["summary"] + " A new caveat."
    write_content(course, data)
    assert project.inspect(course, stem=STEM)["units"][0]["published"] == "teaching_changed"
    with pytest.raises(CampusError, match="changed"):
        project.acknowledge(course, STEM, review(tmp_path))
    assert any(e.startswith("unit.stale") for e in project.check(course, STEM).errors)


def test_publication_refuses_stale_silent_or_failing_runs(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    prepare(course, tmp_path)
    project.timing(course, STEM, profile=None, silent=True)
    silent = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert not silent["ok"]
    with pytest.raises(CampusError, match="failing checks"):
        project.publish(
            course, STEM, silent["run"], teaching_review=review(tmp_path), visual_review="performed"
        )
    narrate(course)
    runtime.layout = [
        {"chapter": "c01", "beat": "b01", "rule": "layout.overlap", "detail": "a x b"}
    ]
    overlapping = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert not overlapping["ok"] and any("layout" in f for f in overlapping["check"]["failed"])
    board_path = course / f"videos/storyboards/{STEM}.json"
    board = json.loads(board_path.read_text())
    board["chapters"][0]["beats"][0]["layout_waiver"] = "The label deliberately sits on its node."
    board_path.write_text(json.dumps(board))
    project.timing(course, STEM, profile="narrator", silent=False)
    waived = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert waived["ok"]
    scene = course / f"videos/scenes/{STEM}/chapters.py"
    scene.write_text(scene.read_text() + "\n")
    with pytest.raises(CampusError, match="Inputs changed"):
        project.publish(
            course, STEM, waived["run"], teaching_review=review(tmp_path), visual_review="performed"
        )


def test_interrupted_publication_rolls_back(
    course: Path, runtime: FakeRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare(course, tmp_path)
    narrate(course)
    final = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    original = project._write_json

    def crash(path: Path, value: object) -> bytes:
        if path.name == "manifest.json":
            raise OSError("disk full")
        return original(path, value)

    monkeypatch.setattr(project, "_write_json", crash)
    with pytest.raises(OSError):
        project.publish(
            course, STEM, final["run"], teaching_review=review(tmp_path), visual_review="performed"
        )
    assert (course / f"videos/tracks/{STEM}.mp4").exists()
    monkeypatch.setattr(project, "_write_json", original)
    state = project.inspect(course)
    assert state["interrupted_publication"]
    with project.locked(course):
        pass
    assert not (course / f"videos/tracks/{STEM}.mp4").exists()
    assert not (course / f"videos/narration/{STEM}.txt").exists()
    assert project.load_manifest(course) is None


def test_foreign_folders_locks_and_lint_failures_stop_work(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    (course / "videos").mkdir()
    (course / "videos/holiday.mp4").write_bytes(b"personal")
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"units": [{"unit": "bfs", "decision": "video", "reason": "Trace."}]})
    )
    with pytest.raises(CampusError, match="did not create"):
        project.plan(course, selection)
    (course / "videos/holiday.mp4").unlink()
    prepare(course, tmp_path)
    narrate(course)
    with FileLock(str(course / "videos/.build/video.lock")):
        with pytest.raises(CampusError, match="Another Video Notes command"):
            project.render(course, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    scene = course / f"videos/scenes/{STEM}/chapters.py"
    scene.write_text(SCENE.replace('self.label("start")', 'Text("start")'))
    blocked = project.render(course, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    assert not blocked["ok"] and blocked["lint"]
    assert runtime.renders == 0


def test_prune_keeps_rendering_runs_and_removes_abandoned_ones(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    prepare(course, tmp_path)
    narrate(course)
    first = project.render(course, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    runs_dir = course / f"videos/.build/{STEM}/runs"
    for name in ("r-00000000", "r-11111111"):
        (runs_dir / name).mkdir()
        (runs_dir / name / "pending.json").write_text(json.dumps({"stage": "render"}))
    second = project.render(course, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    review = tmp_path / "review.md"
    review.write_text("Teaching review.")
    rendering = FileLock(str(runs_dir / "r-11111111/run.lock"), timeout=0)
    with rendering:
        with pytest.raises(CampusError, match="still rendering"):
            project.publish(
                course,
                STEM,
                "r-11111111",
                teaching_review=review,
                visual_review="performed",
            )
        result = project.prune(course, keep=1)
    runs = {path.name for path in runs_dir.iterdir()}
    assert runs == {"r-11111111", second["run"]} and first["run"] not in runs
    assert result["freed_bytes"] > 0
    with pytest.raises(CampusError, match="not a render run id"):
        project.recheck(course, STEM, "../plan")
    assert Storyboard.model_validate_json((course / f"videos/storyboards/{STEM}.json").read_bytes())
