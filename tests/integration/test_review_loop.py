import json
import re
import shlex
import sys
from importlib.resources import files
from pathlib import Path

import pytest
from documents import content_file
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.browser_evidence import BrowserBuild, build_files, save_receipt
from tum_mcp.course.review import loop, registry
from tum_mcp.course.review.models import CRITERIA
from tum_mcp.errors import CampusError

RULED = "The situation is one plain fact the prompt states."


def packets(project: Path, opened: dict) -> list[dict]:
    return [
        json.loads((project / entry["path"]).read_text(encoding="utf-8"))
        for entry in opened["packets"]
    ]


def answer(packet: dict, fail: dict[str, str] | None = None, covers: dict | None = None) -> dict:
    """A synthetic checker: it quotes each item's first passage for every verdict."""
    items = []
    for entry in packet["items"]:
        first = next(
            (
                p
                for p in entry["passages"]
                if re.fullmatch(r"blocks\[\d+\]\.paragraphs\[0\]", p["path"])
            ),
            entry["passages"][0],
        )
        quote, location = first["text"][:40], first["path"]
        checks, findings = {}, []
        for check in entry["needs"]:
            if (fail or {}).get(entry["item"]) == check:
                checks[check] = {"verdict": "fail", "method": "read"}
                findings.append(
                    {
                        "check": check,
                        "quote": quote,
                        "location": location,
                        "why": "Synthetic defect.",
                        "fix": "Rewrite the passage.",
                    }
                )
                continue
            checks[check] = {
                "verdict": "pass",
                "method": "read",
                "quote": quote,
                "location": location,
                "reason": "The closest call still passes.",
                "evidence": "Synthetic script output.",
            } | (
                {"covers": covers[entry["item"]][check]}
                if covers and check in covers.get(entry["item"], {})
                else {}
            )
        items.append(
            {
                "item": entry["item"],
                "checks": checks,
                "findings": findings,
                "verify": [
                    {
                        "finding": f["id"],
                        "resolved": True,
                        "reason": "Changed.",
                        "quote": next(
                            p["text"][:40] for p in entry["passages"] if p["path"] == f["location"]
                        ),
                    }
                    for f in entry["verify"]
                ],
                "flags": [
                    {"key": flag["key"], "ruling": "not_applicable", "reason": RULED}
                    for flag in entry["report"]
                    if flag.get("needs_ruling")
                ],
                "visuals": [
                    {"visual": key, "scores": dict.fromkeys(CRITERIA, 3)}
                    for key in entry["visuals"]
                ],
            }
        )
    return {"packet": packet["id"], "items": items}


def check_all(project: Path, **options) -> list[dict]:
    opened = loop.next_round(project)
    sent = packets(project, opened)
    for packet in sent:
        loop.record(project, answer(packet, **options), "fresh")
    return sent


def edit_first_block(project: Path) -> str:
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    unit = document["units"][0]
    block = unit["blocks"][0]
    block["paragraphs"] = [block["paragraphs"][0] + " Each step names its reason."]
    path.write_text(json.dumps(document))
    return f"study/{unit['key']}"


@pytest.mark.parametrize("evidence", ["current", "stale-draft", "missing-phone"])
def test_visual_packet_links_the_current_captures(project: Path, evidence: str) -> None:
    key = next(key for key, visuals in loop.load(project).visuals.items() if visuals)
    build, managed = build_files(project)
    identity = BrowserBuild(build=build, checks="a" * 64, browser="b" * 64, managed=managed)
    directory = project / ".tum-mcp/visuals"
    directory.mkdir()
    sheets = {}
    for width in ("phone", "desktop"):
        sheet = directory / f"{width}.png"
        sheet.touch()
        sheets[f"visual/{width}/{key}"] = (sheet.relative_to(project).as_posix(),)
    save_receipt(project, identity, dict.fromkeys(sheets, True), captures=sheets)
    if evidence == "stale-draft":
        edit_first_block(project)
    if evidence == "missing-phone":
        (directory / "phone.png").unlink()

    loop.start(project, workspaces=("study",))
    sent = packets(project, loop.next_round(project))

    entry = next(e for packet in sent for e in packet["items"] if e["item"] == key)
    assert entry["visuals"]
    expected = {
        state.split("/")[1]: list(paths)
        for state, paths in sheets.items()
        if (project / paths[0]).is_file()
    }
    assert entry.get("visual_sheets", {}) == ({} if evidence == "stale-draft" else expected)


