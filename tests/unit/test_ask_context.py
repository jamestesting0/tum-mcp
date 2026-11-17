"""The Ask agent's thread packet and chat store, on synthetic course files."""

import json
from pathlib import Path

from tum_mcp.course.app import ask_threads
from tum_mcp.course.app.ask_context import ANCHOR, LIMIT, View, packet


def course(tmp_path: Path, paragraph: str = "Edges connect nodes.") -> Path:
    root = tmp_path / "course"
    (root / ".tum-mcp").mkdir(parents=True)
    (root / ".tum-mcp/state.json").write_text("{}", encoding="utf-8")
    units = root / "app/study/units"
    units.mkdir(parents=True)
    unit = {
        "key": "graphs",
        "title": "Graphs",
        "blocks": [
            {"kind": "text", "key": "intro", "title": "Intro", "paragraphs": [paragraph]},
            {"kind": "text", "key": "degree", "title": "Degree", "paragraphs": ["d(v)"]},
        ],
    }
    (units / "graphs.json").write_text(json.dumps(unit), encoding="utf-8")
    return root


def anchor(index: int = 1) -> object:
    return ANCHOR.validate_python(
        {
            "view": "content",
            "unit_key": "graphs",
            "unit_revision": "0" * 64,
            "block_index": index,
            "block_title": "Degree",
            "quote": "d(v)",
        }
    )


class Course:
    title, semester = "Algorithms", "WS26/27"


def test_the_packet_names_the_file_section_and_student_state(tmp_path, monkeypatch) -> None:
    root = course(tmp_path)
    monkeypatch.setattr(
        "tum_mcp.course.app.ask_context.load_state", lambda _: type("S", (), {"course": Course})
    )
    monkeypatch.setattr("tum_mcp.course.app.ask_context._related", lambda *_: [])
    text = packet(root, anchor(), View(route="graphs/content", chosen="B"), ["Unclear"])

    assert "file: app/study/units/graphs.json · blocks[1] (key degree)" in text
    assert "sections: Intro | > Degree" in text
    assert '"paragraphs": [\n  "d(v)"' in text
    assert "chosen option: B" in text and "open comments here: Unclear" in text


def test_the_packet_stays_within_its_limit(tmp_path, monkeypatch) -> None:
    root = course(tmp_path, paragraph="x" * 20000)
    monkeypatch.setattr(
        "tum_mcp.course.app.ask_context.load_state", lambda _: type("S", (), {"course": Course})
    )
    monkeypatch.setattr("tum_mcp.course.app.ask_context._related", lambda *_: [])
    text = packet(root, anchor(0), View(), [])

    assert len(text) <= LIMIT + 50
    assert "truncated; read the file" in text


def test_a_codex_turn_sends_the_choice_and_reports_its_events(tmp_path) -> None:
    from tum_mcp.course.app.ask_runtime import CodexTurn

    calls = []

    class Codex:
        queues = {}

        def call(self, method, params):
            calls.append((method, params))
            return {"turn": {"id": "turn-1"}}

        def start(self, root, session):
            return "thread-1"

    codex = Codex()
    turn = CodexTurn(codex, tmp_path, None, "Why?", "gpt-6.1-terra", "high")
    method, params = calls[0]
    assert method == "turn/start"
    assert (params["model"], params["effort"]) == ("gpt-6.1-terra", "high")
    assert params["sandboxPolicy"]["writableRoots"] == [
        str(tmp_path / "app"),
        str(tmp_path / ".tum-mcp"),
    ]
    assert params["sandboxPolicy"]["networkAccess"] is False

    for method, params in (
        ("item/started", {"item": {"type": "reasoning", "id": "r1"}}),
        ("item/reasoning/summaryTextDelta", {"itemId": "r1", "delta": "Compare costs"}),
        ("item/started", {"item": {"type": "agentMessage", "id": "m1", "phase": "commentary"}}),
        ("item/agentMessage/delta", {"itemId": "m1", "delta": "Checking "}),
        (
            "item/started",
            {"item": {"type": "fileChange", "changes": [{"path": "app/study/units/graphs.json"}]}},
        ),
        ("item/started", {"item": {"type": "agentMessage", "id": "m2", "phase": "final_answer"}}),
        ("item/agentMessage/delta", {"itemId": "m2", "delta": "Depth "}),
        (
            "item/completed",
            {"item": {"type": "agentMessage", "phase": "final_answer", "text": "Depth order."}},
        ),
        ("turn/completed", {"turn": {}}),
    ):
        codex.queues["thread-1"].put({"method": method, "params": params})
    # Reasoning and commentary go to the log; only the marked final answer streams as the answer.
    assert list(turn.events()) == [
        {"type": "thinking", "text": ""},
        {"type": "thinking", "text": "Compare costs"},
        {"type": "note", "text": "Checking "},
        {"type": "status", "text": "Editing graphs.json"},
        {"type": "delta", "text": "Depth "},
        {"type": "final", "text": "Depth order."},
    ]
    assert "thread-1" not in codex.queues


