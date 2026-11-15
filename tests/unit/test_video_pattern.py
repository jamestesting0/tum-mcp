from importlib.resources import files

import pytest

from tum_mcp.course.content.exam import ExamContent, Pattern
from tum_mcp.course.media.sources import part_fingerprint, required_parts, teaching_hash
from tum_mcp.course.media.video_content import PatternStoryboard
from tum_mcp.course.media.video_sources import VideoSource, check_pattern


@pytest.fixture
def pattern() -> Pattern:
    example = files("tum_mcp.bundled.course_app.example").joinpath("exam.json").read_bytes()
    return ExamContent.model_validate_json(example).patterns[0]


def locate(pattern: Pattern, kind: str, ref: str) -> dict:
    return {"kind": kind, "ref": ref, "fingerprint": part_fingerprint(pattern, kind, ref)}


def board(pattern: Pattern) -> dict:
    steps = range(len(pattern.workflow))
    beats = [
        ("cue", [("cue", f"cues[{i}]") for i in range(len(pattern.cues))], 0),
        *(("step", [("workflow", f"workflow[{i}]")], 1) for i in steps),
        *(
            ("example", [("example", "examples[0]"), ("workflow", f"workflow[{i}]")], 1)
            for i in steps
        ),
        ("pitfall", [("pitfall", "pitfalls[0]")], 2),
        ("recap", [("marking", "marking")], 0),
    ]
    return {
        "video": "01_name-structure",
        "pattern": pattern.key,
        "pattern_hash": teaching_hash(pattern),
        "title": pattern.title,
        "language": "en",
        "chapters": [
            {
                "key": "c01",
                "title": "The method",
                "beats": [
                    {
                        "key": f"b{n:02d}",
                        "kind": kind,
                        "narration": [f"Beat {n} names {kind} work for the pattern."],
                        "intent": "Teach this part.",
                        "locators": [locate(pattern, k, r) for k, r in parts],
                        "on_screen": [
                            {"key": f"s{n}-{j}", "kind": "label", "text": f"Item {j}"}
                            for j in range(shown)
                        ],
                    }
                    for n, (kind, parts, shown) in enumerate(beats, 1)
                ],
            }
        ],
    }


def errors(pattern: Pattern, value: dict) -> tuple[str, ...]:
    source = VideoSource(f"exam/patterns/{pattern.key}", pattern)
    return check_pattern(PatternStoryboard.model_validate(value), source).errors


def test_a_complete_pattern_video_covers_every_required_part(pattern: Pattern) -> None:
    assert {kind for kind, _ in required_parts(pattern)} >= {"cue", "workflow", "example"}
    assert errors(pattern, board(pattern)) == ()


@pytest.mark.parametrize("defect", ["step", "order", "apply", "pitfall", "cue"])
def test_a_pattern_video_names_what_it_misses(pattern: Pattern, defect: str) -> None:
    value = board(pattern)
    beats = value["chapters"][0]["beats"]
    first_step = next(beat for beat in beats if beat["kind"] == "step")
    examples = [beat for beat in beats if beat["kind"] == "example"]
    match defect:
        case "step":
            # The worked example still passes through the step, which is not teaching it.
            beats.remove(first_step)
            expected = "pattern.step workflow[0]"
        case "order":
            examples[0]["locators"], examples[1]["locators"] = (
                examples[1]["locators"],
                examples[0]["locators"],
            )
            expected = "pattern.example examples[0]"
        case "apply":
            first_step["on_screen"] = []
            expected = f"pattern.apply {first_step['key']}"
        case "pitfall":
            next(beat for beat in beats if beat["kind"] == "pitfall")["on_screen"].pop()
            expected = "pattern.pitfall"
        case _:
            beats[0]["kind"] = "step"
            beats[0]["on_screen"] = [{"key": "cue-shown", "kind": "label", "text": "When"}]
            expected = "pattern.cue"
    assert any(error.startswith(expected) for error in errors(pattern, value))
