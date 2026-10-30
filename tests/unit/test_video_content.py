import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.study_content import StudyContent
from tum_mcp.video_content import (
    Locator,
    Selection,
    Storyboard,
    VideoPlan,
    VoiceProfile,
    allocate,
    check_storyboard,
    chunk_name,
    compose_timing,
    locator_fingerprint,
    semantic_hash,
    voice_tag,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/course_app/content.json"


@pytest.fixture
def content() -> StudyContent:
    return StudyContent.model_validate_json(FIXTURE.read_bytes())


def locate(content: StudyContent, unit: str, kind: str, ref: str) -> dict:
    target = next(item for item in content.units if item.key == unit)
    probe = Locator(kind=kind, ref=ref, fingerprint="0" * 64)
    return {"kind": kind, "ref": ref, "fingerprint": locator_fingerprint(target, probe)}


def storyboard(content: StudyContent, **changes: object) -> dict:
    unit = next(item for item in content.units if item.key == "bfs")
    question = unit.questions[0]
    value = {
        "video": "01_breadth-first-search",
        "unit": "bfs",
        "unit_hash": semantic_hash(unit),
        "title": "Breadth-first search",
        "language": "en",
        "objectives": [question.objective],
        "chapters": [
            {
                "key": "c01",
                "title": "Layers",
                "beats": [
                    {
                        "key": "b01",
                        "kind": "hook",
                        "narration": ["Which node does the search reach next?"],
                        "intent": "Show the start node.",
                        "locators": [locate(content, "bfs", "summary", "summary")],
                        "on_screen": [{"key": "start", "kind": "label", "text": "s"}],
                    },
                    {
                        "key": "b02",
                        "kind": "question",
                        "narration": ["Pause and decide."],
                        "pause_s": 3,
                        "question": question.key,
                        "intent": "Ask the practice question.",
                        "locators": [locate(content, "bfs", "question", question.key)],
                    },
                ],
            }
        ],
    }
    value.update(changes)
    return value


def test_teaching_hash_ignores_layout_provenance_and_navigation(content: StudyContent) -> None:
    unit = next(item for item in content.units if item.key == "bfs")
    original = semantic_hash(unit)
    data = unit.model_dump(mode="json")
    data["minutes"] += 5
    data["path"] = ["Moved"]
    data["label"] = "Renamed eyebrow"
    for block in data["blocks"]:
        if block["kind"] == "diagram":
            shift = 5 - max(node["row"] for node in block["nodes"])
            for node in block["nodes"]:
                node["row"] += shift
    moved = type(unit).model_validate(data)
    assert semantic_hash(moved) == original
    data["summary"] = data["summary"] + " Changed meaning."
    assert semantic_hash(type(unit).model_validate(data)) != original


def test_valid_storyboard_maps_objectives_and_estimates_length(content: StudyContent) -> None:
    report = check_storyboard(Storyboard.model_validate(storyboard(content)), content)
    assert report.errors == ()
    assert report.estimated_seconds > 3 and report.words == 10
    assert any(item.startswith("objective.not_in_video") for item in report.warnings)


def test_storyboard_reports_stale_units_changed_locators_and_unknown_items(
    content: StudyContent,
) -> None:
    value = storyboard(content, unit_hash="1" * 64, objectives=["missing-objective"])
    value["chapters"][0]["beats"][0]["locators"][0]["fingerprint"] = "2" * 64
    value["chapters"][0]["beats"][1]["question"] = "no-such-question"
    report = check_storyboard(Storyboard.model_validate(value), content)
    rules = {error.split(":")[0].split(" ")[0] for error in report.errors}
    assert {"unit.stale", "locator.changed", "question.missing", "objective.missing"} <= rules


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("beats", 1, "question"), None, "Question beats"),
        (("beats", 1, "pause_s"), 1, "Question beats"),
        (("beats", 0, "narration"), [], "intentional pause"),
        (("beats", 1, "key"), "b01", "Beat keys"),
        (("beats", 0, "on_screen"), [{"key": "m", "kind": "math", "typst": "#read(x)"}], "#"),
        (("beats", 0, "on_screen"), [{"key": "m", "kind": "label", "typst": "x"}], "exactly"),
    ],
)
def test_storyboard_rejects_unsafe_or_inconsistent_beats(
    content: StudyContent, path: tuple, replacement: object, message: str
) -> None:
    value = storyboard(content)
    target = value["chapters"][0]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement
    with pytest.raises(ValidationError, match=message):
        Storyboard.model_validate(value)


def test_stems_stay_stable_and_new_videos_take_unused_numbers(content: StudyContent) -> None:
    first = allocate(
        None, (Selection(unit="bfs", decision="video", reason="Trace."),), content, frozenset()
    )
    plan = VideoPlan(course_key=content.course_key, content_sha256="0" * 64, videos=first)
    selections = (
        Selection(unit="graphs", decision="video", reason="Structure."),
        Selection(unit="dfs", decision="text-first", reason="Mostly a table."),
        Selection(unit="bfs", decision="video", reason="Still a trace."),
    )
    second = allocate(plan, selections, content, frozenset({"02_taken"}))
    stems = {item.unit: item.stem for item in second}
    assert stems["bfs"] == first[0].stem and stems["bfs"].startswith("01_")
    assert stems["graphs"].startswith("03_") and stems["dfs"] is None
    assert [item.unit for item in second] == [
        unit.key for unit in content.units if unit.key in stems
    ]
    # A unit set to text-first and later re-selected keeps its published stem.
    paused = VideoPlan(course_key=content.course_key, content_sha256="0" * 64, videos=second)
    again = allocate(
        paused,
        (Selection(unit="dfs", decision="video", reason="Now a trace."),),
        content,
        frozenset({"02_taken", "04_depth-first"}),
        {"dfs": "04_depth-first"},
    )
    assert {item.unit: item.stem for item in again}["dfs"] == "04_depth-first"


def test_timing_lays_out_measured_sentences_and_pauses(content: StudyContent) -> None:
    board = Storyboard.model_validate(storyboard(content))
    timing = compose_timing(board, "a" * 64, "silent", {"b01/1": (2.0, None), "b02/1": (1.0, None)})
    first, second = timing.beats
    assert first.cues[0].start == 0.25 and first.duration == 2.45
    assert second.start == 2.45 and second.duration == pytest.approx(0.25 + 1 + 0.2 + 3)
    assert timing.total == pytest.approx(second.start + second.duration)


def test_chunk_names_change_with_text_and_voice_settings() -> None:
    profile = VoiceProfile(provider="kokoro", route="local", voice="af_heart", language="en")
    faster = profile.model_copy(update={"settings": {"speed": 1.1}})
    tag, other = voice_tag("narrator", profile), voice_tag("narrator", faster)
    assert tag != other
    assert chunk_name("b01", 1, "A sentence.", tag) != chunk_name("b01", 1, "A sentence!", tag)
    assert chunk_name("b01", 1, "A sentence.", tag) != chunk_name("b01", 1, "A sentence.", other)
    assert json.dumps(chunk_name("b01", 1, "x", tag)).startswith('"b01_01-')
