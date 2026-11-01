import json
import math
import os
import shutil
import struct
import wave
from pathlib import Path

import pytest

from tum_mcp import video_project as project
from tum_mcp import video_runtime

FIXTURES = Path(__file__).parents[1] / "fixtures"
STEM = "01_follow-the-frontier"
SCENE = """from manim import *
from vnotes import NotesScene


class C01(NotesScene):
    def construct(self):
        with self.beat("b01") as b:
            node = Circle(radius=0.6, color=self.color("accent"))
            label = self.label("start").move_to(node)
            with self.cue(1) as cue:
                self.play(Create(node), FadeIn(label), run_time=cue.share(0.5))
            with self.cue(2) as cue:
                expected = self.beat_timing["b01"]["cues"][1]["start"] - self.chapter_start
                assert abs(self.time - expected) <= 1 / 15
                self.play(Indicate(node), run_time=cue.share(0.5))
        with self.beat("b02") as b:
            formula = self.math("rule").to_edge(UP, buff=1)
            self.play(Write(formula), node.animate.set_fill(self.color("active"), opacity=1),
                      label.animate.set_color(self.color("active_ink")), run_time=b.share(0.5))


class C02(NotesScene):
    def construct(self):
        with self.beat("b03") as b:
            code = self.code("trace").to_edge(LEFT, buff=1)
            assert len(code) == 4 and code[3].get_left()[0] > code[2].get_left()[0] + 0.3
            assert code[1].get_center()[1] < code[0].get_center()[1]
            self.play(FadeIn(code), run_time=b.share(0.37))
            self.play(Indicate(code[3]), run_time=b.share(0.21))
"""

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_VIDEO_RENDER_INTEGRATION") != "1",
    reason="Installs the optional render runtime; select it explicitly.",
)


def speech_like(path: Path, seconds: float) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        frames = bytearray()
        for index in range(int(rate * seconds)):
            envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * index / rate)
            value = 0.3 * envelope * math.sin(2 * math.pi * 180 * index / rate)
            frames += struct.pack("<h", int(value * 32767))
        stream.writeframes(bytes(frames))


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("video-runtime")
    previous = os.environ.get("TUM_MCP_DATA_DIR")
    os.environ["TUM_MCP_DATA_DIR"] = str(folder)
    try:
        status = video_runtime.status()
        if status.missing:
            pytest.fail("Render prerequisites missing: " + "; ".join(status.commands))
        assert video_runtime.install().installed
        yield folder
    finally:
        if previous is None:
            os.environ.pop("TUM_MCP_DATA_DIR", None)
        else:
            os.environ["TUM_MCP_DATA_DIR"] = previous


