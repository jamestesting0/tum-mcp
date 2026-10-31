import importlib.util
import itertools
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.video_content import BeatTiming, ChapterBound, Cue, StyleProfile, Timing
from tum_mcp.video_media import Probe, captions, chapters, check_media, faststart, parse_vtt
from tum_mcp.video_style import STYLESHEET, resolve

FIXTURES = Path(__file__).parents[1] / "fixtures/video"
STYLE = Path(__file__).parents[2] / "src/tum_mcp/bundled/video_runtime/vnotes/style.py"


def timing(voice: str = "narrator@" + "a" * 16) -> Timing:
    long = (
        "A deliberately long sentence that goes on to exceed the caption width so that it must "
        "split <cleanly> & safely across several readable cues."
    )
    return Timing(
        video="01_demo",
        storyboard_sha256="0" * 64,
        voice=voice,
        beats=(
            BeatTiming(
                key="b01",
                chapter="c01",
                start=0,
                duration=2.0,
                cues=(Cue(start=0.25, end=1.8, text=long),),
            ),
        ),
        total=2.0,
    )


def probe(**changes: object) -> Probe:
    value = {
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
        "video_codec": "h264",
        "pix_fmt": "yuv420p",
        "width": 854,
        "height": 480,
        "fps": 15.0,
        "video_duration": 2.0,
        "audio_codec": "aac",
        "sample_rate": 48000,
        "channels": 1,
        "audio_duration": 2.0,
        "loudness_lufs": -16.2,
        "true_peak_dbtp": -2.0,
    }
    value.update(changes)
    return Probe.model_validate(value)


def test_long_captions_split_escape_and_stay_inside_their_sentence() -> None:
    cues = parse_vtt(captions(timing()))
    assert len(cues) > 1
    assert cues[0][0] == 0.25 and cues[-1][1] == 1.8
    assert all(len(text) <= 84 for _, _, text in cues)
    assert all(a[1] == b[0] for a, b in itertools.pairwise(cues))
    assert "&lt;cleanly&gt; &amp;" in " ".join(text for _, _, text in cues)


def test_chapter_track_and_parser_reject_malformed_timing() -> None:
    track = chapters((ChapterBound(key="c01", title="Start", start=0, end=2.0),))
    assert parse_vtt(track) == [(0.0, 2.0, "Start")]
    with pytest.raises(ValueError, match="header"):
        parse_vtt("1\n00:00:00.000 --> 00:00:01.000\nx\n")
    with pytest.raises(ValueError, match="timing"):
        parse_vtt("WEBVTT\n\n1\n00:00:00 --> 00:00:01.000\nx\n")


def test_faststart_reads_box_order(tmp_path: Path) -> None:
    assert faststart(FIXTURES / "clip.mp4")
    late = tmp_path / "late.mp4"
    late.write_bytes(
        (16).to_bytes(4, "big")
        + b"ftypisom"
        + b"\0" * 4
        + (8).to_bytes(4, "big")
        + b"mdat"
        + (8).to_bytes(4, "big")
        + b"moov"
    )
    assert not faststart(late)
    broken = tmp_path / "broken.mp4"
    broken.write_bytes((4).to_bytes(4, "big") + b"ftyp")
    assert not faststart(broken)


def check(tmp_path: Path, value: Probe, **changes: object):
    poster = tmp_path / "poster.jpg"
    poster.write_bytes((FIXTURES / "poster.jpg").read_bytes())
    arguments = {
        "quality": "draft",
        "timing": timing(),
        "track": FIXTURES / "clip.mp4",
        "captions_text": captions(timing()),
        "chapters_text": chapters((ChapterBound(key="c01", title="Start", start=0, end=2.0),)),
        "poster": poster,
    }
    arguments.update(changes)
    return check_media(value, **arguments)


