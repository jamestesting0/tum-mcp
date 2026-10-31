import json

import pytest
from skill_lab import LabError, judge, ledger, paths, rounds


def test_blind_ids_are_stable_and_hide_variant_names():
    first = judge.assign_ids("r1|base-1|inv-1|0")
    assert first == judge.assign_ids("r1|base-1|inv-1|0")
    assert set(first) == {"A", "B"} and set(first.values()) == {"left", "right"}


def test_verdict_parsing_and_unblinding():
    text = (
        "Reasoning...\n```json\n"
        '{"scores": {"A": {"clarity": 3}, "B": {"clarity": 2}},'
        ' "preference": {"clarity": "A"}, "overall": "A", "why": "clearer steps"}\n```'
    )
    verdict = judge.parse_verdict(text)
    named = judge.unblind(verdict, {"A": "right", "B": "left"}, {"left": "base", "right": "inv"})
    assert named["overall"] == "inv"
    assert named["preference"] == {"clarity": "inv"}
    assert named["scores"]["base"] == {"clarity": 2}
    with pytest.raises(LabError):
        judge.parse_verdict("no block here")
    with pytest.raises(LabError):
        judge.parse_verdict('```json\n{"scores": {}, "preference": {}, "overall": "C"}\n```')


def test_review_parsing_and_other_host_reviewer():
    review = judge.parse_review(
        'Notes\n```json\n{"scores": {"lessons": {"clarity": 2}, "exercises": null},'
        ' "findings": [{"dimension": "clarity", "where": "L1", "problem": "p", "fix": "f"}]}\n```'
    )
    assert review["findings"][0]["where"] == "L1"
    with pytest.raises(LabError):
        judge.parse_review('```json\n{"scores": {}}\n```')
    config = {
        "confirm_judges": [
            {"host": "claude", "model": "claude-opus-5-5", "effort": "xhigh"},
            {"host": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"},
        ]
    }
    assert str(judge.other_host_reviewer(config, "claude")) == "codex:gpt-6.1-sol:xhigh"
    assert str(judge.other_host_reviewer(config, "codex")) == "claude:claude-opus-5-5:xhigh"


DECISION = """## Weakness
Dense lesson blocks.

## Edits
- prepare-study writing reference: split rule -> fewer long blocks -> helped

## Lesson
No lesson.

## Decision
Dropped; the confirmation judges disagreed.
"""


def test_ledger_rejects_unsafe_text_and_appends_clean_entries(lab_state, tmp_path):
    rounds.save(
        "r1",
        {
            "scenario": "smoke",
            "confirm_scenario": None,
            "roles": {
                "author": {"host": "claude", "model": "opus", "effort": "high"},
                "judge": {"host": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"},
            },
            "base": {"ref": "0123456789abcdef", "patches": []},
        },
    )
    target = tmp_path / "ledger.md"
    target.write_text("# Ledger\n")
    decision = tmp_path / "decision.md"
    for unsafe in (
        DECISION + "\nSee https://www.moodle.tum.de/course/view.php?id=1\n",
        DECISION + "\n> quoted slide text\n",
        DECISION + "\nFile at /Users/someone/x\n",
        "## Weakness\nOnly one section.\n",
    ):
        decision.write_text(unsafe)
        with pytest.raises(LabError):
            ledger.add("r1", decision, target)
    decision.write_text(DECISION)
    ledger.add("r1", decision, target)
    text = target.read_text()
    assert "## r1 (" in text and "### Weakness" in text and "author: claude:opus:high" in text


def fake_run(round_id, run_id, author, started, workspaces, materials):
    run_dir = paths.round_dir(round_id) / "runs" / run_id
    app = run_dir / "workspace" / "app"
    app.mkdir(parents=True)
    for name in (*workspaces, "data.mjs"):
        (app / name).write_text("{}")
    for name in materials:
        (run_dir / "workspace" / "materials" / name).parent.mkdir(parents=True, exist_ok=True)
        (run_dir / "workspace" / "materials" / name).write_text(name)
    record = {
        "id": run_id,
        "round": round_id,
        "variant": run_id.rsplit("-", 1)[0],
        "author": author,
        "scenario": "s",
        "status": "completed",
        "started": started,
        "project": ".",
        "inventory_hash": ",".join(materials),
    }
    (run_dir / "run.json").write_text(json.dumps(record))
    return record


def test_a_round_judges_its_candidates_against_the_previous_rounds_runs(lab_state):
    # Given an earlier round's runs by two authors and one candidate per author now.
    claude, codex = "claude:sonnet:high", "codex:gpt-6.1-terra:xhigh"
    fake_run("t1", "base-1", claude, "1", ["content.json"], ["a.pdf"])
    fake_run("t1", "base-2", claude, "2", ["content.json", "exercises.json"], ["a.pdf"])
    fake_run("t1", "base-3", codex, "3", ["content.json"], ["a.pdf"])
    assert sorted(rounds.inherited_baselines("t1")) == ["t1/base-2", "t1/base-3"]
    rounds.save("r1", {"baselines": ["t1/base-2", "t1/base-3"]})
    fake_run("r1", "candidate-1", codex, "4", ["content.json", "exam.json"], ["a.pdf", "b.pdf"])
    fake_run("r1", "candidate-2", claude, "5", ["content.json", "exercises.json"], ["a.pdf"])
    # When the round pairs runs, each baseline meets the newest candidate by its author.
    assert judge.default_pairs("r1") == [["t1/base-2", "candidate-2"], ["t1/base-3", "candidate-1"]]
    # Then a packet holds only the workspaces both built, and every material either read.
    left = judge.find_run("r1", "t1/base-3")
    right = judge.find_run("r1", "candidate-1")
    packet = lab_state / "packet"
    built = judge.build_packet("k", left, right, packet)
    assert built["unjudged"] == {"Exam": "candidate-1"}
    assert built["same_materials"] is False
    assert sorted(p.name for p in (packet / "sources").iterdir()) == ["a.pdf", "b.pdf"]
    for letter in ("A", "B"):
        app = packet / "candidates" / letter / "app"
        assert sorted(p.name for p in app.iterdir()) == ["content.json"]
    with pytest.raises(LabError):
        rounds.checked_baselines(["base-2"])
