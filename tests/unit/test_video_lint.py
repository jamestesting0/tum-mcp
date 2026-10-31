import pytest

from tum_mcp.video_content import Storyboard
from tum_mcp.video_lint import lint

BOARD = Storyboard.model_validate(
    {
        "video": "01_demo",
        "unit": "demo",
        "unit_hash": "0" * 64,
        "title": "Demo",
        "language": "en",
        "objectives": ["goal"],
        "chapters": [
            {
                "key": "c01",
                "title": "Start",
                "beats": [
                    {
                        "key": "b01",
                        "kind": "hook",
                        "narration": ["Hello."],
                        "intent": "Open.",
                        "locators": [
                            {"kind": "summary", "ref": "summary", "fingerprint": "0" * 64}
                        ],
                        "on_screen": [
                            {"key": "title", "kind": "label", "text": "Demo"},
                            {"key": "n", "kind": "number", "value": 4},
                        ],
                    }
                ],
            }
        ],
    }
)

GOOD = """from manim import *
from vnotes import NotesScene


class C01(NotesScene):
    def construct(self):
        with self.beat("b01") as b:
            title = self.label("title")
            tracker = ValueTracker(0)
            tracker.set_value(self.value("n"))
            self.play(Write(title), run_time=b.share(0.5))
"""


def test_scene_using_helpers_passes() -> None:
    report = lint(GOOD, BOARD)
    assert report.ok, report.errors
    assert report.warnings == ()


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (("from manim import *", "import os\nfrom manim import *"), "import line"),
        (("from manim import *", "from manim import *\nfrom manim import Text as T"), "Text"),
        (("from manim import *", "from subprocess import run\nfrom manim import *"), "import"),
        (('self.label("title")', 'Text("Demo")'), "text line"),
        (('self.label("title")', 'MathTex("x")'), "text line"),
        (('self.label("title")', 'self.label("missing")'), "no on-screen item"),
        (('self.label("title")', "self.label(name)"), "literal key"),
        (('self.label("title")', 'self.number("title")'), "is a label"),
        (("Write(title)", "ShowCreation(title)"), "ManimGL"),
        (('self.label("title")', 'open("/etc/passwd")'), "forbidden"),
        (('self.label("title")', 'np.load("x.npy")'), "touch files"),
        (('self.label("title")', "self.__class__"), "dunder"),
        (('self.beat("b01")', 'self.beat("b02")'), "beats appear"),
        (("class C01(NotesScene)", "class C02(NotesScene)"), "missing"),
        (('tracker.set_value(self.value("n"))', "tracker.set_value(4)"), "set_value"),
        (("tracker = ValueTracker(0)", "config.frame_rate = 60"), "forbidden"),
        (
            ('            title = self.label("title")', "            self.add_sound('x.wav')"),
            "pipeline",
        ),
    ],
)
def test_lint_rejects_unsafe_or_unsynchronised_code(change: tuple[str, str], fragment: str) -> None:
    report = lint(GOOD.replace(*change, 1), BOARD)
    assert not report.ok
    assert any(fragment in error for error in report.errors), report.errors


def test_syntax_errors_and_unused_items_are_reported() -> None:
    assert not lint("class C01(:\n", BOARD).ok
    report = lint(
        GOOD.replace('            title = self.label("title")\n', "            title = Dot()\n"),
        BOARD,
    )
    assert report.ok
    assert "title" in report.warnings[0]


@pytest.mark.parametrize("index", ["0", "2", "True", "index"])
def test_cues_require_an_existing_literal_sentence(index: str) -> None:
    source = GOOD.replace(
        '            title = self.label("title")',
        f'            with self.cue({index}):\n                title = self.label("title")',
    )
    assert any(error.startswith("cue ") for error in lint(source, BOARD).errors)


def test_cues_are_allowed_only_inside_beats() -> None:
    valid = GOOD.replace(
        '            title = self.label("title")',
        '            with self.cue(1):\n                title = self.label("title")',
    )
    assert lint(valid, BOARD).ok
    invalid = GOOD.replace(
        '        with self.beat("b01") as b:',
        "        with self.cue(1) as b:",
    )
    assert any("enclosing beat" in error for error in lint(invalid, BOARD).errors)
