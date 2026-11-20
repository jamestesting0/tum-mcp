import json
import os
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app import visuals
from tum_mcp.course.app.browser_evidence import current_sheets
from tum_mcp.course.app.build import build
from tum_mcp.course.checks.plans import plan_packet, read_plan, record_gate
from tum_mcp.course.checks.preparation import _browser_problems
from tum_mcp.errors import CampusError

browser = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Owned browser QA."
)


@pytest.mark.parametrize("command", ["lint", "verify"])
def test_scoped_checks_skip_unrelated_answer_keys(project: Path, command: str) -> None:
    checks = project / ".tum-mcp/checks/study"
    checks.mkdir(parents=True, exist_ok=True)
    stamp = project / "unrelated-key-ran"
    (checks / "dfs.py").write_text(
        f"from pathlib import Path\nPath({str(stamp)!r}).touch()\n",
        encoding="utf-8",
    )
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


def test_checker_batch_precedence_and_completion(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_preparation_workflow import write

    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review import runner
    from tum_mcp.course.workflow import tasks

    plan = project / ".tum-mcp/plans/study/bfs.json"
    write(plan, {"item": "study/bfs"})
    course = load_state(project).course.key
    for name, items in (("older", ["study/bfs", "study/dfs"]), ("active.v_2", ["study/bfs"])):
        write(
            project / f".tum-mcp/batches/{name}.json",
            {"course_key": course, "request": "Study graphs.", "items": items},
        )
    monkeypatch.setattr(runner, "_ask", lambda *args: pytest.fail("Unexpected host invocation"))
    with pytest.raises(CampusError, match=r"active\.v_2.*older"):
        runner.run(project, None, "codex", plans=True)

    monkeypatch.setenv("CODEX_THREAD_ID", "task-8")
    tasks.begin(project, "active.v_2")
    assert [row["item"] for row in plan_packet(project)["plans"]] == ["study/bfs"]
    with pytest.raises(CampusError, match="Missing: study/dfs"):
        plan_packet(project, batch="older")
    plan.unlink()
    with pytest.raises(CampusError, match="Missing: study/bfs"):
        runner.run(project, None, "codex", plans=True)


@pytest.mark.parametrize(
    "reply", ["empty", "partial", "duplicate", "foreign", "stale", "invalid", "full"]
)
def test_checker_records_only_a_complete_current_response(
    project: Path, monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    from test_preparation_workflow import write

    from tum_mcp.course.review import runner

    items = ("study/bfs", "study/dfs")
    for key in items:
        write(project / f".tum-mcp/plans/{key}.json", {"item": key})
    entries = [row | {"verdict": "pass"} for row in plan_packet(project)["answer"]["items"]]
    first, last = entries
    replies = {
        "empty": [],
        "partial": [first],
        "duplicate": [first, first],
        "foreign": [first, last | {"item": "study/graphs"}],
        "stale": [first, last | {"fingerprint": "0" * 16}],
        "invalid": [first, last | {"verdict": "fail"}],
        "full": entries,
    }
    monkeypatch.setattr(runner, "_ask", lambda *args: {"items": replies[reply]})
    if reply == "full":
        assert set(runner.run(project, None, "codex", plans=True)["recorded"]) == set(items)
        assert plan_packet(project)["plans"] == []
    else:
        with pytest.raises(CampusError):
            runner.run(project, None, "codex", plans=True)
        assert {row["item"] for row in plan_packet(project)["plans"]} == set(items)


def test_batch_readiness_only_runs_requested_answer_keys(project: Path) -> None:
    from test_preparation_workflow import write

    from tum_mcp.course.checks.batch import assess_batch
    from tum_mcp.course.project.store import load_state

    checks = project / ".tum-mcp/checks/study"
    checks.mkdir(parents=True, exist_ok=True)
    stamp = project / "unrelated-key-ran"
    (checks / "dfs.py").write_text(f"from pathlib import Path\nPath({str(stamp)!r}).touch()\n")
    (checks / "bfs.py").write_text('print(\'{"exact_values": {"title": "Wrong title"}}\')\n')
    write(
        project / ".tum-mcp/batches/selected.json",
        {
            "course_key": load_state(project).course.key,
            "request": "Study BFS.",
            "items": ["study/bfs"],
        },
    )

    report = assess_batch(project, "selected")
    assert any("study/bfs: computed answers do not match" in issue for issue in report.problems)
    assert not stamp.exists()


def test_dotted_and_underscore_route_round_trips_through_checker(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from documents import content_file
    from test_preparation_workflow import write
    from test_review_loop import packets

    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review import loop, runner
    from tum_mcp.course.workflow import tasks

    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    unit = next(unit for unit in content["units"] if unit["key"] == "bfs")
    unit["key"] = "intro_bfs.v2"
    path.write_text(json.dumps(content))
    build(project, publish=False)

    item = "study/intro_bfs.v2"
    write(project / f".tum-mcp/plans/{item}.json", {"item": item})
    write(
        project / ".tum-mcp/batches/scope_1.v2.json",
        {"course_key": load_state(project).course.key, "request": "Study BFS.", "items": [item]},
    )
    tasks.begin(project, "scope_1.v2", owner="codex:fixture")

    response = plan_packet(project, batch="scope_1.v2")["answer"]
    monkeypatch.setattr(
        runner,
        "_ask",
        lambda *args: {"items": [row | {"verdict": "pass"} for row in response["items"]]},
    )
    result = CliRunner().invoke(
        app, ["review", "run-checker", str(project), "--plans", "--batch", "scope_1.v2"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["recorded"] == [item]

    loop.start(project, workspaces=("study",), ad_hoc=True)
    assert item in {
        entry["item"]
        for packet in packets(project, loop.next_round(project))
        for entry in packet["items"]
    }


@pytest.mark.parametrize(
    "route", ["study", "study/", "study//topic", "study/" + "a" * 101, "study/Topic"]
)
def test_batch_registration_rejects_invalid_route_shapes(project: Path, route: str) -> None:
    from pydantic import ValidationError
    from test_preparation_workflow import write

    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.workflow import tasks

    write(
        project / ".tum-mcp/batches/invalid.json",
        {"course_key": load_state(project).course.key, "request": "Study topic.", "items": [route]},
    )
    with pytest.raises(ValidationError, match="items.0"):
        tasks.begin(project, "invalid", owner="codex:fixture")


def test_review_packet_reads_shared_digest_once_and_refreshes_after_edit(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from documents import content_file
    from test_preparation_workflow import write
    from test_review_loop import packets

    from tum_mcp.course.project.store import load_state
    from tum_mcp.course.review import loop
    from tum_mcp.course.sources import digests

    source = next(entry for entry in load_state(project).resources if entry.resource.key == "bfs")
    write(project / ".tum-mcp/digests/bfs.json", {"source": "bfs", "sha256": source.sha256})
    path = content_file(project, "study")
    content = json.loads(path.read_bytes())
    units = {unit["key"]: unit for unit in content["units"]}
    units["dfs"]["sources"].extend(units["bfs"]["sources"])
    path.write_text(json.dumps(content))
    lookup = digests.digest_evidence
    reads = []

    def count(root: Path, key: str, *args):
        if key == "bfs":
            reads.append(key)
        return lookup(root, key, *args)

    monkeypatch.setattr(digests, "digest_evidence", count)
    loop.start(project, budget=2, workspaces=("study",))

    def statuses(opened: dict) -> dict[str, str]:
        return {
            item["item"]: row["status"]
            for packet in packets(project, opened)
            for item in packet["items"]
            for row in item["digests"]
            if row["source"] == "bfs" and item["item"] in {"study/bfs", "study/dfs"}
        }

    assert statuses(loop.next_round(project)) == dict.fromkeys(
        ("study/bfs", "study/dfs"), "current"
    )
    assert reads == ["bfs"]
    loop.close_round(project, incomplete=True)
    assert source.path
    material = project / source.path
    material.write_bytes(material.read_bytes() + b"\n% fixture revision\n")
    reads.clear()
    assert statuses(loop.next_round(project)) == dict.fromkeys(("study/bfs", "study/dfs"), "stale")
    assert reads == ["bfs"]


def test_large_batch_assesses_each_bound_scope_once(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_preparation_workflow import bounded_scope, write

    from tum_mcp.course.checks import coverage_plan

    _, scope = bounded_scope(project)
    items = tuple(f"study/lesson-{index}" for index in range(29))
    for key in items:
        write(project / f".tum-mcp/plans/{key}.json", {"item": key, "preparation": "bounded"})
    write(
        project / ".tum-mcp/batches/selected.json",
        {
            "course_key": scope["course_key"],
            "request": "Study the topic.",
            "items": items,
            "preparations": ["bounded"],
        },
    )
    real_assess = coverage_plan.assess_plan
    calls = []

    def count(root: Path, identifier: str, batches: tuple[str, ...]):
        calls.append((identifier, batches))
        return real_assess(root, identifier, batches)

    monkeypatch.setattr(coverage_plan, "assess_plan", count)
    packet = plan_packet(project, items)
    assert calls == [("bounded", ("selected",))]
    calls.clear()
    record_gate(project, [item | {"verdict": "pass"} for item in packet["answer"]["items"]], "same")
    assert calls == [("bounded", ("selected",))]
    calls.clear()
    assert {plan["status"] for plan in plan_packet(project, items)["plans"]} == {"provisional"}
    assert calls == [("bounded", ("selected",))]


@browser
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


@browser
@pytest.mark.parametrize("fault", ["removed", "truncated", "replaced", "hashless"])
def test_visual_recapture_only_reruns_the_affected_width(project: Path, fault: str) -> None:
    item = "study/graphs"
    first = visuals.check_visuals(project, ("graphs",), phone=True)
    assert first["passed"], first["defects"]
    sheets = current_sheets(project)[item]
    desktop_name, *_ = sheets["desktop"]
    phone_name, *_ = sheets["phone"]
    desktop = project / desktop_name
    phone = project / phone_name
    for path in (desktop, phone):
        with Image.open(path, formats=("PNG",)) as image:
            image.load()
    assert desktop.read_bytes() != phone.read_bytes()
    os.utime(phone, ns=(0, 0))
    retained_time = phone.stat().st_mtime_ns

    if fault == "removed":
        desktop.unlink()
    elif fault == "truncated":
        desktop.write_bytes(desktop.read_bytes()[:32])
    elif fault == "replaced":
        desktop.write_bytes(phone.read_bytes())
    else:
        path = project / ".tum-mcp/browser-check.json"
        saved = json.loads(path.read_bytes())
        saved.get("capture_digests", {}).pop("visual/desktop/study/graphs", None)
        path.write_text(json.dumps(saved), encoding="utf-8")

    assert [problem.message for problem in _browser_problems(project, [], {item})] == [
        "visual/desktop/study/graphs: browser evidence is missing."
    ]
    assert current_sheets(project)[item] == {"phone": sheets["phone"]}
    repaired = visuals.check_visuals(project, ("graphs",), phone=True)
    assert repaired["passed"], repaired["defects"]
    assert phone.stat().st_mtime_ns == retained_time
    assert _browser_problems(project, [], {item}) == []
    assert current_sheets(project)[item] == sheets
    report = visuals.read_report(project)
    assert report is not None
    assert {"phone", "narrow", "desktop"} == set(report["items"][item]["visuals"][0]["widths"])


@browser
def test_custom_css_requires_fresh_visuals_and_interactions(project: Path) -> None:
    item, route = "study/graphs", "#graphs/content"
    css = project / "app/styles.css"
    custom = css.read_bytes() + b"\n/* Local variant */\n"
    css.write_bytes(custom)
    build(project, publish=False)
    assert css.read_bytes() == custom

    assert visuals.check_interactions(project, ("graphs",))["passed"]
    assert _browser_problems(project, [route], set()) == []
    assert visuals.check_visuals(project, ("graphs",))["passed"]
    assert _browser_problems(project, [route], {item}) == []
    assert current_sheets(project)[item]["desktop"]

    css.write_bytes(custom + b"/* Another revision */\n")
    assert "stale" in _browser_problems(project, [route], {item})[0].message
    assert current_sheets(project) == {}
    assert visuals.check_visuals(project, ("graphs",))["passed"]
    assert [problem.message for problem in _browser_problems(project, [route], {item})] == [
        "interact/desktop/#graphs/content: browser evidence is missing.",
        "shell/desktop/dark/study: browser evidence is missing.",
        "shell/desktop/light/study: browser evidence is missing.",
    ]
    assert visuals.check_interactions(project, ("graphs",))["passed"]
    assert _browser_problems(project, [route], {item}) == []


@browser
@pytest.mark.parametrize("custom", [False, True], ids=["stock", "custom"])
def test_only_stock_templates_reuse_an_unchanged_sibling(project: Path, custom: bool) -> None:
    from documents import content_file

    css = project / "app/styles.css"
    if custom:
        css.write_bytes(css.read_bytes() + b"\n/* Local variant */\n")
    first = visuals.check_visuals(project, ("graphs", "dfs"))
    assert first["passed"], first["defects"]
    graphs = current_sheets(project)["study/graphs"]["desktop"]

    path = content_file(project, "study")
    data = json.loads(path.read_bytes())
    next(unit for unit in data["units"] if unit["key"] == "dfs")["title"] += " (edited)"
    path.write_text(json.dumps(data), encoding="utf-8")
    build(project, publish=False)
    second = visuals.check_visuals(project, ("graphs", "dfs"))

    assert second["passed"], second["defects"]
    assert second.get("unchanged", []) == ([] if custom else ["study/graphs"])
    assert (current_sheets(project)["study/graphs"]["desktop"] == graphs) is not custom


def test_browser_identity_survives_broker_and_sandbox_platform_labels(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.app import browser_evidence

    browser_binary = tmp_path / "chrome"
    browser_binary.write_bytes(b"one version")
    browser = browser_evidence.BrowserChoice("Chrome", str(browser_binary))
    monkeypatch.setattr(browser_evidence.platform, "platform", lambda: "macOS-arm64-Mach-O")
    broker_identity = browser_evidence.browser_identity(project, browser)
    monkeypatch.setattr(browser_evidence.platform, "platform", lambda: "macOS-arm64")
    assert browser_evidence.browser_identity(project, browser) == broker_identity
    browser_binary.write_bytes(b"a replaced browser executable")
    assert browser_evidence.browser_identity(project, browser).browser != broker_identity.browser


def test_receipts_merge_widths_and_cannot_certify_an_edited_build(project: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from tum_mcp.course.app.browser_evidence import (
        BrowserBuild,
        build_files,
        cached,
        read_receipt,
        save_receipt,
    )

    build(project, publish=False)
    digest, managed = build_files(project)
    identity = BrowserBuild(
        build=digest, shell="3" * 64, managed=managed, browser="1" * 64, checks="2" * 64
    )
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
    identity = BrowserBuild(
        build=digest, shell="3" * 64, managed=managed, browser="1" * 64, checks="2" * 64
    )
    state = "visual/phone/study/graphs"
    relative = ".tum-mcp/visuals/graphs-phone.png"
    image = project / relative
    image.parent.mkdir()
    image.touch()
    with pytest.raises(CampusError, match="missing or invalid contact sheets"):
        save_receipt(project, identity, {state: True}, captures={state: (relative,)})
    Image.new("RGB", (2, 2), "white").save(image)
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


def test_a_rebuild_keeps_passing_checks_of_unchanged_items_only(project: Path) -> None:
    import json

    from tum_mcp.course.app.browser_evidence import (
        BrowserBuild,
        build_files,
        reusable,
        save_receipt,
    )

    build(project, publish=False)
    before = BrowserBuild(
        build=build_files(project)[0],
        shell="3" * 64,
        managed=True,
        browser="1" * 64,
        checks="2" * 64,
    )
    sheets = {}
    for item in ("a", "b"):
        sheets[item] = f".tum-mcp/visuals/{item}.png"
        (project / sheets[item]).parent.mkdir(exist_ok=True)
        Image.new("RGB", (2, 2), "white").save(project / sheets[item])
    keys = {item: f"visual/desktop/study/{item}" for item in ("a", "b")}
    save_receipt(
        project,
        before,
        {keys["a"]: True, keys["b"]: True},
        captures={keys[item]: (sheets[item],) for item in keys},
        revisions={keys["a"]: "a1", keys["b"]: "b1"},
    )
    unit = next((project / "app/study/units").glob("*.json"))
    data = json.loads(unit.read_text(encoding="utf-8"))
    unit.write_text(json.dumps(data | {"title": data["title"] + " (edited)"}), encoding="utf-8")
    build(project, publish=False)
    after = before.model_copy(update={"build": build_files(project)[0]})
    assert after.build != before.build
    assert {
        key: entry.captures
        for key, entry in reusable(project, after, {keys["a"]: "a1", keys["b"]: "b2"}).items()
    } == {keys["a"]: (sheets["a"],)}
    renderer = after.model_copy(update={"shell": "4" * 64})
    assert reusable(project, renderer, {keys["a"]: "a1"}) == {}

    save_receipt(project, after, {keys["b"]: False}, revisions={keys["b"]: "b1"})
    assert {
        key: entry.captures
        for key, entry in reusable(project, after, {keys["a"]: "a1", keys["b"]: "b1"}).items()
    } == {keys["a"]: (sheets["a"],)}
