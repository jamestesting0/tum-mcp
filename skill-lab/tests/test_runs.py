import json
import subprocess
import sys
import textwrap

import pytest
import yaml
from skill_lab import LabError, paths, rounds, runs

FAKE_CLAUDE = textwrap.dedent(
    """
    import json, os, pathlib, sys
    args = sys.argv[1:]
    message = args[args.index("-p") + 1]
    session = args[args.index("--resume") + 1] if "--resume" in args else "session-1"
    work = pathlib.Path.cwd()
    (work / ".tum-mcp").mkdir(exist_ok=True)
    (work / ".tum-mcp" / "state.json").write_text("{}")
    (work / "materials").mkdir(exist_ok=True)
    (work / "materials" / "lecture-1.txt").write_text("lecture one")
    with open(work / "messages.txt", "a") as log:
        log.write(message + "\\n")
    text = "Which course do you mean?" if message.startswith("Set up") else "Done."
    shell = "Bearer " + "x" * 32 if os.environ.get("FAKE_LEAK") else "listed files"
    if os.environ.get("FAKE_EXPIRED") and message == "Build lessons.":
        shell = "Error executing tool moodle_list_courses: SESSION_EXPIRED: Reconnect."
    for event in (
        {"type": "system", "subtype": "init", "session_id": session, "model": "claude-sonnet-5"},
        {"type": "assistant", "message": {"model": "claude-sonnet-5", "content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__tum__tumonline_list_studies"},
            {"type": "tool_use", "id": "t2", "name": "Bash"},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "Private programme"},
            {"type": "tool_result", "tool_use_id": "t2", "content": shell},
        ]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": text,
         "session_id": session, "usage": {"input_tokens": 10, "output_tokens": 5}},
    ):
        print(json.dumps(event))
    """
)


@pytest.fixture
def lab(lab_state, tmp_path, monkeypatch):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    claude = fake_bin / "claude"
    claude.write_text(f"#!{sys.executable}\n{FAKE_CLAUDE}")
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{__import__('os').environ['PATH']}")
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "trial.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "trial",
                "turns": [
                    {"say": "Set up my course project.", "skills": ["sync-course"]},
                    {"say": "Build lessons.", "skills": ["prepare-study"]},
                ],
                "replies": {"course": "The AI course.", "default": "Go ahead."},
            }
        )
    )
    monkeypatch.setattr(paths, "SCENARIOS", scenario_dir)
    rounds.save(
        "r1",
        {
            "id": "r1",
            "scenario": "trial",
            "confirm_scenario": None,
            "roles": {
                "author": {"host": "claude", "model": "sonnet", "effort": "high"},
                "judge": {"host": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"},
            },
            "confirm_judges": [],
            "base": {"ref": "WORKTREE", "patches": []},
            "budget": {"runs": 5, "judge_sessions": 4, "turn_timeout_min": 1},
        },
    )
    variant = paths.round_dir("r1") / "variants" / "base"
    variant.mkdir(parents=True)
    (variant / "variant.json").write_text(
        json.dumps({"name": "base", "spec": {"ref": "WORKTREE", "patches": []}})
    )
    installs = []
    return installs


def execute(installs, **options):
    return runs.execute(
        "r1",
        "base",
        installer=lambda *args: installs.append(args),
        campus_check=lambda: None,
        python=__import__("pathlib").Path(sys.executable),
        **options,
    )


def test_fresh_run_answers_questions_snapshots_turns_and_redacts(lab):
    record = execute(lab)
    assert record["status"] == "completed", record.get("error")
    assert len(lab) == 1 and lab[0][1] == "claude"
    first, second = record["turns"]
    assert first["replies"] == ["The AI course."]
    assert second["replies"] == []
    assert record["models_reported"] == ["claude-sonnet-5"]
    assert record["project"] == "." and record["inventory_hash"]
    run_dir = paths.round_dir("r1") / "runs" / record["id"]
    messages = (run_dir / "workspace" / "messages.txt").read_text().splitlines()
    assert messages == ["Set up my course project.", "The AI course.", "Build lessons."]
    tags = subprocess.run(
        ["git", f"--git-dir={run_dir / 'history.git'}", "tag"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tags == ["turn-1", "turn-2"]
    assert not (run_dir / "raw").exists()
    transcript = "".join(p.read_text() for p in (run_dir / "transcript").glob("*.jsonl"))
    assert "Private programme" not in transcript and '"redacted": true' in transcript
    assert "listed files" in transcript
    shim = (run_dir / "bin" / "tum-mcp").read_text()
    assert "shim.py" in shim
    assert (run_dir / "workspace").resolve() == paths.workspaces() / "r1" / record["id"]


def test_default_workspaces_sit_outside_the_repository(monkeypatch):
    monkeypatch.delenv("SKILL_LAB_WORKSPACES", raising=False)
    assert not paths.workspaces().is_relative_to(paths.REPO)


def test_checkpoint_run_starts_after_the_named_turn(lab):
    first = execute(lab)
    record = execute(lab, checkpoint=f"{first['id']}@1")
    assert record["status"] == "completed"
    assert [turn["turn"] for turn in record["turns"]] == [2]
    run_dir = paths.round_dir("r1") / "runs" / record["id"]
    messages = (run_dir / "workspace" / "messages.txt").read_text().splitlines()
    assert messages[-1] == "Build lessons." and messages[0] == "Set up my course project."


def test_credential_text_quarantines_the_run(lab, monkeypatch, lab_state):
    monkeypatch.setenv("FAKE_LEAK", "1")
    record = execute(lab)
    assert record["status"] == "quarantined"
    assert not (paths.round_dir("r1") / "runs" / record["id"]).exists()
    assert (lab_state / "quarantine" / f"r1-{record['id']}" / "run.json").is_file()


def test_moodle_must_be_ready_before_a_live_run():
    runs.require_moodle({"Moodle": "Ready"})
    with pytest.raises(LabError, match="tum-mcp login"):
        runs.require_moodle({"Moodle": "Action needed"})


def test_an_expired_campus_session_stops_the_run(lab, monkeypatch):
    monkeypatch.setenv("FAKE_EXPIRED", "1")
    record = execute(lab)
    assert record["status"] == "campus-session-expired"
    assert "tum-mcp login" in record["error"]
    assert [turn["turn"] for turn in record["turns"]] == [1, 2]


def test_one_trial_per_host_with_hosts_side_by_side_within_the_budget(lab, lab_state):
    from filelock import FileLock

    # A live trial of the same host blocks the run.
    held = FileLock(str(lab_state / "live-claude.lock"))
    held.acquire()
    try:
        with pytest.raises(LabError, match="one at a time"):
            execute(lab)
    finally:
        held.release()
    # A live trial of the other host does not; run ids stay distinct.
    other = FileLock(str(lab_state / "live-codex.lock"))
    other.acquire()
    try:
        first, second = execute(lab), execute(lab)
    finally:
        other.release()
    assert first["id"] != second["id"]
    config = rounds.load("r1")
    config["budget"]["runs"] = 2
    rounds.save("r1", config)
    with pytest.raises(LabError, match="budget"):
        execute(lab)
