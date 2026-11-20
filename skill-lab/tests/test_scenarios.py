import pytest
import yaml
from skill_lab import LabError, scenarios


def test_tracked_scenarios_parse_and_list_their_skills():
    names = scenarios.available()
    assert {"setup-and-study", "exercises", "pick-course", "smoke"} <= set(names)
    for name in names:
        scenario = scenarios.load(name)
        assert scenario.turns


def test_specific_replies_do_not_approve_unmatched_actions():
    scenario = scenarios.parse(
        {
            "id": "consent",
            "turns": ["Prepare my study lessons."],
            "replies": {"learning record": "Keep the learning record off."},
        },
        "consent",
    )
    assert scenario.reply_to("Keep a private learning record?") == "Keep the learning record off."
    assert scenario.reply_to("May I publish the course?") is None


def test_local_override_merges_replies_and_can_replace_turns(lab_state):
    override = lab_state / "scenarios" / "smoke.yaml"
    override.parent.mkdir(parents=True)
    override.write_text(yaml.safe_dump({"replies": {"course": "Course X"}}))
    scenario = scenarios.load("smoke")
    assert scenario.replies["course"] == "Course X"
    assert scenario.replies["default"]
    assert scenario.reply_to("Which COURSE do you mean?") == "Course X"
    assert scenario.reply_to("Shall I continue?") == scenario.replies["default"]


@pytest.mark.parametrize("name", ["fai-authoring-026", "fai-authoring-026-resume"])
def test_scored_scenario_ignores_overrides_and_never_answers_questions(lab_state, name):
    expected = scenarios.load(name)
    override = lab_state / "scenarios" / f"{name}.yaml"
    override.parent.mkdir(parents=True)
    override.write_text(yaml.safe_dump({"turns": ["Override"], "replies": {"course": "Leak"}}))

    actual = scenarios.load(name)

    assert actual.turns == expected.turns
    assert actual.reply_to("Which course?") is None


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


def test_code_drift_is_accepted_only_when_later_turns_never_rebuild_restored_content():
    media = scenarios.parse(
        {
            "id": "m",
            "turns": [
                {"say": "Prepare study.", "skills": ["prepare-study"]},
                {"say": "Make a video.", "skills": ["video-notes", "read-content"]},
                {"say": "Review it.", "skills": ["review-course", "video-notes"]},
            ],
        },
        "m",
    )
    assert scenarios.drift_refusal(media, 1) is None
    assert "prepare-study" in scenarios.drift_refusal(media, 0)
    assert "does not list" in scenarios.drift_refusal(scenarios.load("smoke"), 0)


def test_bad_scenarios_are_rejected():
    with pytest.raises(LabError):
        scenarios.parse({"id": "x", "turns": [{"skills": []}]}, "x")
    with pytest.raises(LabError):
        scenarios.load("missing-scenario")


def test_drift_allows_building_a_workspace_the_checkpoint_lacks():
    exam = scenarios.Scenario(
        "exam-after-restore",
        [
            scenarios.Turn("Set up.", ["sync-course"]),
            scenarios.Turn("Prepare the exam.", ["prepare-exams"]),
        ],
    )
    assert scenarios.drift_refusal(exam, 1, frozenset({"study", "exercises"})) is None
    assert "prepare-exams" in scenarios.drift_refusal(exam, 1, frozenset({"study", "exam"}))
    assert scenarios.drift_refusal(exam, 0, frozenset()) is None


def test_drift_allows_a_turn_that_only_adds_to_a_restored_workspace():
    practice = scenarios.Scenario(
        "exam-practice",
        [
            scenarios.Turn("Patterns.", ["prepare-exams"]),
            scenarios.Turn("Practice exam.", ["prepare-exams"], ["exam"]),
            scenarios.Turn("Patterns again.", ["prepare-exams"]),
        ],
    )
    assert scenarios.drift_refusal(practice, 1, frozenset({"exam"})) is not None
    two = scenarios.Scenario("two", practice.turns[:2])
    assert scenarios.drift_refusal(two, 1, frozenset({"exam"})) is None
