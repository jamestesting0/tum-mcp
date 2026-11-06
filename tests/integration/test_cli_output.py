import json
from pathlib import Path

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
