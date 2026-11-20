import pytest
from skill_lab import safety, shim

SKILL = "src/tum_mcp/bundled/skills/prepare-study/SKILL.md"
PATCH = (
    f"diff --git a/{SKILL} b/{SKILL}\n"
    + """--- a/src/tum_mcp/bundled/skills/prepare-study/SKILL.md
+++ b/src/tum_mcp/bundled/skills/prepare-study/SKILL.md
@@ -1 +1 @@
-old
+new
diff --git a/src/tum_mcp/moodle/service.py b/src/tum_mcp/moodle/service.py
--- a/src/tum_mcp/moodle/service.py
+++ b/src/tum_mcp/moodle/service.py
@@ -1 +1 @@
-a
+b
"""
)


def test_patch_paths_and_guard():
    touched = safety.patch_paths(PATCH)
    assert touched == [
        "src/tum_mcp/bundled/skills/prepare-study/SKILL.md",
        "src/tum_mcp/moodle/service.py",
    ]
    assert safety.guarded(touched) == ["src/tum_mcp/moodle/service.py"]
    for path in (
        "skill-lab/skill_lab/runs.py",
        "src/tum_mcp/client_rendering.py",
        "src/tum_mcp/clients/rendering.py",
        "src/tum_mcp/clients/hosts.py",
        "src/tum_mcp/commands/lifecycle.py",
        "src/tum_mcp/commands/actions.py",
        "src/tum_mcp/commands/workflow.py",
        "src/tum_mcp/actions/remote_gate.py",
        "AGENTS.md",
    ):
        assert safety.guarded([path]) == [path]
    assert safety.guarded(["src/tum_mcp/study_report.py"]) == []


def test_shim_refuses_account_and_publishing_commands():
    for arguments in (["login"], ["logout"], ["setup"], ["study", "publish"], ["serve"]):
        assert shim.refusal(arguments)
    for arguments in (["study", "report", "."], ["discover"], []):
        assert shim.refusal(arguments) is None


def test_credential_scan(tmp_path):
    assert safety.credential_hits("Authorization: Bearer " + "a" * 30)
    assert safety.credential_hits('{"password": "hunter22"}')
    assert safety.credential_hits("MoodleSession=abcdef1234567890")
    assert not safety.credential_hits("The lecture covers Bayesian networks.")
    assert safety.credential_hits("key sk-" + "Ab3" * 10)
    # A trial's review quoted 'the task-to-position-to-department structure'.
    assert not safety.credential_hits("the task-to-position-to-department structure")
    (tmp_path / "notes.txt").write_text("cookie _shibsession_x=0123456789abcdef")
    (tmp_path / "slides.pdf").write_bytes(b"Bearer " + b"b" * 40)
    hits = safety.scan_tree(tmp_path)
    assert len(hits) == 1 and hits[0].startswith("notes.txt")


def test_claude_redaction_hides_personal_tool_results_only():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "1", "name": "mcp__tum__tumonline_list_studies"},
                    {"type": "tool_use", "id": "2", "name": "mcp__tum__moodle_list_materials"},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "Private programme"},
                ]
            },
            "tool_use_result": {"studies": ["Private programme"]},
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "2", "content": "Lecture 1"}]
            },
        },
    ]
    redacted = safety.redact_claude(events)
    first = redacted[1]["message"]["content"][0]["content"]
    assert first["redacted"] is True and "Private" not in str(redacted[1])
    assert redacted[2]["message"]["content"][0]["content"] == "Lecture 1"


def test_redaction_also_scrubs_the_agents_echo_of_personal_results():
    studies = '{"studies": [{"name": "Informatics", "degree": "Master of Science"}]}'
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "1", "name": "mcp__tum__tumonline_list_studies"}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "1",
                        "content": [{"type": "text", "text": studies}],
                    }
                ]
            },
        },
        {"type": "result", "result": "You study Informatics (Master of Science); status unknown."},
    ]
    redacted = safety.redact_claude(events)
    final = redacted[2]["result"]
    assert "Informatics" not in final and "Master of Science" not in final
    assert final.endswith("status unknown.")
    codex = [
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "tool": "tumonline_list_courses",
                "result": {"courses": ["Course 4711 Alpha"]},
            },
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Found Course 4711 Alpha."},
        },
    ]
    assert "Alpha" not in safety.redact_codex(codex)[1]["item"]["text"]


