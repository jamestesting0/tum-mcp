import json

from skill_lab import cli, rounds


def create(round_id: str, *options: str) -> int:
    return cli.main(
        [
            "round",
            "new",
            round_id,
            "--fresh",
            "--scenario",
            "fai-authoring-026",
            "--author",
            "codex:gpt-6.1-terra:high",
            "--reason",
            "Test round budget",
            *options,
        ]
    )


def test_zero_judge_budget_does_not_require_a_judge_profile(lab_state, monkeypatch, capsys) -> None:
    def validate(spec, role: str) -> None:
        assert role == "author"

    monkeypatch.setattr(rounds, "validate_spec", validate)
    assert create("no-judge", "--budget-judges", "0") == 0
    config = json.loads(capsys.readouterr().out)
    assert config["roles"]["judge"] is None
    assert config["confirm_judges"] == []
    for command, args in (("judge", ()), ("review", ("--run", "candidate"))):
        assert cli.main([command, "no-judge", *args]) == 1
        assert "budget" in capsys.readouterr().err


def test_positive_judge_budget_requires_a_judge(lab_state, capsys) -> None:
    assert create("needs-judge") == 1
    assert "positive judge budget requires --judge" in capsys.readouterr().err
