"""Ask agent through the real preview server with a scripted Claude Code CLI."""

import json
import os
import sys
from collections.abc import Iterator
from functools import partial
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

FAKE = Path(__file__).parents[1] / "fixtures/ask_agent"
ANCHOR = {
    "view": "content",
    "unit_key": "graphs",
    "unit_revision": "0" * 64,
    "block_index": 0,
    "block_title": "A small language for connections",
    "quote": "connections",
}


@pytest.fixture
def preview(project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    from tum_mcp.course.app.preview import Handler, PreviewServer

    (FAKE / "claude").chmod(0o755)
    (FAKE / "cursor-agent").chmod(0o755)
    # Windows finds commands by extension, so each scripted CLI gets a .cmd shim there. The PATH
    # keeps out any real agent CLIs installed on the machine.
    commands = FAKE
    system = ["/usr/bin", "/bin"]
    if os.name == "nt":
        commands = tmp_path / "bin"
        commands.mkdir()
        for name in ("claude", "cursor-agent"):
            (commands / f"{name}.cmd").write_text(f'@"{sys.executable}" "{FAKE / name}" %*\r\n')
        system = [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")]
    path = [str(commands), str(Path(sys.executable).parent), *system]
    monkeypatch.setenv("PATH", os.pathsep.join(path))
    monkeypatch.setenv("FAKE_ASK_STATE", str(tmp_path))
    monkeypatch.setenv("FAKE_ASK_LOG", str(tmp_path / "prompt.txt"))
    with PreviewServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(project / "app"))
    ) as server:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()


def request(
    base: str, path: str, body: dict | None = None, headers: dict | None = None
) -> tuple[int, bytes]:
    connection = HTTPConnection(base.removeprefix("http://"), timeout=120)
    try:
        connection.request(
            "GET" if body is None else "POST",
            "/_study/agent/" + path,
            None if body is None else json.dumps(body),
            {"Origin": base, "Content-Type": "application/json", **(headers or {})},
        )
        reply = connection.getresponse()
        return reply.status, reply.read()
    finally:
        connection.close()


def call(base: str, path: str, body: dict | None = None, *, token: str | None = None) -> dict:
    status, data = request(base, path, body, {"X-Ask-Token": token} if token else None)
    assert status == 200, data
    return json.loads(data)


def send(base: str, token: str, body: dict) -> list[dict]:
    status, data = request(base, "send", body, {"X-Ask-Token": token})
    assert status == 200, data
    return [json.loads(line) for line in data.splitlines()]


def unit_text(project: Path) -> str:
    return (project / "app/study/units/graphs.json").read_text(encoding="utf-8")


def test_requests_need_the_preview_origin_and_the_start_token(preview: str) -> None:
    status = call(preview, "status")
    assert status["provider"] == "claude"
    assert status["providers"]["claude"] == {
        "installed": True,
        "connected": True,
        "method": "Max plan",
    }
    assert request(preview, "chats")[0] == 403
    foreign = {"Origin": "http://evil.example", "X-Ask-Token": status["token"]}
    assert request(preview, "send", {"text": "hi"}, foreign)[0] == 403


def test_a_question_streams_an_answer_with_the_passage_context_and_keeps_the_chat(
    preview: str, project: Path, tmp_path: Path
) -> None:
    token = call(preview, "status")["token"]
    before = unit_text(project)
    events = send(preview, token, {"text": "Why?", "anchor": ANCHOR, "place": "Graphs"})

    assert events[0]["type"] == "chat"
    # Text streams into the log until the turn ends; the answer is not kept there twice.
    assert {"type": "thinking", "text": ""} in events
    assert any(event["type"] == "note" for event in events)
    assert events[-1] == {"type": "done", "edited": False}
    assert [step["kind"] for step in events[-2]["message"]["log"]] == ["thinking"]
    assert "\\(g(n)\\)" in events[-2]["message"]["text"]
    prompt = (tmp_path / "prompt.txt").read_text(encoding="utf-8")
    assert "file: app/study/units/graphs.json · blocks[0]" in prompt
    assert '"title": "A small language for connections"' in prompt
    assert unit_text(project) == before

    chats = call(preview, "chats", token=token)["chats"]
    assert [chat["title"] for chat in chats] == ["Why?"]
    chat = call(preview, f"chats/{chats[0]['id']}", token=token)
    assert [message["role"] for message in chat["messages"]] == ["student", "agent"]
    assert "session" not in chat


