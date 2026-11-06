import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app import visuals
from tum_mcp.course.app.build import build
from tum_mcp.course.checks.plans import read_plan, record_gate


@pytest.mark.parametrize("command", ["lint", "verify"])
def test_scoped_checks_skip_unrelated_answer_keys(project: Path, command: str) -> None:
    checks = project / ".tum-mcp/checks/study"
    checks.mkdir(parents=True, exist_ok=True)
    stamp = project / "unrelated-key-ran"
    (checks / "dfs.py").write_text(f"from pathlib import Path\nPath({str(stamp)!r}).touch()\n")
    result = CliRunner().invoke(app, ["study", command, str(project), "--item", "bfs", "--json"])
    assert result.exit_code == 0, result.output
    assert not stamp.exists()
    result = CliRunner().invoke(app, ["study", command, str(project), "--json"])
    assert result.exit_code == 0, result.output
    assert stamp.exists()


def test_scoped_plan_packet_preserves_provisional_status(project: Path) -> None:
    for key in ("bfs", "dfs"):
        plan = project / ".tum-mcp/plans/study" / f"{key}.json"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(json.dumps({"item": f"study/{key}"}))
    plan = read_plan(project, "study/bfs")
    assert plan is not None
    record_gate(
        project, [{"item": plan.item, "fingerprint": plan.fingerprint(), "verdict": "pass"}], "same"
    )
    result = CliRunner().invoke(app, ["review", "plans", str(project), "--item", "study/bfs"])
    assert result.exit_code == 0, result.output
    plans = json.loads(result.output)["plans"]
    assert [(item["item"], item["status"]) for item in plans] == [("study/bfs", "provisional")]


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Owned browser QA."
)
def test_matching_build_reuses_browser_checks(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(project, publish=False)
    first = visuals.check_visuals(project, ("graphs",))
    assert first["passed"]
    first_interaction = visuals.check_interactions(project, ("graphs",))
    assert first_interaction["passed"]

    def no_render(*args, **kwargs) -> None:
        pytest.fail("An exact receipt should avoid opening the browser.")

    monkeypatch.setattr(visuals, "_measure", no_render)
    monkeypatch.setattr(visuals, "_open", no_render)
    assert visuals.check_visuals(project, ("graphs",)) == first
    assert visuals.check_interactions(project, ("graphs",)) == first_interaction


def test_receipts_merge_widths_and_cannot_certify_an_edited_build(project: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from tum_mcp.course.app.browser_evidence import (
        BrowserBuild,
        build_files,
        cached,
        read_receipt,
        save_receipt,
    )
    from tum_mcp.errors import CampusError

    build(project, publish=False)
    digest, managed = build_files(project)
    identity = BrowserBuild(build=digest, managed=managed, browser="1" * 64, checks="2" * 64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(save_receipt, project, identity, {width: True}, (width, {"passed": True}))
            for width in ("phone", "desktop")
        ]
        for job in jobs:
            job.result(timeout=10)
    receipt = read_receipt(project)
    assert receipt and receipt.states == {"phone": True, "desktop": True}
    assert cached(project, identity, "phone", ["phone", "desktop"]) == {"passed": True}
    save_receipt(project, identity, {"phone": False})
    assert cached(project, identity, "phone", ["phone"]) is None

    css = project / "app/styles.css"
    css.write_text(css.read_text(encoding="utf-8") + "\n/* changed while capturing */\n")
    with pytest.raises(CampusError, match="changed during browser checks"):
        save_receipt(project, identity, {"phone": True})


def test_visual_receipt_loses_its_evidence_when_the_capture_is_removed(project: Path) -> None:
    from tum_mcp.course.app.browser_evidence import (
        BrowserBuild,
        build_files,
        cached,
        read_receipt,
        save_receipt,
    )

    build(project, publish=False)
    digest, managed = build_files(project)
    identity = BrowserBuild(build=digest, managed=managed, browser="1" * 64, checks="2" * 64)
    state = "visual/phone/study/graphs"
    relative = ".tum-mcp/visuals/graphs-phone.png"
    image = project / relative
    image.parent.mkdir()
    image.touch()
    result = {"passed": True}
    save_receipt(
        project, identity, {state: True}, ("request", result), captures={state: (relative,)}
    )
    assert cached(project, identity, "request", [state]) == result
    receipt = read_receipt(project)
    assert receipt and receipt.evidence(project, state)
    image.unlink()
    assert not receipt.evidence(project, state)
    assert cached(project, identity, "request", [state]) is None