def test_reordering_named_blocks_invalidates_an_open_packet(project: Path) -> None:
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    blocks = document["units"][0]["blocks"]
    for index in (0, 1):
        blocks[index].setdefault("key", f"block-{index}")
    path.write_text(json.dumps(document))
    loop.start(project, workspaces=("study",))
    packet = next(
        p for p in packets(project, loop.next_round(project)) if p["profile"] == "study-unit"
    )
    response = answer(packet)
    for entry, reply in zip(packet["items"], response["items"], strict=True):
        unchanged = next(p for p in entry["passages"] if p["path"] == "title")
        for check in reply["checks"].values():
            check.update(quote=unchanged["text"], location=unchanged["path"])
    blocks[0], blocks[1] = blocks[1], blocks[0]
    path.write_text(json.dumps(document))
    with pytest.raises(CampusError, match="content changed since the packet"):
        loop.record(project, response, "fresh")


def test_every_v1_check_is_kept_merged_or_retired_with_a_reason() -> None:
    data = registry.registry()
    active = set(registry.checks())
    replaced = {old for entry in data["checks"] for old in entry.get("replaces", [])}
    retired = {entry["id"] for entry in data["retired"] if entry["reason"]}
    assert set(data["v1_checks"]) <= active | replaced | retired
    for check in registry.checks().values():
        assert check.passing and check.failing and check.rule
        assert set(check.profiles) <= set(registry.PROFILES)
    teaching = {check.id for check in registry.checks().values() if check.teaching}
    assert {"representation.process_shown", "intuition.reasons"} <= teaching


def test_round_one_asks_everything_and_later_rounds_only_what_changed(project: Path) -> None:
    # Given a loop over the built course, with one block-scoped verdict pinned to a block
    # the coming edit does not touch.
    loop.start(project, budget=5)
    first = loop.next_round(project)
    sent = packets(project, first)
    for packet in sent:
        guide = "course.md" if packet["profile"] == "course" else "profiles.md"
        assert packet["guidance"] == files("tum_mcp.bundled").joinpath(
            f"skills/review-course/references/{guide}"
        ).read_text(encoding="utf-8")
    example = sent[0]["answer"]["items"][0]["visuals"][0]
    weak_visual = {**example, "scores": {**example["scores"], "legibility": 2}}
    assert loop.VisualReview.model_validate(weak_visual).note
    unit_entry = next(e for p in sent for e in p["items"] if e["item"].startswith("study/"))
    untouched = [b for b in unit_entry["blocks"] if b.startswith("blocks:")][-1]
    for packet in sent:
        loop.record(
            project,
            answer(packet, covers={unit_entry["item"]: {"correctness.source_match": [untouched]}}),
            "fresh",
        )
    loop.close_round(project)
    # When one paragraph of the first unit changes and a later loop starts.
    key = edit_first_block(project)
    loop.start(project, budget=5)
    second = packets(project, loop.next_round(project))
    # Then only that unit is asked again, its item-wide checks but not the pinned one.
    asked = {entry["item"]: entry for packet in second for entry in packet["items"]}
    assert set(asked) == {key}
    assert "clarity.one_reading" in asked[key]["needs"]
    if key == unit_entry["item"]:
        assert "correctness.source_match" not in asked[key]["needs"]


def test_a_fix_is_refused_until_its_passage_changes_and_is_then_verified(project: Path) -> None:
    loop.start(project, budget=5)
    opened = packets(project, loop.next_round(project))
    unit = next(e["item"] for p in opened for e in p["items"] if e["item"].startswith("study/"))
    for packet in opened:
        loop.record(project, answer(packet, fail={unit: "clarity.one_reading"}), "fresh")
    record = loop.load(project).record(unit)
    finding = record.findings[0]
    assert finding.status == "open"
    assert "clarity.one_reading" in " ".join(loop.item_gate(loop.load(project), unit))
    with pytest.raises(CampusError, match="unchanged"):
        loop.change(project, unit, finding.id, "fixed")
    loop.close_round(project)
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    target = next(u for u in document["units"] if f"study/{u['key']}" == unit)
    head = finding.location.split(".", 1)[0]
    field, index = head.split("[")[0], int(head.split("[")[1].rstrip("]"))
    entry = target[field][index]
    entry["paragraphs"] = [entry["paragraphs"][0] + " A clearer reading."]
    path.write_text(json.dumps(document))
    loop.change(project, unit, finding.id, "fixed")
    # A fix made after the item's last check waits for the next round to verify it.
    assert loop.status(project)["fixes_to_verify"] == 1
    second = packets(project, loop.next_round(project))
    verify = [f["id"] for p in second for e in p["items"] if e["item"] == unit for f in e["verify"]]
    assert verify == [finding.id]
    sent = next(f for p in second for e in p["items"] for f in e["verify"] if f["id"] == finding.id)
    assert "blocks_at_open" not in sent
    assert sent["quote"] == finding.quote and sent["fix"] == finding.fix
    assert loop.load(project).record(unit).findings[0].blocks_at_open == finding.blocks_at_open
    for packet in second:
        loop.record(project, answer(packet), "fresh")
    assert loop.load(project).record(unit).findings[0].status == "verified"


