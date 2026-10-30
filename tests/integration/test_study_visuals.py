"""The render check: it passes a synthetic FAI-style corpus, follows the content and the app
it measured, and catches the broken layouts of review-course's calibration gallery."""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.study_build import build, read_content
from tum_mcp.study_review import revision
from tum_mcp.study_visuals import app_revision, report_path

CORPUS = Path(__file__).parents[1] / "fixtures/visual-corpus.json"
browser = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1",
    reason="Owned browser checks require TUM_MCP_BROWSER_INTEGRATION=1.",
)


def invoke(*args: str) -> dict:
    result = CliRunner().invoke(app, ["study", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def render(project: Path) -> dict:
    return invoke("report", str(project), "--section", "render")["render"]


def add_corpus(project: Path) -> None:
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    content["units"].append(json.loads(CORPUS.read_bytes()))
    path.write_text(json.dumps(content), encoding="utf-8")
    build(project, publish=False)


def test_render_report_follows_the_content_and_the_app(project: Path) -> None:
    # Given a course whose units draw visuals, nothing has been checked yet.
    first = render(project)
    assert first["checked"] is False and first["passed"] is False
    unchecked = set(first["unchecked"])
    assert unchecked == {
        f"study/{key}" for key in ("bfs", "dfs", "graphs", "weighted", "probability")
    }
    # When a check of the current app recorded every unit, only its defects remain.
    units = {f"study/{unit.key}": unit for unit in read_content(project).units}
    defect = {"code": "label_overlap", "detail": '"2" overlaps "12"'}
    items = {
        item: {
            "revision": revision(units[item]),
            "checked_at": "2026-10-30",
            "sheets": [],
            "visuals": [
                {
                    "id": "block:1",
                    "kind": "diagram",
                    "title": "A graph",
                    "widths": {
                        "phone": {"findings": [defect] if item == "study/bfs" else [], "facts": {}}
                    },
                }
            ],
        }
        for item in unchecked
    }
    site = project / "study"
    record = {"schema_version": 1, "app": app_revision(site), "items": items}
    report_path(project).write_text(json.dumps(record), encoding="utf-8")
    measured = render(project)
    assert measured["unchecked"] == [] and measured["stale"] == []
    assert [(d["item"], d["code"]) for d in measured["defects"]] == [("study/bfs", "label_overlap")]
    # Then a changed app makes every record stale until the check runs again.
    report_path(project).write_text(json.dumps(record | {"app": "0" * 16}), encoding="utf-8")
    stale = render(project)
    assert stale["stale"] == sorted(unchecked) and stale["defects"] == []


@browser
def test_corpus_passes_and_an_edit_makes_its_check_stale(project: Path) -> None:
    # Given the FAI-style corpus: seven graphs, five UML diagrams and seven plots.
    add_corpus(project)
    checked = invoke("visuals", str(project), "--unit", "visuals")
    # Then every visual is drawn as authored, clear and legible at every width.
    assert checked["passed"] is True, checked["defects"]
    assert checked["checked"] == ["study/visuals"]
    assert checked["sheets"] and all((project / sheet).is_file() for sheet in checked["sheets"])
    record = json.loads(report_path(project).read_bytes())["items"]["study/visuals"]
    assert len(record["visuals"]) == 19
    widths = {width for visual in record["visuals"] for width in visual["widths"]}
    assert widths == {"phone", "narrow", "desktop"}
    assert "study/visuals" not in render(project)["unchecked"]
    # When the unit changes, its check is stale until it runs again.
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    content["units"][-1]["summary"] += " Revised."
    path.write_text(json.dumps(content), encoding="utf-8")
    assert "study/visuals" in render(project)["stale"]


@browser
def test_gallery_shows_what_the_check_catches_and_what_needs_a_reviewer(project: Path) -> None:
    findings = invoke("visuals", str(project), "--gallery")["findings"]
    # A scrambled map breaks measurable rules; its lattice version passes.
    assert any(code.startswith("coincident_edges") for code in findings["gallery:map-scrambled"])
    assert findings["gallery:map-lattice"] == []
    # Three worded boxes in a row scroll on a phone; with the third on the next row they fit.
    assert "scrolls (phone)" in findings["gallery:mdp-row-on-phone"]
    assert findings["gallery:mdp-two-rows"] == []
    # An invented state or a dropped class draws cleanly: only the visual review catches them.
    assert findings["gallery:mdp-fake-state"] == []
    assert not [
        code for code in findings["gallery:composite-without-client"] if "scrolls" not in code
    ]
