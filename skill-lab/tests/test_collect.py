import json
import subprocess
import sys
from pathlib import Path

from skill_lab import shim
from skill_lab.collect import checker_phases, collect_run, review_stats, transcript_stats


def _write(path, events):
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")


def test_codex_usage_is_counted_once_per_thread(tmp_path):
    transcript = tmp_path / "transcript"
    transcript.mkdir()
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "turns": [
                    {"turn": 1, "parts": [{"label": "turn-1"}, {"label": "turn-1-reply-1"}]},
                    {"turn": 2, "parts": [{"label": "turn-2"}]},
                ]
            }
        )
    )
    command = {
        "type": "item.completed",
        "item": {"type": "command_execution", "aggregated_output": "abc\u03c0", "exit_code": 0},
    }
    _write(
        transcript / "turn-1.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            command,
            {"type": "turn.completed", "usage": {"input_tokens": 53027776}},
        ],
    )
    _write(
        transcript / "turn-1-reply-1.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "turn.completed", "usage": {"input_tokens": 53366734}},
        ],
    )
    _write(
        transcript / "turn-2.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            command,
            {"type": "turn.completed", "usage": {"input_tokens": 114658765}},
        ],
    )

    stats = transcript_stats(tmp_path, "codex")

    assert stats["tokens"] == 114658765
    assert stats["turn_tokens"] == [53027776, 338958, 61292031]
    assert stats["output_chars"] == 8
    assert stats["output_bytes"] == 10
    assert stats["tool_calls"] == 2
    assert all("start" not in phase and "minutes" not in phase for phase in stats["phase_table"])


def test_review_stats_counts_checker_sessions_and_verdicts(tmp_path):
    broker = tmp_path / ".lab-broker"
    broker.mkdir()
    for name, stdout in (
        ("a", {"recorded": ["study/x"], "verdicts": {}}),
        ("b", {"recorded": ["study/x"], "opened": 2, "resolved": 0}),
        ("c", {"summary": {"passed": True}}),
    ):
        (broker / f"{name}.response.json").write_text(
            json.dumps({"code": "0", "stdout": json.dumps(stdout)}), encoding="utf-8"
        )
    packets = tmp_path / "course" / ".tum-mcp" / "review" / "packets"
    packets.mkdir(parents=True)
    (packets / "r1-study-unit-1.answer.json").write_text(
        json.dumps(
            {"items": [{"checks": {"a": {"verdict": "pass"}, "b": {"verdict": "uncertain"}}}]}
        ),
        encoding="utf-8",
    )

    stats = review_stats(tmp_path)

    assert stats == {
        "plan_checks": 1,
        "packet_checks": 1,
        "verdicts": {"pass": 1, "uncertain": 1},
    }


def test_uncertain_verdicts_are_grouped_by_missing_evidence(tmp_path):
    packets = tmp_path / "course" / ".tum-mcp" / "review" / "packets"
    packets.mkdir(parents=True)
    checks = {
        "a": {"verdict": "uncertain", "missing": "Slide 4 image cannot be opened."},
        "b": {"verdict": "uncertain", "missing": "Slide 4 image cannot be opened."},
        "c": {"verdict": "uncertain", "reason": "Legacy source is unavailable."},
        "d": {"verdict": "uncertain"},
        "e": {"verdict": "pass", "reason": "Read the slide."},
    }
    (packets / "r1.answer.json").write_text(json.dumps({"items": [{"checks": checks}]}))

    stats = review_stats(tmp_path)

    assert stats["uncertain_causes"] == {
        "Slide 4 image cannot be opened.": 2,
        "Legacy source is unavailable.": 1,
    }
    assert stats["verdicts"] == {"uncertain": 4, "pass": 1}


