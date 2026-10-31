import pytest
import yaml
from skill_lab import LabError, scenarios


def test_tracked_scenarios_parse_and_list_their_skills():
    names = scenarios.available()
    assert {"setup-and-study", "exercises", "pick-course", "smoke"} <= set(names)
    for name in names:
        scenario = scenarios.load(name)
        assert scenario.turns and scenario.replies.get("default")


def test_local_override_merges_replies_and_can_replace_turns(lab_state):
    override = lab_state / "scenarios" / "smoke.yaml"
    override.parent.mkdir(parents=True)
    override.write_text(yaml.safe_dump({"replies": {"course": "Course X"}}))
    scenario = scenarios.load("smoke")
    assert scenario.replies["course"] == "Course X"
    assert scenario.replies["default"]
    assert scenario.reply_to("Which COURSE do you mean?") == "Course X"
    assert scenario.reply_to("Shall I continue?") == scenario.replies["default"]


LIVE_QUESTION_BEFORE_OPTIONS = """Moodle shows no release dates. Which sheet do you want?

1. **Exercise 1** is my recommendation.

2. **Exercise 2a** is plausible.

3. **Another sheet number:** tell me which one and I'll fetch it.

I'll record the unconfirmed status in the coverage ledger."""

LIVE_REQUEST_WITHOUT_QUESTION_MARK = (
    "I couldn't identify the latest released sheet, so I haven't added exercises yet.\n\n"
    "Please select the intended sheet in the question above; I can then prepare it."
)

LIVE_UNRELATED_COURSE_MENTION = (
    "I worked in the course project for this course.\n\n"
    "Should I redraw the timeline so the review can pass?"
)


def test_live_question_shapes_are_detected_and_matched():
    scenario = scenarios.parse(
        {
            "id": "x",
            "turns": ["go"],
            "replies": {"course": "AI.", "sheet": "Sheet 1.", "default": "Go ahead."},
        },
        "x",
    )
    assert scenarios.asks_student(LIVE_QUESTION_BEFORE_OPTIONS)
    assert scenario.reply_to(LIVE_QUESTION_BEFORE_OPTIONS) == "Sheet 1."
    assert scenarios.asks_student(LIVE_REQUEST_WITHOUT_QUESTION_MARK)
    assert scenario.reply_to(LIVE_REQUEST_WITHOUT_QUESTION_MARK) == "Sheet 1."
    assert scenario.reply_to(LIVE_UNRELATED_COURSE_MENTION) == "Go ahead."


def test_question_detection():
    assert scenarios.asks_student("Which course should I use?")
    assert scenarios.asks_student("Proceed with **Fundamentals of AI**?**")
    assert not scenarios.asks_student("Done. The project is ready.")
    assert scenarios.asks_student(
        "Several courses match.\n\nIs it Fundamentals of AI? If so, I'll set it up."
    )
    assert not scenarios.asks_student("Why does it work?\n\nIt converges.\n\nDone.\n\nAll set.")


def test_checkpoint_reuse_is_refused_when_earlier_turns_used_the_change():
    scenario = scenarios.load("setup-and-study")
    study = ["src/tum_mcp/bundled/skills/prepare-study/references/writing.md"]
    sync = ["src/tum_mcp/bundled/skills/sync-course/SKILL.md"]
    code = ["src/tum_mcp/study_report.py"]
    assert scenarios.checkpoint_refusal(scenario, 1, study) is None
    assert "earlier turn used" in scenarios.checkpoint_refusal(scenario, 1, sync)
    assert "changes code" in scenarios.checkpoint_refusal(scenario, 1, code)
    assert scenarios.checkpoint_refusal(scenario, 0, code) is None
    assert "does not list" in scenarios.checkpoint_refusal(scenarios.load("smoke"), 2, study)


def test_bad_scenarios_are_rejected():
    with pytest.raises(LabError):
        scenarios.parse({"id": "x", "turns": [{"skills": []}]}, "x")
    with pytest.raises(LabError):
        scenarios.load("missing-scenario")