def test_an_edit_is_built_recorded_undone_and_redone_while_unchanged(
    preview: str, project: Path
) -> None:
    token = call(preview, "status")["token"]
    events = send(preview, token, {"text": "IMPROVE it", "anchor": ANCHOR})
    assert events[-1] == {"type": "done", "edited": True}
    change = events[-2]["message"]["change"]
    assert change["sections"] == ["A small language for connections"]
    log = [(step["kind"], step["text"]) for step in events[-2]["message"]["log"]]
    assert log[:3] == [
        ("thinking", ""),
        ("note", "Adding the rule to this section."),
        ("step", "Editing graphs.json"),
    ]
    assert ("step", "Checking the edit") in log
    assert "Uniform-cost needs a priority queue." in unit_text(project)
    assert "Uniform-cost needs a priority queue." in (project / "app/data.mjs").read_text()

    chat = events[0]["id"]
    assert call(preview, f"chats/{chat}", token=token)["messages"][-1]["change"]["undoable"]
    call(preview, f"chats/{chat}/undo/{change['id']}", {}, token=token)
    assert "Uniform-cost needs a priority queue." not in unit_text(project)
    assert "Uniform-cost needs a priority queue." not in (project / "app/data.mjs").read_text()
    undone = call(preview, f"chats/{chat}", token=token)["messages"][-1]["change"]
    assert undone["undone"] and undone["redoable"]

    call(preview, f"chats/{chat}/redo/{change['id']}", {}, token=token)
    assert "Uniform-cost needs a priority queue." in unit_text(project)
    assert "Uniform-cost needs a priority queue." in (project / "app/data.mjs").read_text()
    redone = call(preview, f"chats/{chat}", token=token)["messages"][-1]["change"]
    assert not redone["undone"] and redone["undoable"]
    call(preview, f"chats/{chat}/undo/{change['id']}", {}, token=token)
    assert "Uniform-cost needs a priority queue." not in unit_text(project)


def test_undo_closes_once_the_page_changed_after_the_edit(preview: str, project: Path) -> None:
    token = call(preview, "status")["token"]
    events = send(preview, token, {"text": "IMPROVE it", "anchor": ANCHOR})
    change, chat = events[-2]["message"]["change"], events[0]["id"]
    path = project / "app/study/units/graphs.json"
    path.write_text(unit_text(project).replace("priority queue", "heap"), encoding="utf-8")

    assert (
        call(preview, f"chats/{chat}", token=token)["messages"][-1]["change"]["undoable"] is False
    )
    undo = f"chats/{chat}/undo/{change['id']}"
    assert request(preview, undo, {}, {"X-Ask-Token": token})[0] == 409
    assert "heap" in unit_text(project)


def test_an_edit_that_does_not_build_is_rolled_back(preview: str, project: Path) -> None:
    token = call(preview, "status")["token"]
    before = unit_text(project)
    events = send(preview, token, {"text": "BREAK it", "anchor": ANCHOR})

    assert events[-1] == {"type": "done", "edited": False}
    assert events[-2]["message"]["text"].startswith("The edit did not build, so it was undone")
    assert any(event == {"type": "status", "text": "Fixing the edit"} for event in events)
    assert unit_text(project) == before


def test_protected_course_files_are_put_back(preview: str, project: Path) -> None:
    token = call(preview, "status")["token"]
    guide = (project / "AGENTS.md").read_bytes()
    events = send(preview, token, {"text": "PROTECTED", "anchor": ANCHOR})

    assert (project / "AGENTS.md").read_bytes() == guide
    assert {
        "type": "status",
        "text": "Kept protected course files unchanged",
        "after": True,
    } in events


def test_a_follow_up_resumes_the_same_agent_session(preview: str, tmp_path: Path) -> None:
    token = call(preview, "status")["token"]
    first = send(preview, token, {"text": "Why?", "anchor": ANCHOR})
    second = send(preview, token, {"chat": first[0]["id"], "text": "And then?"})

    assert second[0]["id"] == first[0]["id"]
    assert "<course-app-context>" not in (tmp_path / "prompt.txt").read_text(encoding="utf-8")
    sessions = json.loads((tmp_path / "fake-claude-sessions.json").read_text(encoding="utf-8"))
    assert len(sessions) == 1