def course(tmp_path: Path, scene: str) -> Path:
    root = tmp_path / "course"
    (root / "app").mkdir(parents=True)
    shutil.copyfile(FIXTURES / "course_app/content.json", root / "app/content.json")
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"units": [{"unit": "bfs", "decision": "video", "reason": "Trace."}]}),
        encoding="utf-8",
    )
    project.plan(root, selection)
    info = project.unit_locators(root, "bfs")
    refs = {item["ref"]: item for item in info["locators"]}
    code_block = next(item["ref"] for item in info["locators"] if "code:" in item["preview"])

    def locator(ref: str) -> dict:
        return {key: refs[ref][key] for key in ("kind", "ref", "fingerprint")}

    objective = json.loads((root / "app/content.json").read_text(encoding="utf-8"))["units"][1][
        "objectives"
    ][0]
    board = {
        "video": STEM,
        "unit": "bfs",
        "unit_hash": info["unit_hash"],
        "title": "Follow the frontier",
        "language": "en",
        "objectives": [objective["key"]],
        "chapters": [
            {
                "key": "c01",
                "title": "Start",
                "beats": [
                    {
                        "key": "b01",
                        "kind": "overview",
                        "narration": [
                            "The search starts at one node and looks outward.",
                            "This is the starting node.",
                        ],
                        "intent": "Start node.",
                        "locators": [locator("summary"), locator(objective["key"])],
                        "on_screen": [{"key": "start", "kind": "label", "text": "s"}],
                    },
                    {
                        "key": "b02",
                        "kind": "mechanism",
                        "point": "Discovery order",
                        "narration": ["Every neighbour joins the frontier before we go deeper."],
                        "intent": "Show the rule.",
                        "locators": [locator(code_block)],
                        "on_screen": [{"key": "rule", "kind": "math", "typst": "d(v) = d(u) + 1"}],
                    },
                ],
            },
            {
                "key": "c02",
                "title": "Code",
                "beats": [
                    {
                        "key": "b03",
                        "kind": "recap",
                        "narration": ["The queue keeps the frontier in order."],
                        "intent": "Show code.",
                        "locators": [locator(code_block)],
                        "on_screen": [
                            {
                                "key": "trace",
                                "kind": "code",
                                "language": "python",
                                "code": (
                                    "queue = deque([s])\n\nwhile queue:\n"
                                    '    u = queue.popleft()  # "next"'
                                ),
                            }
                        ],
                    }
                ],
            },
        ],
    }
    (root / "videos/storyboards").mkdir()
    (root / f"videos/storyboards/{STEM}.json").write_text(json.dumps(board), encoding="utf-8")
    (root / f"videos/scenes/{STEM}").mkdir(parents=True)
    (root / f"videos/scenes/{STEM}/chapters.py").write_text(scene, encoding="utf-8")
    voice = json.loads((root / "videos/voice.json").read_text(encoding="utf-8"))
    voice["profiles"] = {
        "tone": {"provider": "synthetic", "route": "test", "voice": "tone", "language": "en"}
    }
    (root / "videos/voice.json").write_text(json.dumps(voice), encoding="utf-8")
    for item in project.narration(root, STEM, "tone"):
        target = root / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        speech_like(target, len(item["text"].split()) / 2.6)
    project.timing(root, STEM, profile="tone", silent=False)
    return root


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_real_render_mixes_checks_and_publishes(
    installed: Path, tmp_path: Path, theme: str
) -> None:
    root = course(tmp_path, SCENE)
    style_path = root / "videos/style.json"
    style = json.loads(style_path.read_bytes())
    style["theme"] = theme
    style_path.write_text(json.dumps(style), encoding="utf-8")
    draft = project.render(root, STEM, quality="draft", jobs=2, max_minutes=None, run=None)
    assert draft["ok"], draft
    final = project.render(root, STEM, quality="final", jobs=2, max_minutes=None, run=None)
    assert final["ok"], final
    probe = json.loads(
        (root / f"videos/.build/{STEM}/runs/{final['run']}/probe.json").read_text(encoding="utf-8")
    )
    assert probe["width"] == 1920 and abs(probe["loudness_lufs"] + 16) <= 1
    assert abs(probe["audio_duration"] - probe["video_duration"]) <= 0.1
    # Beat padding and per-chapter frame counts must add up to the timing, frame for frame.
    timing = json.loads((root / f"videos/.build/{STEM}/timing.json").read_text(encoding="utf-8"))
    assert probe["video_duration"] == pytest.approx(round(timing["total"] * 30) / 30, abs=1e-3)
    review = tmp_path / "review.md"
    review.write_text("Synthetic narration; every beat traced.\n", encoding="utf-8")
    receipt = project.publish(
        root, STEM, final["run"], teaching_review=review, visual_review="not_performed"
    )
    assert receipt.duration == pytest.approx(probe["video_duration"])


def test_transient_rich_speech_stays_below_the_decoded_true_peak_ceiling(
    installed: Path, tmp_path: Path
) -> None:
    # Actual synthetic speech from the gallery recipe exposes AAC transient overshoot
    # that the sinusoidal codec fixture cannot. No course or account data is used.
    speech = FIXTURES / "video/speech.wav"
    measured = video_runtime.call_worker({"action": "measure", "files": [str(speech)]})
    duration = measured["durations"][str(speech)]
    result = video_runtime.call_worker(
        {
            "action": "assemble",
            "quality": "draft",
            "chapters": [{"file": str(FIXTURES / "video/clip.mp4"), "frames": 30}] * 7,
            "audio": [{"file": str(speech), "start": 0, "end": duration}],
            "output": str(tmp_path / "speech.mp4"),
            "poster": str(tmp_path / "poster.jpg"),
            "poster_at": 0,
        },
        timeout=180,
    )
    assert result["ok"], result
    assert result["probe"]["true_peak_dbtp"] <= -1.5
    assert abs(result["probe"]["loudness_lufs"] + 16) <= 1