def test_model_menus_keep_the_current_model_of_each_family() -> None:
    from tum_mcp.course.app.ask_runtime import current_models

    def model(name: str, description: str = "Current", default: bool = False) -> dict:
        return {"id": name, "description": description, "default": default}

    listed = [
        model("gpt-6.1-sol", default=True),
        model("gpt-6-astra", "Previous generation model for complex work"),
        model("gpt-6-sol", "Legacy model"),
        model("gpt-6-luna", "Fast and affordable"),
        model("gpt-5.6-luna", "Legacy fast model"),
        model("codex-mini"),
        model("claude-opus-4-8"),
        model("claude-opus-4-7"),
    ]
    assert [item["id"] for item in current_models(listed)] == [
        "gpt-6.1-sol",
        "gpt-6-astra",
        "gpt-6-luna",
        "codex-mini",
        "claude-opus-4-8",
    ]


def test_the_cursor_menu_folds_effort_variants_into_one_model() -> None:
    from tum_mcp.course.app.ask_runtime import parse_cursor_models

    printed = "\n".join(
        [
            "\x1b[2mAvailable models\x1b[22m",
            "",
            "\x1b[36mauto\x1b[39m \x1b[2m- Auto\x1b[22m\x1b[2m (current, default)\x1b[22m",
            "claude-opus-5-5-low - Claude Opus 5.5 1M Low",
            "claude-opus-5-5-medium - Claude Opus 5.5 1M",
            "claude-opus-5-5-medium-fast - Claude Opus 5.5 1M Fast",
            "claude-opus-5-5-high - Claude Opus 5.5 1M High",
            "claude-opus-4-8-high - Claude Opus 4.8 1M",
            "claude-4.6-opus-high-thinking - Claude Opus 4.6 1M Thinking",
            "grok-4.7-low - Grok 4.7  Low",
            "grok-4.7-medium - Grok 4.7  Medium\u200b",
            "",
            "Tip: use --model <id> to switch.",
        ]
    )
    menu = parse_cursor_models(printed)
    assert [(m["id"], m["label"], m["default"], m["effort"], m["efforts"]) for m in menu] == [
        ("auto", "Auto", True, "", []),
        ("claude-opus-5-5", "Claude Opus 5.5 1M", False, "medium", ["low", "medium", "high"]),
        ("grok-4.7", "Grok 4.7", False, "medium", ["low", "medium"]),
    ]
    assert menu[1]["variants"]["high"] == "claude-opus-5-5-high"


