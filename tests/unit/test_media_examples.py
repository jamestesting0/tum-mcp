import json

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.media.examples import _models, catalogue, example


@pytest.mark.parametrize("medium", ["video", "audio"])
def test_every_media_example_validates_and_states_its_rule(medium: str) -> None:
    models = _models()[medium]
    assert set(catalogue(medium)) == set(models)
    for name, model in models.items():
        rule, value = example(medium, name)
        model.model_validate(value)
        assert len(rule.split()) >= 10, name


def test_the_cli_prints_the_example_and_its_rule_apart() -> None:
    result = CliRunner().invoke(app, ["video-notes", "schema", "--example", "pattern-beat"])
    assert result.exit_code == 0, result.output
    assert result.stderr.startswith("Rule: One moment of a pattern video.")
    assert json.loads(result.stdout)["kind"] == "step"