def test_labels_wrap_at_measured_width_without_shrinking_the_type(
    installed: Path, tmp_path: Path
) -> None:
    wrapped = SCENE.replace(
        'label = self.label("start").move_to(node)',
        'label = self.label("start", width=3.2).move_to(node)\n'
        '            natural = self.label("start")\n'
        "            assert label.width <= 3.22\n"
        "            assert label.height > natural.height * 1.5\n"
        "            assert label.vnotes_font == natural.vnotes_font == 32",
    )
    root = course(tmp_path, wrapped)
    path = root / f"videos/storyboards/{STEM}.json"
    board = json.loads(path.read_bytes())
    board["chapters"][0]["beats"][0]["on_screen"][0]["text"] = (
        "Wrap the explanation onto readable lines without making its letters smaller."
    )
    path.write_text(json.dumps(board), encoding="utf-8")
    project.timing(root, STEM, profile="tone", silent=False)
    result = project.render(root, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    assert result["ok"], result
    assert not result["layout"]


def test_real_probe_reports_overlap_and_overrun(installed: Path, tmp_path: Path) -> None:
    overlap = SCENE.replace(
        'label = self.label("start").move_to(node)',
        'label = self.label("start").move_to(node)\n'
        '            self.add(self.math("rule").move_to(node))',
    ).replace('formula = self.math("rule").to_edge(UP, buff=1)', "formula = Dot()")
    root = course(tmp_path, overlap)
    result = project.render(root, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    assert not result["ok"]
    assert any(issue["rule"] == "layout.overlap" for issue in result["layout"])
    slow = SCENE.replace("run_time=b.share(0.37)", "run_time=b.duration + 2")
    shutil.rmtree(tmp_path / "course")
    root = course(tmp_path, slow)
    result = project.render(root, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    assert not result["ok"]
    assert "past the narration" in json.dumps(result["failures"])


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("self.cue(1)", "self.cue(3)"), "literal sentence index"),
        (("self.cue(2)", "self.cue(1)"), "out of order"),
        (("run_time=cue.share(0.5)", "run_time=cue.duration + 1"), "past cue 1"),
        (('with self.beat("b01") as b:', "with self.cue(1) as b:"), "enclosing beat"),
    ],
)
def test_sentence_cue_failures_are_precise(
    installed: Path, tmp_path: Path, change: tuple[str, str], message: str
) -> None:
    root = course(tmp_path, SCENE.replace(*change, 1))
    result = project.render(root, STEM, quality="draft", jobs=1, max_minutes=None, run=None)
    assert not result["ok"]
    assert message in json.dumps(result)


def test_exercise_source_uses_the_same_native_worker_without_study(
    installed: Path,
    exercise_project: Path,
    tmp_path: Path,
) -> None:
    from test_video_pipeline import prepare_walkthrough

    from tum_mcp.course_app_paths import app_path

    app_path(exercise_project, "content.json").unlink()
    stem = prepare_walkthrough(exercise_project, tmp_path, parts=2, timed=False)
    for item in project.narration(exercise_project, stem, "narrator"):
        speech_like(exercise_project / item["file"], 2.0)
    project.timing(exercise_project, stem, profile="narrator", silent=False)
    final = project.render(
        exercise_project,
        stem,
        quality="final",
        jobs=2,
        max_minutes=None,
        run=None,
    )
    assert final["ok"], final
    review = tmp_path / "exercise-review.md"
    review.write_text("Synthetic source and measured cues checked; no speech-quality claim.")
    receipt = project.publish(
        exercise_project,
        stem,
        final["run"],
        teaching_review=review,
        visual_review="not_performed",
    )
    assert len(receipt.answers) == 2 and receipt.chapters[1].answer.ref == "answers[1]"