def test_the_chosen_model_and_effort_reach_the_agent(preview: str, tmp_path: Path) -> None:
    token = call(preview, "status")["token"]
    chosen = {"provider": "claude", "model": "opus", "effort": "high"}
    options = call(preview, "settings", chosen, token=token)["options"]

    assert (options["model"], options["effort"]) == ("opus", "high")
    assert call(preview, "status")["options"]["model"] == "opus"
    unknown = {**chosen, "model": "gpt-9"}
    assert request(preview, "settings", unknown, {"X-Ask-Token": token})[0] == 400
    send(preview, token, {"text": "Why?", "anchor": ANCHOR})
    args = json.loads((tmp_path / "prompt.args.json").read_text(encoding="utf-8"))
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--effort") + 1] == "high"


def test_a_follow_up_sends_only_context_it_has_not_sent(preview: str, tmp_path: Path) -> None:
    token = call(preview, "status")["token"]
    prompt = tmp_path / "prompt.txt"
    section = {"anchor": ANCHOR, "scope": "section", "section": "A small language"}
    chat = send(preview, token, {"text": "Why?", **section})[0]["id"]
    assert "context: the section in view" in prompt.read_text(encoding="utf-8")

    send(preview, token, {"chat": chat, "text": "More?", **section})
    assert "<course-app-context>" not in prompt.read_text(encoding="utf-8")

    quote = "connections, and the next section's first line"
    send(preview, token, {"chat": chat, "text": "And this?", "anchor": ANCHOR, "quote": quote})
    brief = prompt.read_text(encoding="utf-8")
    assert f'selected text: "{quote}"' in brief
    assert "course:" not in brief
    asked = [
        m for m in call(preview, f"chats/{chat}", token=token)["messages"] if m["role"] == "student"
    ]
    assert [(m["quote"], m["section"]) for m in asked] == [
        ("", "A small language"),
        ("", "A small language"),
        (quote, ""),
    ]


def test_a_chat_keeps_one_live_agent_process_until_the_model_changes(
    preview: str, tmp_path: Path
) -> None:
    token = call(preview, "status")["token"]
    chat = send(preview, token, {"text": "Why?", "anchor": ANCHOR})[0]["id"]
    send(preview, token, {"chat": chat, "text": "And then?"})
    starts = tmp_path / "prompt.starts"
    assert len(starts.read_text(encoding="utf-8").splitlines()) == 1

    call(
        preview, "settings", {"provider": "claude", "model": "sonnet", "effort": "low"}, token=token
    )
    send(preview, token, {"chat": chat, "text": "Once more?"})
    sessions = starts.read_text(encoding="utf-8").splitlines()
    assert len(sessions) == 2
    assert sessions[0] == sessions[1]


def test_the_course_checks_undo_an_edit_that_adds_problems(preview: str, project: Path) -> None:
    token = call(preview, "status")["token"]
    before = unit_text(project)
    events = send(preview, token, {"text": "SLOPPY", "anchor": ANCHOR})

    assert {"type": "status", "text": "Checking the edit", "after": True} in events
    assert {"type": "status", "text": "Fixing the edit"} in events
    assert events[-2]["message"]["text"].startswith("The edit did not pass the course checks")
    assert unit_text(project) == before


def test_accounts_are_profiles_the_student_switches_and_signs_out(preview: str) -> None:
    token = call(preview, "status")["token"]
    key = {"provider": "claude", "key": "sk-ant-api03-" + "y" * 40}
    call(preview, "connect", key, token=token)
    status = call(preview, "status")
    assert [item["id"] for item in status["profiles"]] == ["claude-subscription", "claude-key"]
    assert status["profile"] == "claude-key"

    call(preview, "connect", {"provider": "claude"}, token=token)
    assert call(preview, "status")["profile"] == "claude-key"
    call(preview, "profile", {"profile": "claude-subscription"}, token=token)
    assert call(preview, "status")["profile"] == "claude-subscription"
    call(preview, "disconnect", {"profile": "claude-subscription"}, token=token)
    assert [item["id"] for item in call(preview, "status")["profiles"]] == ["claude-key"]
    call(preview, "disconnect", {"profile": "claude-key"}, token=token)
    status = call(preview, "status")
    assert (status["profiles"], status["profile"]) == ([], None)


def test_a_chat_continues_with_its_whole_history_under_another_provider(
    preview: str, project: Path, tmp_path: Path
) -> None:
    from uuid import UUID

    from tum_mcp.course.app import ask_threads

    token = call(preview, "status")["token"]
    chat = send(preview, token, {"text": "Why BFS?", "anchor": ANCHOR})[0]["id"]
    send(preview, token, {"chat": chat, "text": "And DFS?"})
    found = ask_threads.read(project, UUID(chat))
    ask_threads.save(project, found.model_copy(update={"provider": "codex", "session": ""}))

    send(preview, token, {"chat": chat, "text": "Compare them."})
    prompt = (tmp_path / "prompt.txt").read_text(encoding="utf-8")
    assert prompt.index('student (about "connections"): Why BFS?') < prompt.index(
        "student: And DFS?"
    )
    assert "agent: Breadth-first orders the frontier" in prompt
    assert prompt.rstrip().endswith("Compare them.")


