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
    for path in ("skill-lab/skill_lab/runs.py", "src/tum_mcp/client_rendering.py", "AGENTS.md"):
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
    ran = request("review", "run-checker", ".", "--packet", "r1-p2")
    assert ran[:5] == ["review", "run-checker", ".", "--packet", "r1-p2"]
    template = ran[ran.index("--command") + 1]
    assert "read-only" in template and "gpt-6.1-terra" in template and "{prompt}" in template
    assert request("review", "run-checker", ".", "--plans")[3] == "--plans"
    # The trial cannot pick the host command or reach outside its packets.
    for arguments in (
        ("review", "run-checker", ".", "--packet", "x", "--command", "sh -c id"),
        ("review", "run-checker", ".", "--host", "claude", "--plans"),
        ("review", "run-checker", ".", "--packet", "../../etc"),
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
