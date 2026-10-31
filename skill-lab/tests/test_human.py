import json

import pytest
from skill_lab import LabError, human, paths


def make_run(round_id="r1", run_id="base-1", comments=None):
    run_dir = paths.round_dir(round_id) / "runs" / run_id
    project = run_dir / "workspace"
    (project / ".tum-mcp").mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"id": run_id, "project": "."}))
    if comments is not None:
        (project / ".tum-mcp" / "comments.json").write_text(
            json.dumps({"schema_version": 3, "course_identity": "x", "comments": comments})
        )
    return run_dir


COMMENT = {
    "id": "00000000-0000-0000-0000-000000000001",
    "anchor": {
        "view": "content",
        "unit_key": "agents",
        "block_title": "Agent programs",
        "quote": "the agent function maps",
    },
    "text": "This step jumps ahead; show the table first.",
    "status": "open",
}


def test_in_app_comments_and_notes_become_review_evidence(lab_state):
    make_run(comments=[COMMENT, {**COMMENT, "status": "resolved", "text": "Fine now."}])
    human.add_note("r1", "base-1", "Lessons are too dense in lecture 2.")
    evidence = human.export("r1", "base-1")
    assert "too dense" in evidence["notes"]
    assert evidence["comments"][0] == {
        "status": "open",
        "view": "content",
        "where": "Agent programs",
        "item": None,
        "quote": "the agent function maps",
        "note": "This step jumps ahead; show the table first.",
    }
    summary = human.summary("r1", "base-1")
    assert summary == {"run": "base-1", "notes": True, "comments": 2, "open_comments": 1}
    assert (paths.round_dir("r1") / "human" / "base-1.json").is_file()


def test_runs_without_comments_and_unknown_runs(lab_state):
    make_run()
    assert human.summary("r1", "base-1")["comments"] == 0
    with pytest.raises(LabError):
        human.add_note("r1", "missing-1", "note")
    with pytest.raises(LabError):
        human.add_note("r1", "base-1", "   ")
