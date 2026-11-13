import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from tum_mcp.cli import app


def test_report_prints_a_short_summary_and_saves_the_whole_result(project: Path) -> None:
    runner = CliRunner()
    # Given a built course, a report without a section stays short for the calling agent.
    short = runner.invoke(app, ["study", "report", str(project)])
    whole = runner.invoke(app, ["study", "report", str(project), "--json"])
    assert short.exit_code == 0 and whole.exit_code == 0
    summary = json.loads(short.stdout)
    # Then the summary points at the saved full result, which equals the --json output.
    saved = json.loads((project / summary["full"]).read_text(encoding="utf-8"))
    assert saved == json.loads(whole.stdout)
    assert len(short.stdout) < len(whole.stdout)
    assert set(summary["summary"]) == set(saved)


def test_schema_prints_one_definition_on_request() -> None:
    runner = CliRunner()
    unit = runner.invoke(app, ["study", "schema", "content", "--definition", "Unit"])
    assert unit.exit_code == 0
    assert "blocks" in json.loads(unit.stdout)["properties"]
    unknown = runner.invoke(app, ["study", "schema", "content", "--definition", "Nope"])
    assert unknown.exit_code != 0


def test_schema_examples_are_reachable_from_cli() -> None:
    runner = CliRunner()
    listing = runner.invoke(app, ["study", "schema", "--example"])
    example = runner.invoke(app, ["study", "schema", "--example", "walkthrough-tree"])
    assert listing.exit_code == 0
    assert example.exit_code == 0
    assert "walkthrough-tree" in json.loads(listing.stdout)
    assert json.loads(example.stdout)["stage"]["layout"] == "tree"


def test_readiness_summary_keeps_all_problems_and_saves_full_result(
    project: Path, monkeypatch
) -> None:
    from tum_mcp.course.checks import preparation

    problems = tuple(f"study/one: problem {i}" for i in range(6))
    reading = preparation.Readiness(
        identifier="scope", items={"study/one": [], "study/two": []}, problems=problems
    )
    monkeypatch.setattr(preparation, "assess", lambda root, scope: reading)
    runner = CliRunner()
    args = ["study", "report", str(project), "--section", "readiness", "--preparation", "scope"]
    short = runner.invoke(app, args)
    full = runner.invoke(app, [*args, "--json"])
    assert short.exit_code == full.exit_code == 0
    summary = json.loads(short.stdout)
    assert summary["problems"] == list(problems)
    assert summary["items"] == {
        "study/one": {"status": "blocked", "problems": 6},
        "study/two": {"status": "ready", "problems": 0},
    }
    assert json.loads((project / summary["full"]).read_text()) == json.loads(full.stdout)


def test_batch_start_names_missing_and_invalid_batch_file(project: Path) -> None:
    runner = CliRunner()
    args = ["study", "task", "start", str(project), "--batch", "broken", "--owner", "test"]
    missing = runner.invoke(app, args)
    path = project / ".tum-mcp/batches/broken.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    invalid = runner.invoke(app, args)
    for result in (missing, invalid):
        assert result.exit_code != 0
        assert ".tum-mcp/batches/broken.json" in str(result.exception)
        assert "tum-mcp study schema batch" in str(result.exception)


def test_repeated_example_requires_ruling_without_failing_lint(project: Path, monkeypatch) -> None:
    from tum_mcp.course.checks import plans
    from tum_mcp.course.cli import _lint_item
    from tum_mcp.course.review.models import RULED_FLAGS

    monkeypatch.setattr(plans, "read_plan", lambda root, item: None)
    context = SimpleNamespace(
        flags_by_item={"study/one": [{"flag": "repeated_example"}]}, answer_keys=[]
    )
    result = _lint_item(project, context, "study/one", None)
    assert result["passed"] is True
    assert RULED_FLAGS["repeated_example"] == "redundancy.said_once"