def test_cursor_runs_auto_resumes_its_session_and_edits_through_the_gate(
    preview: str, project: Path, tmp_path: Path
) -> None:
    from tum_mcp.course.app import ask_runtime

    token = call(preview, "status")["token"]
    assert call(preview, "status")["providers"]["cursor"] == {"installed": True, "connected": False}
    (tmp_path / "fake-cursor-signed-in").write_text("", encoding="utf-8")
    call(preview, "status?fresh=1")  # as the sign-in wait asks once the browser sign-in ends
    call(preview, "profile", {"profile": "cursor-subscription"}, token=token)
    status = call(preview, "status")
    assert status["profile"] == "cursor-subscription"
    menu = [(item["id"], item["default"], item["efforts"]) for item in status["options"]["models"]]
    assert menu == [("auto", True, []), ("claude-opus-4-8", False, [])]

    first = send(preview, token, {"text": "Why?", "anchor": ANCHOR})
    answer = first[-2]["message"]["text"]
    assert answer.startswith("Auto here")
    assert "".join(event["text"] for event in first if event["type"] == "note") == answer
    assert first[-2]["message"]["log"] == []
    args = json.loads((tmp_path / "prompt.cursor-args.json").read_text(encoding="utf-8"))
    assert (args[args.index("--model") + 1], args[args.index("--sandbox") + 1]) == (
        "auto",
        "enabled",
    )
    # The prompt goes in on stdin, never as an argument.
    prompt = (tmp_path / "prompt.txt").read_text(encoding="utf-8")
    assert "--resume" not in args and "<ask-agent-instructions>" in prompt
    assert all("ask-agent-instructions" not in arg for arg in args)
    assert Path(args[args.index("--workspace") + 1]) == project / "app"

    chat = first[0]["id"]
    send(preview, token, {"chat": chat, "text": "And then?"})
    args = json.loads((tmp_path / "prompt.cursor-args.json").read_text(encoding="utf-8"))
    assert args[args.index("--resume") + 1] == "cursor-session-1"
    assert "<ask-agent-instructions>" not in (tmp_path / "prompt.txt").read_text(encoding="utf-8")

    edit = send(preview, token, {"chat": chat, "text": "IMPROVE it", "anchor": ANCHOR})
    assert edit[-1] == {"type": "done", "edited": True}
    assert "Cursor adds a sentence." in unit_text(project)
    config = ask_runtime.agent_dir() / "cursor" / ".cursor" / "cli-config.json"
    rules = json.loads(config.read_text(encoding="utf-8"))["permissions"]
    assert "Write(app/**)" in rules["allow"] and "Write(AGENTS.md)" in rules["deny"]


def test_an_anthropic_key_stays_out_of_arguments_and_rejects_login_tokens(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.app import ask_runtime
    from tum_mcp.errors import CampusError

    with pytest.raises(CampusError):
        ask_runtime.save_key("sk-ant-oat01-subscription-token")
    key = "sk-ant-api03-" + "x" * 40
    ask_runtime.save_key(key)
    assert ask_runtime.load_key() == key
    assert key.encode() not in (ask_runtime.agent_dir() / "anthropic-key.enc").read_bytes()

    started = {}

    class Process:
        def __init__(self, command: list[str], **options: object) -> None:
            started.update(command=command, env=options["env"])

    monkeypatch.setattr(ask_runtime.subprocess, "Popen", Process)
    ask_runtime.ClaudeSession(project, None, key=True)
    assert all(key not in part for part in started["command"])
    assert key not in json.dumps(started["env"])
    # Settings and instructions travel in files, out of reach of Windows argument quoting.
    settings_file = Path(started["command"][started["command"].index("--settings") + 1])
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert Path(
        started["command"][started["command"].index("--append-system-prompt-file") + 1]
    ).is_file()
    assert settings["apiKeyHelper"].endswith("-m tum_mcp.course.app.ask_runtime")
    assert settings["promptCacheTtl"] == "1h"
    assert started["env"]["CLAUDE_CONFIG_DIR"] == str(ask_runtime.agent_dir() / "claude")