def test_the_claude_menu_follows_claude_codes_list() -> None:
    from tum_mcp.course.app.ask_runtime import _menu

    efforts = ["low", "medium", "high"]
    listed = [
        {"value": "default", "resolvedModel": "claude-opus-5-5", "displayName": "Default"},
        {"value": "opus", "resolvedModel": "claude-opus-5-5", "displayName": "Opus 5.5"},
        {
            "value": "claude-fable-5-2",
            "resolvedModel": "claude-fable-5-2",
            "displayName": "Fable 5.2",
        },
        {"value": "fable", "resolvedModel": "claude-fable-5-1", "displayName": "Fable 5.1"},
        {"value": "claude-opus-4-8", "resolvedModel": "claude-opus-4-8", "displayName": "Opus 4.8"},
    ]
    for item in listed:
        item["supportedEffortLevels"] = efforts
    menu = _menu(listed)
    assert [(item["id"], item["default"]) for item in menu] == [
        ("opus", True),
        ("claude-fable-5-2", False),
    ]


def test_a_saved_model_follows_its_family_to_the_newest_version() -> None:
    from tum_mcp.course.app import ask_runtime

    def model(name: str, default: bool = False) -> dict:
        return {
            "id": name,
            "description": "Current",
            "default": default,
            "efforts": ["low", "high"],
            "effort": "low",
        }

    ask_runtime.prefer("codex", "gpt-6.1-terra", "high", "gpt-terra")
    menu = ask_runtime.current_models([model("gpt-6.2-luna", default=True), model("gpt-6.2-terra")])
    assert ask_runtime.options("codex", menu)["model"] == "gpt-6.2-terra"
    assert ask_runtime.options("codex", menu)["effort"] == "high"
    ask_runtime.prefer("codex", "gpt-6.1-sol", "high", "gpt-sol")
    assert ask_runtime.options("codex", menu)["model"] == "gpt-6.2-luna"


def test_a_work_log_keeps_steps_notes_and_thinking_but_not_the_answer() -> None:
    from tum_mcp.course.app.ask_api import LOG_TEXT, WorkLog

    log = WorkLog()
    for event in (
        {"type": "thinking", "text": ""},
        {"type": "thinking", "text": "x" * (LOG_TEXT + 50)},
        {"type": "note", "text": "Reading the   lecture "},
        {"type": "note", "text": "first."},
        {"type": "status", "text": "Reading graphs.json"},
        {"type": "status", "text": "Reading graphs.json"},
        {"type": "status", "text": "Working"},
        {"type": "note", "text": "BFS expands the shallowest node."},
    ):
        log.take(event)
    steps = log.finish("BFS expands the shallowest node. Source: p. 3")
    assert [(step.kind, step.text[:20]) for step in steps] == [
        ("thinking", "x" * 20),
        ("note", "Reading the lecture "),
        ("step", "Reading graphs.json"),
    ]
    assert len(steps[0].text) == LOG_TEXT
    assert steps[0].text.endswith("\u2026")


def test_a_runtime_that_fails_mid_turn_ends_the_stream_with_an_error() -> None:
    from tum_mcp.course.app.ask_runtime import stream

    def events():
        yield {"type": "note", "text": "Reading"}
        raise OSError("pipe closed")

    assert [event["type"] for event in stream(events())] == ["note", "error"]


def test_checks_after_the_answer_keep_the_answer_out_of_the_log() -> None:
    from tum_mcp.course.app.ask_api import WorkLog

    log = WorkLog()
    for event in (
        {"type": "status", "text": "Editing graphs.json"},
        {"type": "note", "text": "Updated the section."},
        {"type": "status", "text": "Checking the edit", "after": True},
    ):
        log.take(event)
    steps = log.finish("Updated the section.")
    assert [(step.kind, step.text) for step in steps] == [
        ("step", "Editing graphs.json"),
        ("step", "Checking the edit"),
    ]


def test_chats_keep_the_newest_fifty(tmp_path, monkeypatch) -> None:
    root = course(tmp_path)
    monkeypatch.setattr(ask_threads, "KEEP", 3)
    for index in range(5):
        ask_threads.create(root, "claude", title=f"Q{index}", place="", route="", anchor=None)

    assert [chat["title"] for chat in ask_threads.listing(root)] == ["Q4", "Q3", "Q2"]