def test_codex_redaction():
    events = [
        {
            "type": "item.completed",
            "item": {"type": "mcp_tool_call", "tool": "zulip_read_topic", "result": "hi Anna"},
        },
        {
            "type": "item.completed",
            "item": {"type": "mcp_tool_call", "tool": "moodle_list_courses", "result": "AI"},
        },
    ]
    redacted = safety.redact_codex(events)
    assert redacted[0]["item"]["result"]["redacted"] is True
    assert redacted[1]["item"]["result"] == "AI"


def test_a_browser_check_runs_on_the_host_and_its_output_returns(tmp_path, monkeypatch, capsys):
    # The trial's sandbox blocks the browser; the shim hands `study visuals` to the lab, which
    # runs it outside the sandbox and returns its output and exit code.
    import sys
    from pathlib import Path

    from skill_lab import runs, shim

    folder = tmp_path / "broker"
    host = tmp_path / "host.py"
    host.write_text("import sys; print('checked', sys.argv[-1]); raise SystemExit(3)\n")
    monkeypatch.setattr(
        runs, "_broker_command", lambda python, arguments: [sys.executable, str(host), *arguments]
    )
    stop = runs.render_broker(folder, Path(sys.executable))
    monkeypatch.chdir(tmp_path)
    try:
        code = shim.brokered(["study", "visuals", "course"], str(folder))
    finally:
        stop.set()
    assert code == 3
    assert "checked course" in capsys.readouterr().out


def test_the_render_broker_refuses_other_commands_and_outside_projects(tmp_path):
    from skill_lab import LabError, runs

    for arguments in (
        ["login"],
        ["study", "publish", "."],
        ["study", "visuals", "../outside"],
        ["study", "visuals", ".", "--output", "../outside"],
        ["review", "run-checker", ".", "--packet", "r1-p1"],
    ):
        with pytest.raises(LabError):
            runs._render_request({"arguments": arguments, "cwd": str(tmp_path)}, tmp_path)


def test_the_broker_runs_the_interaction_check_and_a_lab_chosen_checker(tmp_path):
    # The pilot's trials could not run `--interact`, and a sandboxed Codex trial cannot open
    # a fresh checker session itself.
    from skill_lab import LabError, runs
    from skill_lab.hosts import checker_command
    from skill_lab.models import ModelSpec

    def request(*arguments):
        job = {"arguments": list(arguments), "cwd": str(tmp_path)}
        return runs._render_request(job, tmp_path, checker)[0]

    checker = checker_command(ModelSpec.parse("codex:gpt-6.1-terra:high"))
    assert request("study", "visuals", ".", "--exam", "--interact", "--json")[-1] == "--json"
    learner = [
        "study",
        "visuals",
        ".",
        "--unit",
        "bfs",
        "--exercise",
        "practice/trace",
        "--learner",
        "--phone",
        "--json",
    ]
    assert request(*learner) == learner
    ran = request("review", "run-checker", ".", "--packet", "r1-p2")
    assert ran[:5] == ["review", "run-checker", ".", "--packet", "r1-p2"]
    template = ran[ran.index("--command") + 1]
    assert "read-only" in template and "gpt-6.1-terra" in template and "{prompt}" in template
    assert request("review", "run-checker", ".", "--plans")[3] == "--plans"
    assert request("review", "run-checker", ".", "--plans", "--batch", "week_1.v2")[3:6] == [
        "--plans",
        "--batch",
        "week_1.v2",
    ]
    # The trial cannot pick the host command or reach outside its packets.
    for arguments in (
        ("review", "run-checker", ".", "--packet", "x", "--command", "sh -c id"),
        ("review", "run-checker", ".", "--host", "claude", "--plans"),
        ("review", "run-checker", ".", "--packet", "../../etc"),
        ("review", "run-checker", ".", "--plans", "--batch", "Week-1"),
        ("review", "run-checker", ".", "--packet", "r1-p2", "--batch", "week-1"),
    ):
        with pytest.raises(LabError):
            request(*arguments)