def test_a_conforming_draft_passes(tmp_path: Path) -> None:
    report = check(tmp_path, probe())
    assert report.ok, report.failed


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        ({"video_duration": 1.2}, "video.duration"),
        ({"audio_duration": 1.7}, "audio.sync"),
        ({"loudness_lufs": -23.0}, "audio.loudness"),
        ({"true_peak_dbtp": -0.2}, "audio.true_peak"),
        ({"width": 1920, "height": 1080}, "video.size"),
        ({"audio_codec": None, "audio_duration": None}, "audio.aac"),
        ({"pix_fmt": "yuv444p"}, "video.yuv420p"),
    ],
)
def test_media_defects_fail_named_rules(tmp_path: Path, value: dict, rule: str) -> None:
    report = check(tmp_path, probe(**value))
    assert any(item.startswith(rule) for item in report.failed), report.failed


def test_silent_drafts_and_overlong_cues_never_pass(tmp_path: Path) -> None:
    silent = check(tmp_path, probe(), timing=timing("silent"))
    assert any(item.startswith("narration.present") for item in silent.failed)
    late = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:09.000\nToo late\n"
    report = check(tmp_path, probe(), captions_text=late)
    assert any(item.startswith("captions.bounds") for item in report.failed)


def test_style_tokens_meet_contrast_targets_in_both_themes() -> None:
    spec = importlib.util.spec_from_file_location("video_style", STYLE)
    assert spec and spec.loader
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    for theme in ("light", "dark"):
        tokens = resolve(StyleProfile(theme=theme))["tokens"]
        background = tokens["background"]
        for name in style.TEXT_TOKENS:
            assert style.contrast(tokens[name], background) >= 4.5, name
        for color in tokens["palette"]:
            assert style.contrast(color, background) >= 3, color
        assert style.contrast(tokens["active_ink"], tokens["active"]) >= 4.5
    left, right, bottom, top = style.safe_box()
    for row, column in itertools.product(range(style.GRID), repeat=2):
        x, y = style.anchor(row, column)
        assert left < x < right and bottom < y < top
    with pytest.raises(ValueError):
        style.anchor(6, 0)


def test_palette_uses_only_effective_colors_and_rejects_invalid_tokens(tmp_path: Path) -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    path = tmp_path / "styles.css"
    original = resolve(StyleProfile())
    path.write_text(css.replace("--s1: 4px", "--s1: 7px"), encoding="utf-8")
    assert resolve(StyleProfile(), stylesheet=path) == original
    path.write_text(css.replace("--accent: #3070b3", "--accent: #205080"), encoding="utf-8")
    changed = resolve(StyleProfile(), stylesheet=path)
    assert changed["tokens"]["accent"] == "#205080"
    assert changed["tokens"]["line"] == changed["tokens"]["muted"]
    assert changed["tokens"]["frontier"] == changed["tokens"]["accent"]
    path.write_text(css.replace("--accent: #3070b3;", ""), encoding="utf-8")
    with pytest.raises(CampusError, match="--accent"):
        resolve(StyleProfile(), stylesheet=path)
    path.write_text(css.replace("--accent: #3070b3", "--accent: red"), encoding="utf-8")
    with pytest.raises(CampusError, match="--accent"):
        resolve(StyleProfile(), stylesheet=path)


def test_symbol_colors_are_preserved_but_cannot_disappear_on_canvas() -> None:
    dark = StyleProfile(theme="dark", symbol_colors={"mass": "#FFFFFF"})
    assert resolve(dark)["symbol_colors"] == {"mass": "#FFFFFF"}
    with pytest.raises(CampusError, match="mass"):
        resolve(StyleProfile(symbol_colors={"mass": "#FFFFFF"}))


def test_initial_system_theme_matches_explicit_dark() -> None:
    from tum_mcp.video_style import _declarations

    css = STYLESHEET.read_text(encoding="utf-8")
    initial = css.split("@media (prefers-color-scheme: dark)", 1)[1]
    explicit = _declarations(css, ':root[data-theme="dark"]')
    initial = _declarations(initial.replace("  :root", ":root"), ":root:not([data-theme])")
    assert initial == explicit