def test_collected_phase_table_orders_commands_by_start_in_each_turn(lab_state):
    tmp_path = lab_state / "rounds" / "r1" / "runs" / "candidate-1"
    transcript = tmp_path / "transcript"
    transcript.mkdir(parents=True)
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "author": "codex:gpt-6.1-terra:high:fast",
                "status": "completed",
                "variant": "candidate",
                "turns": [
                    {"turn": 2, "parts": [{"label": "turn-2"}]},
                    {"turn": 1, "parts": [{"label": "turn-1"}]},
                ],
            }
        )
    )
    first = {
        "id": "p",
        "type": "command_execution",
        "command": "tum-mcp review run-checker . --plans",
    }
    second = {"id": "b", "type": "command_execution", "command": "tum-mcp study build ."}
    _write(
        transcript / "turn-1.jsonl",
        [
            {"type": "item.started", "timestamp": "2026-11-14T00:00:00Z", "item": first},
            {"type": "item.started", "timestamp": "2026-11-14T00:01:00Z", "item": second},
            {"type": "item.completed", "timestamp": "2026-11-14T00:02:00Z", "item": second},
            {"type": "item.completed", "timestamp": "2026-11-14T00:03:00Z", "item": first},
        ],
    )
    _write(
        transcript / "turn-2.jsonl",
        [
            {
                "type": "item.started",
                "_lab_timestamp": "2026-11-14T00:04:00Z",
                "item": {
                    "id": "r",
                    "type": "command_execution",
                    "command": "tum-mcp study rebuild .",
                },
            },
            {
                "type": "item.completed",
                "_lab_timestamp": "2026-11-14T00:05:30Z",
                "item": {
                    "id": "r",
                    "type": "command_execution",
                    "command": "tum-mcp study rebuild .",
                },
            },
        ],
    )

    metrics = collect_run("r1", "candidate-1", visuals=False)
    phases = metrics["phase_table"]

    assert json.loads((tmp_path / "metrics.json").read_text())["phase_table"] == phases
    assert [(p["turn"], p["kind"], p["start"], p["end"], p["minutes"]) for p in phases] == [
        (1, "plan_check", "2026-11-14T00:00:00Z", "2026-11-14T00:03:00Z", 3),
        (1, "study.build", "2026-11-14T00:01:00Z", "2026-11-14T00:02:00Z", 1),
        (2, "study.rebuild", "2026-11-14T00:04:00Z", "2026-11-14T00:05:30Z", 1.5),
    ]


def test_checker_phases_include_refused_answers_and_repairs(tmp_path):
    broker = tmp_path / ".lab-broker"
    broker.mkdir()
    _write(
        broker / "packet.sessions.jsonl",
        [
            {
                "event": "started",
                "kind": "review_packet",
                "attempt": 0,
                "timestamp": "2026-11-14T00:00:10Z",
            },
            {
                "event": "completed",
                "attempt": 0,
                "status": "completed",
                "timestamp": "2026-11-14T00:01:10Z",
            },
            {
                "event": "started",
                "kind": "review_packet",
                "attempt": 1,
                "timestamp": "2026-11-14T00:01:20Z",
            },
            {
                "event": "completed",
                "attempt": 1,
                "status": "failed",
                "timestamp": "2026-11-14T00:01:50Z",
            },
        ],
    )
    parent = {
        "turn": 2,
        "part": "turn-2",
        "kind": "review_packet",
        "start": "2026-11-14T00:00:00Z",
        "end": "2026-11-14T00:02:00Z",
    }

    phases = checker_phases(tmp_path, [parent])

    assert [(p["turn"], p["attempt"], p["repair"], p["status"], p["minutes"]) for p in phases] == [
        (2, 0, False, "refused", 1),
        (2, 1, True, "failed", 0.5),
    ]
    assert checker_phases(tmp_path / "old-run", []) == []


def test_checker_observation_keeps_output_and_records_every_invocation(tmp_path):
    broker = tmp_path / ".lab-broker"
    broker.mkdir()
    log = broker / "packet.sessions.jsonl"
    command = [
        sys.executable,
        "-I",
        str(Path(shim.__file__)),
        "--lab-checker",
        str(log),
        "review_packet",
        sys.executable,
        "-c",
        "import sys; print('private checker prompt \u03c0'); sys.exit(3)",
    ]

    results = [
        subprocess.run(
            [*command[:-1], command[-1].replace("exit(3)", f"exit({code})")],
            capture_output=True,
            text=True,
            check=False,
        )
        for code in (0, 3)
    ]

    assert [(result.returncode, result.stdout) for result in results] == [
        (0, "private checker prompt \u03c0\n"),
        (3, "private checker prompt \u03c0\n"),
    ]
    phases = checker_phases(tmp_path, [])
    assert [(p["attempt"], p["repair"], p["status"]) for p in phases] == [
        (0, False, "refused"),
        (1, True, "failed"),
    ]
    assert all(phase["minutes"] >= 0 for phase in phases)
    assert "private checker prompt" not in log.read_text()