@pytest.mark.parametrize("damage", ["quote", "missing", "evidence", "unbacked_fail"])
def test_answers_that_skip_evidence_are_refused(project: Path, damage: str) -> None:
    loop.start(project, budget=5)
    packet = packets(project, loop.next_round(project))[0]
    answers = answer(packet)
    item = answers["items"][0]
    default_fail = next(check for check in item["checks"] if registry.checks()[check].default_fail)
    match damage:
        case "quote":
            item["checks"]["clarity.one_reading"]["quote"] = "A sentence the item never says."
        case "missing":
            del item["checks"]["clarity.one_reading"]
        case "evidence":
            item["checks"][default_fail].pop("evidence")
        case "unbacked_fail":
            item["checks"]["clarity.one_reading"] = {"verdict": "fail"}
    with pytest.raises(CampusError, match="Answers need fixing"):
        loop.record(project, answers, "fresh")


def test_recording_an_answered_packet_again_cannot_duplicate_findings(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    response = answer(packet, fail={key: "clarity.one_reading"})
    loop.record(project, response, "fresh")
    before = loop.load(project).record(key)
    state = loop.read_state(project)
    assert len(before.findings) == 1

    repeated = loop.record(project, response, "fresh")

    assert repeated["opened"] == 0
    assert loop.load(project).record(key) == before
    assert loop.read_state(project) == state
    response["items"][0]["findings"][0]["why"] = "A distinct defect in the same passage."
    assert loop.record(project, response, "fresh")["opened"] == 1
    assert len(loop.load(project).record(key).findings) == 2


def test_the_gate_wants_fresh_checkers_for_correctness(project: Path) -> None:
    loop.start(project, budget=5)
    for packet in packets(project, loop.next_round(project)):
        loop.record(project, answer(packet), "same")
    context = loop.load(project)
    unit = next(key for key in context.items if key.startswith("study/"))
    assert any("needs a fresh checker" in p for p in loop.item_gate(context, unit))
    # Sources no requirement records yet hold the course, not the item filed with them.
    flag = {"item": unit, "flag": "unrecorded_sources", "detail": "3 sources unread."}
    context.flags_by_item.setdefault(unit, []).append(flag)
    held = loop.gate(context, (unit,))
    assert held["course"] == ["flag unrecorded_sources: 3 sources unread."]
    assert not any("unrecorded_sources" in problem for problem in held[unit])


def test_cli_uses_one_round_unless_a_budget_is_requested(project: Path) -> None:
    runner = CliRunner()
    assert json.loads(runner.invoke(app, ["review", "start", str(project)]).output)["budget"] == 1
    result = runner.invoke(app, ["review", "start", str(project), "--rounds", "3"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["budget"] == 3


def test_closing_with_unanswered_packets_requires_an_explicit_choice(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    opened = loop.next_round(project)
    pending = [packet["packet"] for packet in opened["packets"]]
    runner = CliRunner()
    args = ["review", "close-round", str(project)]

    attempt = runner.invoke(app, args)

    assert attempt.exit_code != 0
    assert all(packet in str(attempt.exception) for packet in pending)
    status = loop.status(project)
    assert status["pending_packets"] == pending and status["open_round"]
    explicit = runner.invoke(app, [*args, "--incomplete"])
    assert explicit.exit_code == 0, explicit.output
    card = json.loads(explicit.output)
    assert card["status"] == "budget_spent" and not card["gate"]
    assert card["rounds"][0]["answered_packets"] == 0
    assert card["averages"] == {} and all(row["scores"] == {} for row in card["items"])
    assert card["score_coverage"] == {"scored_items": 0, "in_scope_items": 5, "complete": False}
    markdown = (project / ".tum-mcp/loop/scorecard.md").read_text(encoding="utf-8")
    assert "all 3" not in markdown and "unreviewed" in markdown


def test_incomplete_checker_answers_report_the_entire_missing_verdict_set(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    response = answer(packet)
    for item in response["items"]:
        item["checks"] = {}
    with pytest.raises(CampusError) as refused:
        loop.record(project, response, "fresh")
    required = {check for item in packet["items"] for check in item["needs"]}
    assert len(required) > 20
    assert all(check in refused.value.message for check in required)


def test_a_spent_budget_stops_and_extending_continues(project: Path) -> None:
    assert loop.start(project).budget == 1
    check_all(project, fail={})
    edit_first_block(project)
    card = loop.close_round(project)
    assert card["status"] == "budget_spent" and not card["gate"]
    with pytest.raises(CampusError):
        loop.next_round(project)
    loop.extend(project, 1)
    assert loop.status(project)["status"] == "running"
    assert (
        (project / ".tum-mcp/loop/scorecard.md")
        .read_text(encoding="utf-8")
        .startswith("# Review scorecard")
    )


def test_a_headless_checker_is_recorded_as_fresh(project: Path, tmp_path: Path) -> None:
    loop.start(project, budget=5)
    opened = loop.next_round(project)
    packet_id = opened["packets"][0]["packet"]
    script = tmp_path / "fresh checker.py"
    script.write_text(
        "import json, re, sys\n"
        f"sys.path[:0] = [{str(Path(__file__).parent)!r}, {str(Path(__file__).parents[1])!r}]\n"
        "from test_review_loop import answer\n"
        "path = re.search(r'at (\\S+\\.json)', sys.argv[1]).group(1)\n"
        "print(json.dumps(answer(json.load(open(path, encoding='utf-8')))))\n"
    )
    result = CliRunner().invoke(
        app,
        [
            "review",
            "run-checker",
            str(project),
            "--packet",
            packet_id,
            "--command",
            shlex.join([sys.executable, str(script), "{prompt}"]),
        ],
    )
    assert result.exit_code == 0, result.output
    context = loop.load(project)
    recorded = json.loads(result.output)["recorded"]
    verdicts = context.record(recorded[0]).checks.values()
    assert verdicts and {verdict.provenance for verdict in verdicts} == {"fresh"}
    saved = json.loads((project / f".tum-mcp/review/packets/{packet_id}.answer.json").read_bytes())
    assert saved["packet"] == packet_id
    assert {item["item"] for item in saved["items"]} == set(recorded)


def test_duplicate_checker_waits_for_the_existing_packet_run(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from tum_mcp.course.review import runner

    loop.start(project)
    packet = packets(project, loop.next_round(project))[0]
    started, release = Event(), Event()
    calls = []

    def check(*args) -> dict:
        calls.append(args)
        started.set()
        assert release.wait(timeout=10)
        return answer(packet)

    monkeypatch.setattr(runner, "_ask", check)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(runner.run, project, packet["id"], "codex")
        try:
            assert started.wait(timeout=5)
            with pytest.raises(CampusError, match="already being checked"):
                runner.run(project, packet["id"], "codex")
        finally:
            release.set()
        assert first.result(timeout=5)["recorded"]
    assert len(calls) == 1


def test_advisory_flags_hold_the_gate_until_a_fresh_checker_rules(project: Path) -> None:
    # Given a situation question with text only, which the pilot's checkers passed in silence.
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    unit = document["units"][0]
    question = unit["questions"][0]
    question.update(level="apply", blocks=[])
    path.write_text(json.dumps(document))
    key = f"study/{unit['key']}"
    loop.start(project, budget=5)
    sent = packets(project, loop.next_round(project))
    entry = next(e for p in sent for e in p["items"] if e["item"] == key)
    flag = next(f for f in entry["report"] if f["flag"] == "text_only_question")
    assert flag["needs_ruling"] and flag["key"] in entry["rule"]
    # An answer that passes every check but says nothing about the flag is refused.
    packet = next(p for p in sent if any(e["item"] == key for e in p["items"]))
    silent = answer(packet)
    for item in silent["items"]:
        item["flags"] = []
    with pytest.raises(CampusError, match="needs a ruling"):
        loop.record(project, silent, "fresh")
    # An unrelated finding cannot stand in for addressing the reported defect.
    unrelated = answer(packet, fail={key: "clarity.terms_defined"})
    entry = next(item for item in unrelated["items"] if item["item"] == key)
    entry["flags"][0]["ruling"] = "finding"
    with pytest.raises(CampusError, match="no finding names representation.picture_carries_data"):
        loop.record(project, unrelated, "fresh")
    # The author's own ruling stays provisional; a fresh checker records an advisory ruling.
    loop.record(project, answer(packet), "same")
    assert any("needs a fresh checker" in p for p in loop.item_gate(loop.load(project), key))
    loop.record(project, answer(packet), "fresh")
    context = loop.load(project)
    assert context.record(key).rulings[flag["key"]].reason == RULED
    assert not any(flag["key"] in p for p in loop.item_gate(context, key))
    # Missing question context is a defect even when a fresh checker waives its flag.
    assert any("flag text_only_question:" in p for p in loop.item_gate(context, key))


def test_the_concept_check_is_answered_for_every_planned_concept(project: Path) -> None:
    path = content_file(project, "study")
    unit = json.loads(path.read_bytes())["units"][0]
    key = f"study/{unit['key']}"
    block = "the first trace"
    plan = {
        "item": key,
        "concepts": [
            {"name": name, "kind": "rule", "instance": "One case."}
            for name in ("Frontier order", "Goal test")
        ],
    }
    target = project / ".tum-mcp/plans" / f"{key}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan))
    loop.start(project, budget=5)
    packet = next(
        p
        for p in packets(project, loop.next_round(project))
        if any(e["item"] == key for e in p["items"])
    )
    entry = next(e for e in packet["items"] if e["item"] == key)
    assert [c["name"] for c in entry["concepts"]] == ["Frontier order", "Goal test"]
    answers = answer(packet)
    concept = next(i for i in answers["items"] if i["item"] == key)["checks"]
    concept["intuition.concepts_instanced"]["evidence"] = f"Frontier order: block {block}."
    with pytest.raises(CampusError, match="missing Goal test"):
        loop.record(project, answers, "fresh")
    concept["intuition.concepts_instanced"]["evidence"] += f" Goal test: block {block}."
    loop.record(project, answers, "fresh")


@pytest.mark.parametrize("repair_valid", [True, False])
def test_a_refused_checker_answer_gets_one_repair_pass(
    project: Path, tmp_path: Path, repair_valid: bool
) -> None:
    # A checker's whole review was lost twice to one malformed visual score.
    loop.start(project, budget=5)
    packet_id = loop.next_round(project)["packets"][0]["packet"]
    script = tmp_path / "fresh checker.py"
    script.write_text(
        "import json, re, sys\n"
        f"sys.path[:0] = [{str(Path(__file__).parent)!r}, {str(Path(__file__).parents[1])!r}]\n"
        "from test_review_loop import answer\n"
        "prompt = sys.argv[1]\n"
        "packet = json.load(open(re.search(r'packet at (\\S+\\.json)', prompt).group(1), "
        "encoding='utf-8'))\n"
        "result = answer(packet)\n"
        "if 'were refused' not in prompt:\n"
        "    result['items'][0]['checks'].pop(next(iter(result['items'][0]['checks'])))\n"
        f"elif {not repair_valid!r}:\n"
        "    result['items'][0]['checks'].pop(list(result['items'][0]['checks'])[-1])\n"
        "print(json.dumps(result))\n"
    )
    result = CliRunner().invoke(
        app,
        [
            "review",
            "run-checker",
            str(project),
            "--packet",
            packet_id,
            "--command",
            shlex.join([sys.executable, str(script), "{prompt}"]),
        ],
    )
    if repair_valid:
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["recorded"]
    else:
        assert result.exit_code != 0
    folder = project / ".tum-mcp/review/packets"
    sent = json.loads((folder / f"{packet_id}.json").read_bytes())
    saved = json.loads((folder / f"{packet_id}.answer.json").read_bytes())
    expected = sent["items"][0]["needs"]
    assert set(saved["items"][0]["checks"]) == set(expected if repair_valid else expected[:-1])


def test_partial_current_verdicts_do_not_look_like_a_complete_perfect_score(project: Path) -> None:
    loop.start(project, workspaces=("study", "course"))
    check_all(project, fail={})
    edit_first_block(project)
    context = loop.load(project)
    card = loop.scorecard(context, loop.read_state(project))
    study = next(row for row in card["items"] if row["item"] == "study/graphs")
    assert study["scores"] == {}
    assert not card["score_coverage"]["complete"]
    assert card["score_coverage"]["scored_items"] < card["score_coverage"]["in_scope_items"]