def test_codex_trial_can_import_its_own_moodle_downloads(tmp_path) -> None:
    # Trials stopped for want of lecture PDFs: downloads land outside the Codex workspace.
    from skill_lab.hosts import codex_command
    from skill_lab.models import ModelSpec

    spec = ModelSpec.parse("codex:gpt-6.1-terra:xhigh")
    trial = codex_command(spec, "hi", tmp_path, session=None, downloads="/run/downloads")
    judge = codex_command(spec, "hi", tmp_path, session=None, judge=True, downloads="/x")
    assert trial[trial.index("--add-dir") + 1] == "/run/downloads"
    assert "--add-dir" not in judge


def test_help_runs_in_the_trial_and_checks_go_to_the_broker():
    from skill_lab import shim

    assert shim.brokers(["review", "run-checker", ".", "--plans"])
    assert shim.brokers(["study", "visuals", ".", "--interact"])
    assert shim.brokers(["lecture", "prepare", ".", "--recording", "https://live.rbg.tum.de/w/1/2"])
    assert not shim.brokers(["study", "visuals", ".", "--help"])
    assert not shim.brokers(["lecture", "prepare", ".", "--help"])
    assert not shim.brokers(["study", "lint", "."])


@pytest.mark.parametrize(
    "args",
    [
        ["moodle", "courses"],
        ["doctor", "--live"],
        ["serve"],
        ["lecture", "prepare", ".", "--recording", "https://live.rbg.tum.de/w/1/2"],
    ],
)
def test_offline_shim_and_broker_refuse_campus_paths(tmp_path, args):
    from skill_lab import LabError, runs, shim

    assert shim.refusal(args, offline=True)
    with pytest.raises(LabError, match="offline broker"):
        runs._render_request({"arguments": args, "cwd": str(tmp_path)}, tmp_path, offline=True)


@pytest.mark.parametrize("limit", [1, 3])
def test_offline_checker_limits_actual_launches_and_never_repairs(tmp_path, limit):
    import sys

    from skill_lab import shim

    ledger, counter = tmp_path / "ledger", tmp_path / "launches"
    command = [sys.executable, "-c", f"open({str(counter)!r}, 'a').write('called\\n')"]
    budget = (str(ledger), limit)
    for attempt in range(limit):
        log = str(tmp_path / f"request-{attempt}")
        assert shim.checker(log, "plan_check", command, budget=budget) == 0
        assert shim.checker(log, "plan_check", command, budget=budget) == 2
    assert shim.checker(str(tmp_path / "extra"), "plan_check", command, budget=budget) == 2
    assert counter.read_text().splitlines() == ["called"] * limit


def test_offline_broker_deadline_stops_hanging_child_process(tmp_path, monkeypatch):
    import socket
    import subprocess
    import sys
    import tempfile
    import time
    from pathlib import Path

    from skill_lab import runs, shim

    # EOF on this socket requires the separate worker process to close its inherited fd.
    program = (
        "import socket, subprocess, sys; "
        "s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); "
        "s.sendall(b'ready'); "
        "p=subprocess.Popen([sys.executable,'-c','import signal; signal.pause()'],"
        "pass_fds=[s.fileno()]); p.wait()"
    )
    folder = tmp_path / "broker"
    state = runs.OfflineBrokerTurn(1, tmp_path / "ledger")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        runs, "_broker_command", lambda *_: [sys.executable, "-c", program, sockpath]
    )
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as short_dir,
        socket.socket(socket.AF_UNIX) as receiver,
    ):
        sockpath = f"{short_dir}/broker.sock"
        receiver.bind(sockpath)
        receiver.listen()
        receiver.settimeout(6)
        state.deadline = time.monotonic() + 4
        stop = runs.render_broker(folder, Path(sys.executable), ["checker"], turn=state)
        shim_path = Path(shim.__file__)
        with subprocess.Popen(
            [sys.executable, str(shim_path), "review", "run-checker", ".", "--plans"],
            env={**__import__("os").environ, "SKILL_LAB_RENDER_BROKER": str(folder)},
            stderr=subprocess.PIPE,
        ) as caller:
            try:
                connection, _ = receiver.accept()
                with connection:
                    connection.settimeout(6)
                    assert connection.recv(5) == b"ready"
                    assert connection.recv(1) == b""
                assert b"exhausted the author turn deadline" in caller.communicate(timeout=6)[1]
                assert caller.returncode == 2
            finally:
                state.finish()
                stop.set()
                caller.kill()


