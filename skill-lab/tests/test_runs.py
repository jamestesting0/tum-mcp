import json
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml
from skill_lab import LabError, collect, paths, rounds, runs

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
    (variant / "repo/src/tum_mcp").mkdir(parents=True)
    (variant / "repo/src/tum_mcp/example.py").write_text("value = 1\n")
    (variant / "repo/pyproject.toml").write_text('[project]\nname = "synthetic"\n')
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
    assert record["speed_tier"] == "standard"
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
    events = [
        json.loads(line)
        for path in (run_dir / "transcript").glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert all(event.get("_lab_timestamp") for event in events)
    phases = collect.transcript_stats(run_dir, "claude")["phase_table"]
    assert len(phases) == 6
    assert all(phase["start"] <= phase["end"] and phase["minutes"] >= 0 for phase in phases)
    shim = (run_dir / "bin" / "tum-mcp").read_text()
    assert "shim.py" in shim
    assert (run_dir / "workspace").resolve() == paths.workspaces() / "r1" / record["id"]


@pytest.mark.parametrize(
    ("author", "tier"),
    [("codex:gpt-6.1-terra:high", "standard"), ("codex:gpt-6.1-terra:high:fast", "fast")],
)
def test_collected_metrics_keep_speed_tier_from_run_author(lab_state, author, tier, monkeypatch):
    run_dir = paths.round_dir("r1") / "runs" / "base-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "author": author,
                "status": "completed",
                "variant": "base",
                "turns": [],
                "minutes": 5,
            }
        )
    )
    monkeypatch.setattr(collect, "files_outside_project", lambda *_: [])
    metrics = collect.collect_run("r1", "base-1", visuals=False)
    assert metrics["speed_tier"] == tier
    assert json.loads((run_dir / "metrics.json").read_text())["speed_tier"] == tier


def test_default_workspaces_sit_outside_the_repository(monkeypatch):
    monkeypatch.delenv("SKILL_LAB_WORKSPACES", raising=False)
    assert not paths.workspaces().is_relative_to(paths.REPO)


def test_codex_tool_consent_gets_its_canned_reply_before_the_next_scenario_turn(
    lab, monkeypatch, tmp_path
):
    from skill_lab.models import ModelSpec

    executable = tmp_path / "fake-bin" / "codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """
            import json, os, pathlib, sys
            message = sys.argv[-1]
            work = pathlib.Path.cwd()
            with (work / "messages.txt").open("a") as messages:
                messages.write(message + "\\n")
            session = pathlib.Path(os.environ["HOME"]) / ".codex/sessions/rollout-t-consent.jsonl"
            session.parent.mkdir(parents=True, exist_ok=True)
            with session.open("a") as log:
                log.write(json.dumps({"type": "turn_context", "payload": {
                    "model": "gpt-6.1-terra"
                }}) + "\\n")
                log.write(json.dumps({"type": "response_item", "payload": {
                    "type": "message", "role": "user"
                }}) + "\\n")
                if message.startswith("Set up"):
                    log.write(json.dumps({"type": "response_item", "payload": {
                        "type": "function_call", "name": "request_user_input_async",
                        "arguments": json.dumps({"questions": [
                            {"title": "Which course do you mean?"}
                        ]})
                    }}) + "\\n")
            for event in (
                {"type": "thread.started", "thread_id": "t-consent"},
                {"type": "item.completed", "item": {
                    "type": "agent_message", "text": "Waiting for the choice above."
                }},
                {"type": "turn.completed"},
            ):
                print(json.dumps(event))
            """
        )
    )
    executable.chmod(0o755)
    record = execute(lab, author=ModelSpec.parse("codex:gpt-6.1-terra:high"))
    assert record["status"] == "completed", record.get("error")
    assert record["turns"][0]["replies"] == ["The AI course."]
    assert record["turns"][1]["replies"] == []
    workspace = paths.round_dir("r1") / "runs" / record["id"] / "workspace"
    assert (workspace / "messages.txt").read_text().splitlines() == [
        "Set up my course project.",
        "The AI course.",
        "Build lessons.",
    ]


def test_checkpoint_run_starts_after_the_named_turn(lab):
    first = execute(lab)
    record = execute(lab, checkpoint=f"{first['id']}@1")
    assert record["status"] == "completed"
    assert [turn["turn"] for turn in record["turns"]] == [2]
    run_dir = paths.round_dir("r1") / "runs" / record["id"]
    messages = (run_dir / "workspace" / "messages.txt").read_text().splitlines()
    assert messages[-1] == "Build lessons." and messages[0] == "Set up my course project."


def test_checkpoint_reuses_the_identical_installed_patch(lab, tmp_path):
    variant = paths.round_dir("r1") / "variants/base"
    patch = tmp_path / "sync.patch"
    patch.write_text(
        "--- a/src/tum_mcp/bundled/skills/sync-course/SKILL.md\n"
        "+++ b/src/tum_mcp/bundled/skills/sync-course/SKILL.md\n"
    )
    record = json.loads((variant / "variant.json").read_text())
    record["spec"]["patches"] = [{"path": str(patch), "sha256": "recorded"}]
    (variant / "variant.json").write_text(json.dumps(record))
    first = execute(lab)
    resumed = execute(lab, checkpoint=f"{first['id']}@1")
    assert resumed["status"] == "completed"
    assert [turn["turn"] for turn in resumed["turns"]] == [2]


def test_checkpoint_refuses_changed_code_in_a_new_base_without_a_patch(lab):
    first = execute(lab)
    old = paths.round_dir("r1") / "variants/base"
    new = old.with_name("changed-base")
    shutil.copytree(old, new)
    record = json.loads((new / "variant.json").read_text())
    record["spec"]["ref"] = "another-base"
    (new / "variant.json").write_text(json.dumps(record))
    (new / "repo/src/tum_mcp/example.py").write_text("value = 2\n")
    with pytest.raises(LabError, match="changes code"):
        runs.execute(
            "r1",
            "changed-base",
            checkpoint=f"{first['id']}@1",
            installer=lambda *args: lab.append(args),
            campus_check=lambda: None,
            python=__import__("pathlib").Path(sys.executable),
        )


def test_checkpoint_restore_releases_only_copied_task_ownership(lab, tmp_path):
    first = execute(lab)
    run_dir = paths.round_dir("r1") / "runs" / first["id"]
    original = {
        "phase": "pending",
        "owner": "codex:previous",
        "requirements": {"lecture": {"source_cases": {"source/case": "original"}}},
    }
    task = run_dir / "workspace/.tum-mcp/task.json"
    task.write_text(json.dumps(original))
    runs.snapshot(run_dir / "history.git", run_dir / "workspace", 3)
    destination = tmp_path / "restored"
    destination.mkdir()
    runs.restore(run_dir / "history.git", 3, destination)
    restored = json.loads((destination / ".tum-mcp/task.json").read_text())
    assert restored["phase"] == "paused"
    assert restored["owner"] == original["owner"]
    assert restored["requirements"] == original["requirements"]
    assert json.loads(task.read_text()) == original


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
