import json
import os
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
        with self.beat("b03") as b:
            self.wait(b.share(0.5))
"""


class FakeRuntime:
    def __init__(self) -> None:
        self.layout: list[dict] = []
        self.renders = 0
        self.frame_requests: list[dict] = []
        self.assembly_requests: list[dict] = []

    def __call__(self, request: dict, **_: object) -> dict:
        action = request["action"]
        if action == "measure":
            return {"ok": True, "durations": {name: 1.6 for name in request["files"]}}
        if action == "render":
            run = Path(request["run"])
            timing = json.loads((run / "timing.json").read_text(encoding="utf-8"))
            beats = [b for b in timing["beats"] if b["chapter"] == request["chapter"]]
            fps = 15 if request["quality"] == "draft" else 30
            frames = round((beats[-1]["start"] + beats[-1]["duration"]) * fps) - round(
                beats[0]["start"] * fps
            )
            target = run / "chapters" / f"{request['chapter']}.mp4"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(CLIP, target)
            self.renders += 1
            board = json.loads((run / "storyboard.json").read_text(encoding="utf-8"))
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
            self.assembly_requests.append(request)
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
            self.frame_requests.append(request)
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
        ),
        encoding="utf-8",
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
                        "kind": "overview",
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
                        "point": "Queue order",
                        "narration": ["Pause and choose an answer."],
                        "pause_s": 2,
                        "question": question["ref"],
                        "intent": "Ask.",
                        "locators": [{k: question[k] for k in ("kind", "ref", "fingerprint")}],
                    },
                    {
                        "key": "b03",
                        "kind": "recap",
                        "narration": ["The queue preserves the traversal order."],
                        "intent": "Connect the result to the rule.",
                        "locators": [
                            {k: refs["summary"][k] for k in ("kind", "ref", "fingerprint")}
                        ],
                    },
                ],
            }
        ],
    }
    (root / "videos/storyboards").mkdir(parents=True)
    (root / f"videos/storyboards/{STEM}.json").write_text(json.dumps(board), encoding="utf-8")
    (root / f"videos/scenes/{STEM}").mkdir(parents=True)
    (root / f"videos/scenes/{STEM}/chapters.py").write_text(SCENE, encoding="utf-8")
    voice = json.loads((root / "videos/voice.json").read_text(encoding="utf-8"))
    voice["profiles"] = {
        "narrator": {"provider": "kokoro", "route": "local", "voice": "af_heart", "language": "en"}
    }
    (root / "videos/voice.json").write_text(json.dumps(voice), encoding="utf-8")


def narrate(root: Path) -> None:
    for item in project.narration(root, STEM, "narrator"):
        target = root / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TONE, target)
    project.timing(root, STEM, profile="narrator", silent=False)


def review(tmp_path: Path) -> Path:
    path = tmp_path / "review.md"
    path.write_text("Every beat traced to its locator; no added claims.\n", encoding="utf-8")
    return path


def test_full_flow_publishes_a_checked_final_video(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    prepare(course, tmp_path)
    assert project.check(course, STEM).errors == ()
    working = course / f"videos/.build/{STEM}/transcript.txt"
    assert working.read_text(encoding="utf-8").startswith("Breadth-first search")
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
    if os.name != "nt":
        assert stat.S_IMODE(track.stat().st_mode) == 0o600
    assert receipt.narrated and receipt.files["captions"].path == f"captions/{STEM}.vtt"
    state = project.inspect(course, verify=True)
    rows = {row["unit"]: row for row in state["units"]}
    assert rows["bfs"]["published"] == "current" and rows["dfs"]["decision"] == "text-first"
    assert f"tracks/{STEM}.mp4" in (course / "videos/playlist.m3u").read_text(encoding="utf-8")
    assert "text-first (Mostly a comparison table.)" in (course / "videos/COVERAGE.md").read_text(
        encoding="utf-8"
    )
    before = runtime.renders
    again = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert again["ok"] and runtime.renders == before
    assert all(item["cached"] for item in again["chapters"].values())
    # Revising and checking the storyboard never touches the published transcript.
    board_path = course / f"videos/storyboards/{STEM}.json"
    board = json.loads(board_path.read_text(encoding="utf-8"))
    board["title"] = "Breadth-first search, revised"
    board_path.write_text(json.dumps(board), encoding="utf-8")
    assert project.check(course, STEM).errors == ()
    row = project.inspect(course, stem=STEM, verify=True)["units"][0]
    assert row["published"] == "current" and row["edited_since_publication"]


def test_crlf_scenes_render_publish_and_stay_current(
    course: Path, runtime: FakeRuntime, tmp_path: Path
) -> None:
    # Windows editors save CRLF; render, publish and inspect must fingerprint the same bytes.
    prepare(course, tmp_path)
    scene = course / f"videos/scenes/{STEM}/chapters.py"
    scene.write_bytes(SCENE.replace("\n", "\r\n").encode())
    narrate(course)
    final = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert final["ok"], final
    project.publish(
        course, STEM, final["run"], teaching_review=review(tmp_path), visual_review="performed"
    )
    row = project.inspect(course, stem=STEM, verify=True)["units"][0]
    assert row["published"] == "current" and not row["edited_since_publication"]


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


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_palette_drift_preserves_published_files_and_narration(
    course: Path, runtime: FakeRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, theme: str
) -> None:
    from tum_mcp import video_style
    from tum_mcp.video_content import StyleProfile

    prepare(course, tmp_path)
    project._write_json(course / "videos/style.json", StyleProfile(theme=theme))
    narrate(course)
    before = project.narration(course, STEM, "narrator")
    final = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    project.publish(
        course, STEM, final["run"], teaching_review=review(tmp_path), visual_review="performed"
    )
    staged = json.loads(
        (course / f"videos/.build/{STEM}/runs/{final['run']}/style.json").read_bytes()
    )
    assert (
        staged["theme"] == theme
        and staged["tokens"] == video_style.resolve(StyleProfile(theme=theme))["tokens"]
    )
    css = video_style.STYLESHEET.read_text(encoding="utf-8")
    path = tmp_path / "styles.css"
    path.write_text(css.replace("--s1: 4px", "--s1: 7px"), encoding="utf-8")
    monkeypatch.setattr(
        project,
        "staged_bytes",
        lambda profile: video_style.canonical(video_style.resolve(profile, stylesheet=path)),
    )
    assert project.inspect(course, stem=STEM)["units"][0]["published"] == "current"
    path.write_text(
        css.replace("--accent: #3070b3", "--accent: #205080").replace(
            "--accent: #8cbffa", "--accent: #aaccff"
        ),
        encoding="utf-8",
    )
    assert project.inspect(course, stem=STEM)["units"][0]["published"] == "style_changed"
    assert project.narration(course, STEM, "narrator") == before
    assert (course / f"videos/tracks/{STEM}.mp4").read_bytes() == CLIP.read_bytes()


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
    board = json.loads(board_path.read_text(encoding="utf-8"))
    board["chapters"][0]["beats"][0]["layout_waiver"] = "The label deliberately sits on its node."
    board_path.write_text(json.dumps(board), encoding="utf-8")
    project.timing(course, STEM, profile="narrator", silent=False)
    waived = project.render(course, STEM, quality="final", jobs=1, max_minutes=None, run=None)
    assert waived["ok"]
    scene = course / f"videos/scenes/{STEM}/chapters.py"
    scene.write_text(scene.read_text(encoding="utf-8") + "\n", encoding="utf-8")
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
        json.dumps({"units": [{"unit": "bfs", "decision": "video", "reason": "Trace."}]}),
        encoding="utf-8",
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
    scene.write_text(SCENE.replace('self.label("start")', 'Text("start")'), encoding="utf-8")
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
        (runs_dir / name / "pending.json").write_text(
            json.dumps({"stage": "render"}), encoding="utf-8"
        )
    second = project.render(course, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    review = tmp_path / "review.md"
    review.write_text("Teaching review.", encoding="utf-8")
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


def test_optional_reading_does_not_change_core_video_inputs(course: Path) -> None:
    before = project.unit_locators(course, "bfs")
    payload = content_json(course)
    unit = next(unit for unit in payload["units"] if unit["key"] == "bfs")
    unit["explore"] = [
        {
            "key": "history",
            "title": "Supporting history",
            "sources": unit["sources"],
            "blocks": [
                {
                    "kind": "text",
                    "key": "context",
                    "sources": [unit["sources"][0]["key"]],
                    "paragraphs": ["A synthetic optional historical detour."],
                }
            ],
        }
    ]
    write_content(course, payload)
    after = project.unit_locators(course, "bfs")
    assert after["unit_hash"] == before["unit_hash"]
    assert after["revision"] == before["revision"]
    assert after["locators"] == before["locators"]
    assert after["formulas"] == before["formulas"]


@pytest.mark.parametrize("duration", [1.0, 0.02])
def test_contact_sheets_paginate_unique_real_frames(
    course: Path, runtime: FakeRuntime, tmp_path: Path, duration: float
) -> None:
    from tum_mcp.video_content import BeatTiming, ChapterBound, Timing

    prepare(course, tmp_path)
    board, _ = project.stored_storyboard(course, STEM)
    data = board.model_dump(mode="json")
    first = data["chapters"][0]["beats"][0]
    data["chapters"][0]["beats"] = [
        {**first, "key": f"b{index:02d}", "on_screen": []} for index in range(1, 6)
    ]
    board = Storyboard.model_validate(data)
    timings = Timing(
        video=STEM,
        storyboard_sha256="0" * 64,
        voice="silent",
        total=5 * duration,
        beats=tuple(
            BeatTiming(key=f"b{i + 1:02d}", chapter="c01", start=i * duration, duration=duration)
            for i in range(5)
        ),
    )
    bound = ChapterBound(key="c01", title="Trace", start=0, end=round(5 * duration * 30) / 30)
    sheets = project._sheets(tmp_path, board, timings, [bound], tmp_path / "python", 30)
    samples = [t for request in runtime.frame_requests for t in request["times"]]
    assert samples == sorted(set(samples))
    assert all(0 <= t < bound.end and t * 30 == pytest.approx(round(t * 30)) for t in samples)
    assert all(len(r["times"]) <= 12 for r in runtime.frame_requests)
    assert len(sheets) == (2 if duration == 1 else 1)


def prepare_walkthrough(root: Path, tmp_path: Path, parts: int = 1, *, timed: bool = True) -> str:
    from tum_mcp.course_app_paths import app_path

    path = app_path(root, "exercises.json")
    data = json.loads(path.read_bytes())
    exercise = data["sets"][0]["exercises"][0]
    if parts > 1:
        exercise["parts"] = [f"({i})" for i in range(1, parts + 1)]
        answer = exercise["solution"]["answers"][0]
        exercise["solution"]["answers"] = [
            {**answer, "label": label} for label in exercise["parts"]
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
    ref = {"set": data["sets"][0]["key"], "exercise": exercise["key"]}
    selection = tmp_path / "walkthrough-selection.json"
    selection.write_text(
        json.dumps(
            {
                "exercises": [
                    {"exercise": ref, "decision": "video", "reason": "Work the selected problem."}
                ]
            }
        ),
        encoding="utf-8",
    )
    plan_ = project.plan(root, selection)
    stem = next(item.stem for item in plan_.videos if hasattr(item, "exercise"))
    info = project.exercise_locators(root, f"{ref['set']}/{ref['exercise']}")
    statement = next(item for item in info["locators"] if item["kind"] == "statement")
    chapters = []
    scenes = ["from manim import *\nfrom vnotes import NotesScene\n"]
    for i, answer in enumerate(info["answers"], 1):
        chapter, screen = f"c{i:02d}", f"result-{i}"
        beats = []
        scene = [f"class {chapter.upper()}(NotesScene):", "    def construct(self):"]
        for j, kind in enumerate(("setup", "strategy", "work", "verify", "answer")):
            beat = f"b{(i - 1) * 5 + j + 1:03d}"
            beats.append(
                {
                    "key": beat,
                    "kind": kind,
                    "narration": ["The candidate cost is three."],
                    "intent": "Connect the path cost to the result.",
                    "locators": [statement, answer] if kind == "answer" else [statement],
                    "on_screen": (
                        [{"key": screen, "kind": "label", "text": "2 + 1 = 3"}]
                        if kind == "answer"
                        else []
                    ),
                }
            )
            scene.append(f'        with self.beat("{beat}"):')
            if kind == "answer":
                scene.extend(
                    [
                        "            with self.cue(1) as cue:",
                        f'                self.play(Write(self.label("{screen}")), '
                        "run_time=cue.share(0.5))",
                    ]
                )
            else:
                scene.append("            pass")
        chapters.append(
            {
                "key": chapter,
                "title": f"Part {i}",
                "answer": answer,
                "beats": beats,
            }
        )
        scenes.append("\n".join(scene) + "\n")
    board = {
        "video": stem,
        "exercise": ref,
        "exercise_hash": info["exercise_hash"],
        "title": info["title"],
        "language": "en",
        "answers": info["answers"],
        "chapters": chapters,
    }
    (root / "videos/storyboards").mkdir(exist_ok=True)
    (root / f"videos/storyboards/{stem}.json").write_text(json.dumps(board), encoding="utf-8")
    folder = root / f"videos/scenes/{stem}"
    folder.mkdir(parents=True)
    (folder / "chapters.py").write_text("\n".join(scenes), encoding="utf-8")
    voice = json.loads((root / "videos/voice.json").read_bytes())
    voice["profiles"] = {
        "narrator": {"provider": "kokoro", "route": "local", "voice": "af_heart", "language": "en"}
    }
    (root / "videos/voice.json").write_text(json.dumps(voice), encoding="utf-8")
    for item in project.narration(root, stem, "narrator"):
        target = root / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TONE, target)
    if timed:
        project.timing(root, stem, profile="narrator", silent=False)
    return stem


@pytest.mark.parametrize("mutation", ["mixed", "missing", "reordered", "unmapped"])
def test_walkthrough_rejects_mixed_identity_or_missing_part_mapping(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
    mutation: str,
) -> None:
    from pydantic import ValidationError

    from tum_mcp.video_content import StoryboardFile

    stem = prepare_walkthrough(exercise_project, tmp_path, parts=3)
    data = json.loads((exercise_project / f"videos/storyboards/{stem}.json").read_bytes())
    match mutation:
        case "mixed":
            data["unit"] = "bfs"
        case "missing":
            data["chapters"].pop()
        case "reordered":
            data["chapters"][0]["answer"], data["chapters"][2]["answer"] = (
                data["chapters"][2]["answer"],
                data["chapters"][0]["answer"],
            )
        case "unmapped":
            data["chapters"][0]["beats"][-1]["locators"].pop()
    with pytest.raises(ValidationError):
        StoryboardFile.model_validate(data)


def test_source_variants_do_not_collide_on_bare_keys_or_cross_course(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.course_app_paths import app_path

    path = app_path(exercise_project, "exercises.json")
    data = json.loads(path.read_bytes())
    data["sets"][0]["exercises"][0]["key"] = "bfs"
    path.write_text(json.dumps(data), encoding="utf-8")
    selection = tmp_path / "sources.json"
    selection.write_text(
        json.dumps(
            {
                "units": [{"unit": "bfs", "decision": "video", "reason": "Concept."}],
                "exercises": [
                    {
                        "exercise": {"set": "sheet-1", "exercise": "bfs"},
                        "decision": "video",
                        "reason": "Solve the problem.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan_ = project.plan(exercise_project, selection)
    assert len({item.stem for item in plan_.videos}) == 2
    data["course_key"] = "another-course"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CampusError, match="identities differ"):
        project.plan(exercise_project, selection)


def test_exercise_only_walkthrough_publishes_all_thirteen_parts(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.course_app_paths import app_path
    from tum_mcp.video_content import ExerciseReceipt

    app_path(exercise_project, "content.json").unlink()
    stem = prepare_walkthrough(exercise_project, tmp_path, parts=13)
    assert project.check(exercise_project, stem).errors == ()
    final = project.render(
        exercise_project, stem, quality="final", jobs=2, max_minutes=None, run=None
    )
    assert final["ok"], final
    receipt = project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review(tmp_path),
        visual_review="not_performed",
    )
    assert isinstance(receipt, ExerciseReceipt) and len(receipt.chapters) == 13
    assert [chapter.answer.ref for chapter in receipt.chapters] == [
        f"answers[{i}]" for i in range(13)
    ]
    assert receipt.solution_origin == "authored" and receipt.source_references
    state = project.inspect(exercise_project, verify=True)
    assert state["units"] == [] and state["exercises"][0]["published"] == "current"
    assert project.preview_index(exercise_project)["exercises"]["sheet-1/sample-relaxation"]
    assert (
        project.acknowledge(exercise_project, stem, review(tmp_path)).exercise == receipt.exercise
    )


@pytest.mark.parametrize("mutation", ["answer", "statement", "origin", "hint", "unrelated"])
def test_walkthrough_freshness_tracks_only_selected_teaching_and_provenance(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
    mutation: str,
) -> None:
    from tum_mcp.course_app_paths import app_path

    stem = prepare_walkthrough(exercise_project, tmp_path)
    final = project.render(
        exercise_project, stem, quality="final", jobs=1, max_minutes=None, run=None
    )
    project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review(tmp_path),
        visual_review="not_performed",
    )
    path = app_path(exercise_project, "exercises.json")
    value = json.loads(path.read_bytes())
    exercise = value["sets"][0]["exercises"][0]
    match mutation:
        case "answer":
            exercise["solution"]["answers"][0]["blocks"][0]["paragraphs"][0] += " Different result."
        case "statement":
            exercise["statement"][0]["paragraphs"][0] += " With a changed given."
        case "origin":
            exercise["solution"].update(
                origin="official", official_source=exercise["sources"][0]["key"]
            )
        case "hint":
            exercise["steps"][0]["hints"][0] += " A reminder."
        case "unrelated":
            value["sets"][0]["exercises"][1]["statement"][0]["paragraphs"][0] += " A caveat."
    path.write_text(json.dumps(value), encoding="utf-8")
    status = project.inspect(exercise_project, stem=stem)["exercises"][0]["published"]
    expected = (
        "current"
        if mutation in {"hint", "unrelated"}
        else ("source_changed" if mutation == "origin" else "teaching_changed")
    )
    assert status == expected
    if mutation in {"answer", "statement"}:
        with pytest.raises(CampusError, match="storyboard|changed"):
            project.publish(
                exercise_project,
                stem,
                final["run"],
                teaching_review=review(tmp_path),
                visual_review="not_performed",
            )


def test_walkthrough_used_prerequisite_and_removed_target_are_not_silently_rebound(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.course_app_paths import app_path

    stem = prepare_walkthrough(exercise_project, tmp_path)
    board_path = exercise_project / f"videos/storyboards/{stem}.json"
    board = json.loads(board_path.read_bytes())
    info = project.exercise_locators(exercise_project, "sheet-1/sample-relaxation")
    prerequisite = next(item for item in info["locators"] if item["kind"] == "prerequisite")
    board["chapters"][0]["beats"][0]["locators"].append(prerequisite)
    board_path.write_text(json.dumps(board), encoding="utf-8")
    project.timing(exercise_project, stem, profile="narrator", silent=False)
    final = project.render(
        exercise_project, stem, quality="final", jobs=1, max_minutes=None, run=None
    )
    project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review(tmp_path),
        visual_review="not_performed",
    )
    study = app_path(exercise_project, "content.json")
    data = json.loads(study.read_bytes())
    next(u for u in data["units"] if u["key"] == "weighted")["summary"] += " A new condition."
    study.write_text(json.dumps(data), encoding="utf-8")
    assert (
        project.inspect(exercise_project, stem=stem)["exercises"][0]["published"]
        == "teaching_changed"
    )
    with pytest.raises(CampusError, match="changed"):
        project.acknowledge(exercise_project, stem, review(tmp_path))
    path = app_path(exercise_project, "exercises.json")
    data = json.loads(path.read_bytes())
    data["sets"][0]["exercises"].pop(0)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert project.inspect(exercise_project)["orphaned_exercises"] == ["sheet-1/sample-relaxation"]
    with pytest.raises(CampusError, match="removed or moved"):
        project.check(exercise_project, stem)


def test_walkthrough_rejects_changed_source_bytes(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.study_store import load_state

    stem = prepare_walkthrough(exercise_project, tmp_path)
    info = project.exercise_locators(exercise_project, "sheet-1/sample-relaxation")
    source_key = info["source_references"][0]["key"]
    material = next(
        r for r in load_state(exercise_project).resources if r.resource.key == source_key
    )
    path = exercise_project / material.path
    path.write_bytes(path.read_bytes() + b"\nchanged")
    with pytest.raises(CampusError, match="Source material.*changed"):
        project.check(exercise_project, stem)


def test_published_video_review_identity_survives_pruned_caches_and_detects_changed_bytes(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.study_build import read_content
    from tum_mcp.study_media import discover
    from tum_mcp.study_store import load_state

    stem = prepare_walkthrough(exercise_project, tmp_path)
    final = project.render(
        exercise_project, stem, quality="final", jobs=1, max_minutes=None, run=None
    )
    project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review(tmp_path),
        visual_review="not_performed",
    )
    state, content = load_state(exercise_project), read_content(exercise_project)
    first = discover(exercise_project, state, content)
    assert not first.invalid and not first.items[0].stale and not first.items[0].technical
    assert first.items[0].profile == "exercise"
    assert first.items[0].structure["targets"] == ["exercises/sheet-1/sample-relaxation"]
    timing = project.load_timing(
        exercise_project,
        stem,
        (exercise_project / f"videos/storyboards/{stem}.json").read_bytes(),
    )
    cue = timing.beats[0].cues[0]
    assert cue.start < runtime.assembly_requests[-1]["poster_at"] < cue.end
    shutil.rmtree(exercise_project / "videos/.build")
    assert discover(exercise_project, state, content).items[0].revision == first.items[0].revision
    track = exercise_project / f"videos/tracks/{stem}.mp4"
    data = track.read_bytes()
    track.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    corrupted = discover(exercise_project, state, content)
    assert corrupted.invalid and not corrupted.items and f"video/{stem}" in corrupted.known


def test_media_discovery_cannot_count_a_stem_reassigned_to_another_source_as_complete(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.study_build import read_content
    from tum_mcp.study_media import discover
    from tum_mcp.study_store import load_state

    stem = prepare_walkthrough(exercise_project, tmp_path)
    final = project.render(
        exercise_project, stem, quality="final", jobs=1, max_minutes=None, run=None
    )
    project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review(tmp_path),
        visual_review="not_performed",
    )
    path = exercise_project / "videos/plan.json"
    plan = json.loads(path.read_bytes())
    plan["videos"][0] = {
        "unit": "bfs",
        "stem": stem,
        "decision": "video",
        "reason": "Different source.",
    }
    path.write_text(json.dumps(plan), encoding="utf-8")
    found = discover(exercise_project, load_state(exercise_project), read_content(exercise_project))
    assert found.pending == [{"item": f"video/{stem}", "source": "study/bfs", "reason": "changed"}]
    assert found.items[0].structure["targets"] == ["exercises/sheet-1/sample-relaxation"]


def test_unpublished_plan_target_removed_from_the_source_is_not_new_work(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
) -> None:
    from tum_mcp.course_app_paths import app_path
    from tum_mcp.study_build import read_content
    from tum_mcp.study_media import discover
    from tum_mcp.study_store import load_state

    stem = prepare_walkthrough(exercise_project, tmp_path)
    path = app_path(exercise_project, "exercises.json")
    data = json.loads(path.read_bytes())
    group = next(group for group in data["sets"] if group["key"] == "sheet-1")
    group["exercises"] = [
        exercise for exercise in group["exercises"] if exercise["key"] != "sample-relaxation"
    ]
    path.write_text(json.dumps(data), encoding="utf-8")
    found = discover(exercise_project, load_state(exercise_project), read_content(exercise_project))
    assert not found.invalid
    assert found.pending == [
        {
            "item": f"video/{stem}",
            "source": "exercises/sheet-1/sample-relaxation",
            "reason": "removed",
        }
    ]


@pytest.mark.parametrize(
    "failure", ["index", "bounds", "mapping", "duration", "snapshot", "review_map"]
)
def test_published_chapters_and_input_snapshots_are_not_unchecked_declarations(
    exercise_project: Path,
    runtime: FakeRuntime,
    tmp_path: Path,
    failure: str,
) -> None:
    import hashlib

    from tum_mcp.study_build import read_content
    from tum_mcp.study_media import discover
    from tum_mcp.study_store import load_state

    stem = prepare_walkthrough(exercise_project, tmp_path, parts=2)
    final = project.render(
        exercise_project, stem, quality="final", jobs=1, max_minutes=None, run=None
    )
    project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review(tmp_path),
        visual_review="not_performed",
    )
    path = exercise_project / "videos/manifest.json"
    manifest = json.loads(path.read_bytes())
    receipt = manifest["videos"][stem]
    original = discover(
        exercise_project, load_state(exercise_project), read_content(exercise_project)
    ).items[0]
    match failure:
        case "index":
            index = exercise_project / "videos" / receipt["files"]["chapter_index"]["path"]
            value = json.loads(index.read_bytes())
            value[0]["title"] = "Changed independently"
            data = json.dumps(value).encode()
            index.write_bytes(data)
            receipt["files"]["chapter_index"].update(
                sha256=hashlib.sha256(data).hexdigest(), size=len(data)
            )
        case "bounds":
            receipt["chapters"][1]["start"] = 0
        case "mapping":
            receipt["chapters"][1]["answer"] = receipt["answers"][0]
        case "duration":
            receipt["duration"] = 0
        case "snapshot":
            receipt["voice_profile"] = None
            receipt["assets_sha256"] = None
            receipt["beats"] = []
        case "review_map":
            receipt["beats"][0]["cues"][0]["text"] += " Changed mapping."
    path.write_text(json.dumps(manifest), encoding="utf-8")
    found = discover(exercise_project, load_state(exercise_project), read_content(exercise_project))
    if failure == "review_map":
        assert not found.invalid
        assert found.items[0].artifact_sha256 == original.artifact_sha256
        assert found.items[0].revision != original.revision
    elif failure == "snapshot":
        assert set(found.items[0].technical) == {
            "snapshot.voice",
            "snapshot.assets",
            "snapshot.beats",
        }
    else:
        assert found.invalid and not found.items