def test_recording_preparation_is_confined_to_the_course_and_canonical_streams(tmp_path):
    from skill_lab import LabError, runs

    arguments = [
        "lecture",
        "prepare",
        ".",
        "--recording",
        "https://live.rbg.tum.de/w/1/2",
        "--language",
        "en",
        "--frame-at",
        "120.5",
        "--previews",
    ]
    job = {"arguments": arguments, "cwd": str(tmp_path)}
    assert runs._render_request(job, tmp_path) == (arguments, tmp_path)
    for tail in (
        ["--recording", "https://other.example/w/1/2"],
        ["--recording", "https://live.rbg.tum.de/w/1/2?token=secret"],
        ["--recording", "https://live.rbg.tum.de/w/1/2", "--transcript", "../private.vtt"],
        ["--recording", "https://live.rbg.tum.de/w/1/2", "--frame-at", "nan"],
        ["--recording", "https://live.rbg.tum.de/w/1/2", "--language", "../outside"],
        [],
    ):
        with pytest.raises(LabError):
            runs._render_request(
                {"arguments": ["lecture", "prepare", ".", *tail], "cwd": str(tmp_path)},
                tmp_path,
            )
    with pytest.raises(LabError):
        runs._render_request(
            {
                "arguments": ["lecture", "prepare", "../outside", *arguments[3:]],
                "cwd": str(tmp_path),
            },
            tmp_path,
        )


def test_broker_listens_to_one_published_stem_inside_the_workspace(tmp_path):
    from skill_lab import LabError, runs

    listen = ["video-notes", "listen", ".", "02_rational-vacuum-agents"]
    job = {"arguments": listen, "cwd": str(tmp_path)}
    assert runs._render_request(job, tmp_path) == (listen, tmp_path)
    for arguments in (
        ["audio-notes", "listen", ".", "../tracks"],
        ["audio-notes", "listen", ".", "01_logic", "--extra"],
        ["audio-notes", "listen", "../outside", "01_logic"],
        ["audio-notes", "publish", ".", "01_logic"],
    ):
        with pytest.raises(LabError):
            runs._render_request({"arguments": arguments, "cwd": str(tmp_path)}, tmp_path)


def test_a_render_is_answered_while_a_long_checker_still_runs(tmp_path, monkeypatch):
    # The candidate trial's renders stalled for ten minutes behind one checker.
    import subprocess
    import threading
    from pathlib import Path

    from skill_lab import runs, shim

    started, release = threading.Event(), threading.Event()

    def run(command, **kwargs):
        if "review" in command:
            started.set()
            assert release.wait(timeout=10)
        return subprocess.CompletedProcess(command, 0, stdout="checked", stderr="")

    monkeypatch.setattr(runs.subprocess, "run", run)
    folder = tmp_path / "broker"
    stop = runs.render_broker(folder, Path("python"), ["checker", "{prompt}"])
    monkeypatch.chdir(tmp_path)
    slow = threading.Thread(
        target=shim.brokered, args=(["review", "run-checker", ".", "--plans"], str(folder))
    )
    try:
        slow.start()
        assert started.wait(timeout=10)
        assert shim.brokered(["study", "visuals", "."], str(folder)) == 0
        assert slow.is_alive()
    finally:
        release.set()
        slow.join(timeout=10)
        stop.set()
    assert not slow.is_alive()
