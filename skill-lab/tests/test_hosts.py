import json
from pathlib import Path

from skill_lab import hosts
from skill_lab.models import ModelSpec


def test_claude_command_pins_model_tools_and_resume():
    command = hosts.claude_command(ModelSpec.parse("claude:opus:xhigh"), "Hello", session="abc")
    assert command[:3] == ["claude", "-p", "Hello"]
    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--effort") + 1] == "xhigh"
    disallowed = command[command.index("--disallowedTools") + 1]
    assert "WebFetch" in disallowed and "Bash(git push:*)" in disallowed
    assert command[-2:] == ["--resume", "abc"]
    judge = hosts.claude_command(
        ModelSpec.parse("claude:opus:xhigh"), "x", session=None, judge=True
    )
    assert "--strict-mcp-config" in judge and "--resume" not in judge


def test_codex_command_sandboxes_shell_and_resumes(tmp_path):
    spec = ModelSpec.parse("codex:gpt-6.1-sol:xhigh")
    first = hosts.codex_command(spec, "Hello", tmp_path, session=None)
    assert first[:2] == ["codex", "exec"] and first[-1] == "Hello"
    assert "workspace-write" in first
    assert "sandbox_workspace_write.network_access=false" in first
    assert 'model_reasoning_effort="xhigh"' in first
    later = hosts.codex_command(spec, "Next", tmp_path, session="t-1")
    assert later[-3:] == ["resume", "t-1", "Next"]
    judge = hosts.codex_command(spec, "x", tmp_path, session=None, judge=True)
    assert "read-only" in judge and "mcp_servers={}" in judge


def test_parse_claude_stream():
    events = [
        {"type": "system", "subtype": "init", "session_id": "s1", "model": "claude-opus-5-5"},
        {"type": "assistant", "message": {"model": "claude-opus-5-5", "content": []}},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Done",
            "session_id": "s1",
            "usage": {"input_tokens": 3},
            "total_cost_usd": 0.1,
        },
    ]
    result = hosts.parse_claude(events)
    assert (result.session_id, result.text, result.model_reported) == (
        "s1",
        "Done",
        "claude-opus-5-5",
    )
    assert not result.is_error
    assert hosts.parse_claude(events[:2]).is_error


def test_parse_codex_events_reads_the_model_from_the_session_log(tmp_path):
    log = tmp_path / ".codex" / "sessions" / "2026" / "rollout-x-t-9.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}}) + "\n")
    events = [
        {"type": "thread.started", "thread_id": "t-9"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "First"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Final?"}},
        {"type": "turn.completed", "usage": {"input_tokens": 5}},
    ]
    result = hosts.parse_codex(events, tmp_path)
    assert (result.session_id, result.text, result.model_reported) == (
        "t-9",
        "Final?",
        "gpt-6.1-sol",
    )
    assert hosts.parse_codex(events[:3], tmp_path).is_error


def test_clean_environment_isolates_home_and_drops_host_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_HOME", "/elsewhere")
    monkeypatch.setenv("VIRTUAL_ENV", "/venv")
    environment = hosts.clean_environment({"EXTRA": "1"}, tmp_path, Path("/lab/bin"), "codex")
    assert environment["HOME"] == str(tmp_path)
    claude = hosts.clean_environment({}, tmp_path, None, "claude")
    assert claude["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert claude["HOME"] != str(tmp_path)
    assert environment["PATH"].startswith("/lab/bin")
    assert environment["EXTRA"] == "1"
    assert not {"CLAUDECODE", "CODEX_HOME", "VIRTUAL_ENV"} & set(environment)
