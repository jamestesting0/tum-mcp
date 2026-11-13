import json

from skill_lab.collect import review_stats, transcript_stats


def _write(path, events):
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")


def test_codex_usage_is_counted_once_per_thread(tmp_path):
    transcript = tmp_path / "transcript"
    transcript.mkdir()
    command = {
        "type": "item.completed",
        "item": {"type": "command_execution", "aggregated_output": "abcd", "exit_code": 0},
    }
    _write(
        transcript / "turn-1.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            command,
            {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 10}},
        ],
    )
    _write(
        transcript / "turn-2.jsonl",
        [
            {"type": "thread.started", "thread_id": "t"},
            command,
            {"type": "turn.completed", "usage": {"input_tokens": 250, "output_tokens": 20}},
        ],
    )

    stats = transcript_stats(tmp_path, "codex")

    assert stats["tokens"] == 270
    assert stats["turn_tokens"] == [110, 160]
    assert stats["output_chars"] == 8
    assert stats["tool_calls"] == 2


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
