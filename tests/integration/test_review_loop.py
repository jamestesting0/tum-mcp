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


@pytest.fixture(autouse=True)
def one_packet_per_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the fixture lesson in one packet; batching tests set their own smaller bound."""
    monkeypatch.setattr(loop, "PACKET_VERDICTS", 100)


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


@pytest.mark.parametrize("separate_findings", [False, True])
def test_one_defect_can_fail_four_checks_without_multiple_scores(
    project: Path, separate_findings: bool
) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    response = answer(packet)
    item = response["items"][0]
    checks = (
        "clarity.one_reading",
        "cohesion.linked",
        "intuition.reasons",
        "representation.shape_fits",
    )
    for check in checks:
        item["checks"][check] = {"verdict": "fail", "method": "read"}
    passage = packet["items"][0]["passages"][0]
    finding = {
        "check": checks[0],
        "location": passage["path"],
        "quote": passage["text"],
        "why": "The student encounters an unclear step.",
        "fix": "Explain the step.",
        "score": 2,
    }
    if separate_findings:
        item["findings"] = [
            finding,
            *[
                finding | {"check": check, "why": f"Another description {index}.", "score": 1}
                for index, check in enumerate(checks[1:], 1)
            ],
        ]
    else:
        item["findings"] = [finding | {"also": list(checks[1:])}]

    result = loop.record(project, response, "fresh")

    record = loop.load(project).record(item["item"])
    assert result["opened"] == 1
    assert len(record.findings) == 1
    stored = record.findings[0]
    assert stored.check == checks[0] and stored.also == checks[1:]
    assert stored.why == finding["why"] and stored.fix == finding["fix"]
    assert stored.score == (1 if separate_findings else 2)
    scores = record.scores(registry.dimensions("study-unit"))
    assert scores["clarity"] == stored.score
    assert {scores[name] for name in ("cohesion", "intuition", "representation")} == {3}
    assert all(record.checks[check].verdict == "fail" for check in checks)
    assert all(record.checks[check].finding_ids == (stored.id,) for check in checks)
    assert loop.record(project, response, "fresh")["opened"] == 0
    assert loop.load(project).record(item["item"]) == record


@pytest.mark.parametrize(
    "linked", [["clarity.one_reading"], ["clarity.case_observable"], ["cohesion.linked"]]
)
def test_finding_keeps_owner_and_drops_invalid_linked_check(
    project: Path, linked: list[str]
) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    response = answer(packet, fail={key: "clarity.one_reading"})
    response["items"][0]["findings"][0]["also"] = linked

    loop.record(project, response, "fresh")

    findings = loop.load(project).record(key).findings
    assert [(f.check, f.also) for f in findings] == [("clarity.one_reading", ())]


def test_finding_refuses_malformed_also(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    response = answer(packet, fail={key: "clarity.one_reading"})
    response["items"][0]["findings"][0]["also"] = "clarity.case_observable"

    with pytest.raises(CampusError, match="also"):
        loop.record(project, response, "fresh")

    assert not loop.load(project).record(key).findings


def test_also_drops_current_profile_check_not_asked_in_packet(project: Path) -> None:
    from tum_mcp.course.review.ledger import read_record

    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    entry = original[0]["items"][0]
    key = entry["item"]
    current = "correctness.source_match"
    unchanged = [block for block in entry["blocks"] if block.startswith("blocks:")][-1]
    for packet in original:
        loop.record(project, answer(packet, covers={key: {current: [unchanged]}}), "fresh")
    edit_first_block(project)
    packet = next(
        p
        for p in packets(project, loop.verify_round(project))
        if any(item["item"] == key for item in p["items"])
    )
    entry = next(item for item in packet["items"] if item["item"] == key)
    assert current not in entry["needs"]
    response = answer(packet, fail={key: "clarity.one_reading"})
    next(item for item in response["items"] if item["item"] == key)["findings"][0]["also"] = [
        current
    ]

    loop.record(project, response, "fresh")

    stored = read_record(project, key).findings[-1]
    assert stored.check == "clarity.one_reading" and stored.also == ()


def test_old_review_record_without_also_still_loads(project: Path) -> None:
    from tum_mcp.course.review.ledger import read_record

    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    loop.record(project, answer(packet, fail={key: "clarity.one_reading"}), "fresh")
    path = project / f".tum-mcp/review/items/{key}.json"
    stored = json.loads(path.read_bytes())
    stored["findings"][0].pop("also", None)
    path.write_text(json.dumps(stored))

    assert read_record(project, key).findings[0].also == ()


def test_findings_with_different_quotes_are_not_merged(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    response = answer(packet, fail={key: "clarity.one_reading"})
    original = response["items"][0]["findings"][0]
    other = next(
        passage
        for passage in packet["items"][0]["passages"]
        if passage["path"] == original["location"]
    )
    assert len(other["text"]) > len(original["quote"])
    response["items"][0]["findings"].append(original | {"quote": other["text"]})

    assert loop.record(project, response, "fresh")["opened"] == 2
    assert len(loop.load(project).record(key).findings) == 2


def test_verifying_owner_clears_linked_teaching_failures(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    key = original[0]["items"][0]["item"]
    owner, linked = "clarity.one_reading", "intuition.reasons"
    for packet in original:
        response = answer(packet, fail={key: owner})
        if packet is original[0]:
            item = response["items"][0]
            item["checks"][linked] = {"verdict": "fail", "method": "read"}
            item["findings"][0]["also"] = [linked]
        loop.record(project, response, "fresh")
    finding = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    loop.change(project, key, finding.id, "fixed")
    verify = packets(project, loop.verify_round(project))
    for packet in verify:
        loop.record(project, answer(packet), "fresh")
    context = loop.load(project)
    record = context.record(key)
    assert record.findings[0].status == "verified"
    assert record.findings[0].verified_provenance == "fresh"
    # A current failing teaching verdict linked only to this verified finding has no open defect.
    checks = dict(record.checks)
    checks[linked] = checks[linked].model_copy(
        update={"verdict": "fail", "finding_ids": (finding.id,)}
    )
    context.records[key] = record.model_copy(update={"checks": checks})

    assert not any(linked in issue for issue in loop.item_gate(context, key))
    old_rejection = record.findings[0].model_copy(
        update={"id": "F2", "status": "rejected", "reason": "The old case was correct."}
    )
    context.records[key] = record.model_copy(
        update={"checks": checks, "findings": (*record.findings, old_rejection)}
    )
    assert not any(linked in issue for issue in loop.item_gate(context, key))
    checks[linked] = checks[linked].model_copy(update={"provenance": "user"})
    context.records[key] = record.model_copy(update={"checks": checks})
    assert any(
        issue == f"{linked}: teaching check not passed" for issue in loop.item_gate(context, key)
    )
    checks[linked] = checks[linked].model_copy(update={"round": 2, "provenance": "fresh"})
    context.records[key] = record.model_copy(update={"checks": checks})
    assert any(
        issue == f"{linked}: teaching check not passed" for issue in loop.item_gate(context, key)
    )


def test_linked_failure_still_blocks_if_another_finding_is_open(project: Path) -> None:
    from tum_mcp.course.review.ledger import Finding, Verdict

    context = loop.load(project)
    key = next(key for key in context.items if key.startswith("study/"))
    item = context.items[key]
    linked = "intuition.reasons"
    check = registry.checks()[linked]
    verdict = Verdict(
        verdict="fail",
        method="read",
        round=1,
        provenance="fresh",
        fingerprint=loop.covered(item, ("*",), linked),
        version=check.version,
        finding_ids=("F1", "F2"),
    )
    resolved = Finding(
        id="F1",
        check="clarity.one_reading",
        also=(linked,),
        quote="One sentence.",
        location="title",
        why="A defect.",
        fix="Fix it.",
        status="verified",
        opened=1,
        closed=1,
        verified_provenance="fresh",
        block="title",
    )
    active = resolved.model_copy(update={"id": "F2", "status": "open", "closed": None})
    record = context.record(key)
    context.records[key] = record.model_copy(
        update={"checks": {**record.checks, linked: verdict}, "findings": (resolved, active)}
    )

    assert any(
        issue == f"{linked}: teaching check not passed" for issue in loop.item_gate(context, key)
    )


def test_provisional_verification_does_not_clear_a_teaching_failure(project: Path) -> None:
    from tum_mcp.course.review.ledger import Finding, Verdict

    context = loop.load(project)
    key = next(key for key in context.items if key.startswith("study/"))
    item = context.items[key]
    linked = "intuition.reasons"
    check = registry.checks()[linked]
    verdict = Verdict(
        verdict="fail",
        method="read",
        round=1,
        provenance="fresh",
        fingerprint=loop.covered(item, ("*",), linked),
        version=check.version,
        finding_ids=("F1",),
    )
    finding = Finding(
        id="F1",
        check="clarity.one_reading",
        also=(linked,),
        quote="One sentence.",
        location="title",
        why="A defect.",
        fix="Fix it.",
        status="verified",
        opened=1,
        closed=1,
        verified_provenance="same",
        block="title",
    )
    record = context.record(key)
    context.records[key] = record.model_copy(
        update={"checks": {**record.checks, linked: verdict}, "findings": (finding,)}
    )

    assert any(
        issue == f"{linked}: teaching check not passed" for issue in loop.item_gate(context, key)
    )


def test_flag_ruling_accepts_a_linked_finding(project: Path) -> None:
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    unit = document["units"][0]
    unit["questions"][0].update(level="apply", blocks=[])
    path.write_text(json.dumps(document))
    key = f"study/{unit['key']}"
    loop.start(project, workspaces=("study",))
    packet = next(
        p
        for p in packets(project, loop.next_round(project))
        if any(entry["item"] == key for entry in p["items"])
    )
    response = answer(packet, fail={key: "clarity.one_reading"})
    item = next(entry for entry in response["items"] if entry["item"] == key)
    linked = "representation.picture_carries_data"
    item["checks"][linked] = {"verdict": "fail", "method": "read"}
    item["findings"][0]["also"] = [linked]
    flag = next(entry for entry in item["flags"] if entry["key"].startswith("text_only_question@"))
    flag["ruling"] = "finding"

    loop.record(project, response, "fresh")

    record = loop.load(project).record(key)
    assert record.rulings[flag["key"]].ruling == "finding"
    assert record.findings[0].also == (linked,)


def test_new_failed_verdict_cannot_be_resolved_by_the_same_finding(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    key = original[0]["items"][0]["item"]
    owner, linked = "clarity.one_reading", "intuition.reasons"
    for packet in original:
        response = answer(packet, fail={key: owner})
        if packet is original[0]:
            response["items"][0]["checks"][linked] = {"verdict": "fail", "method": "read"}
            response["items"][0]["findings"][0]["also"] = [linked]
        loop.record(project, response, "fresh")
    finding = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    loop.change(project, key, finding.id, "fixed")
    packet = next(
        p
        for p in packets(project, loop.verify_round(project))
        if any(entry["item"] == key for entry in p["items"])
    )
    response = answer(packet)
    item = next(entry for entry in response["items"] if entry["item"] == key)
    item["checks"][linked] = {"verdict": "fail", "method": "read"}
    item["findings"].append(
        {
            "check": owner,
            "also": [linked],
            "location": finding.location,
            "quote": finding.quote,
            "why": finding.why,
            "fix": finding.fix,
            "score": finding.score,
        }
    )

    with pytest.raises(CampusError, match="cannot be resolved while its checks fail"):
        loop.record(project, response, "fresh")

    assert loop.load(project).record(key).findings[0].status == "fixed"


def test_new_loop_does_not_reuse_an_old_verified_finding(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    key = original[0]["items"][0]["item"]
    owner, linked = "clarity.one_reading", "intuition.reasons"
    for packet in original:
        response = answer(packet, fail={key: owner})
        if packet is original[0]:
            response["items"][0]["checks"][linked] = {"verdict": "fail", "method": "read"}
            response["items"][0]["findings"][0]["also"] = [linked]
        loop.record(project, response, "fresh")
    finding = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    loop.change(project, key, finding.id, "fixed")
    for packet in packets(project, loop.verify_round(project)):
        loop.record(project, answer(packet), "fresh")
    loop.close_round(project)
    edit_first_block(project)
    loop.start(project, workspaces=("study",))
    packet = next(
        p
        for p in packets(project, loop.next_round(project))
        if any(entry["item"] == key for entry in p["items"])
    )
    response = answer(packet, fail={key: owner})
    item = next(entry for entry in response["items"] if entry["item"] == key)
    item["checks"][linked] = {"verdict": "fail", "method": "read"}
    item["findings"][0]["also"] = [linked]

    result = loop.record(project, response, "fresh")

    assert result["opened"] == 1
    record = loop.load(project).record(key)
    assert [f.status for f in record.findings] == ["verified", "open"]
    assert any(linked in issue for issue in loop.item_gate(loop.load(project), key))


def test_same_round_verify_waits_for_packets_and_rechecks_repairs(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    key = original[0]["items"][0]["item"]
    with pytest.raises(CampusError, match="Record all original packets"):
        loop.verify_round(project)
    for packet in original:
        loop.record(project, answer(packet, fail={key: "clarity.one_reading"}), "fresh")
    finding = loop.load(project).record(key).findings[0]
    assert edit_first_block(project) == key
    loop.change(project, key, finding.id, "fixed")

    verification = packets(project, loop.verify_round(project))

    assert all(packet["id"].startswith("r1v-") for packet in verification)
    entry = next(e for p in verification for e in p["items"] if e["item"] == key)
    assert [f["id"] for f in entry["verify"]] == [finding.id]
    assert "clarity.one_reading" in entry["needs"]
    assert entry["changed"]
    with pytest.raises(CampusError, match="unanswered packets"):
        loop.close_round(project)
    with pytest.raises(CampusError, match="Record all.*packets"):
        loop.verify_round(project)
    for packet in verification:
        loop.record(project, answer(packet), "fresh")
    assert loop.load(project).record(key).findings[0].status == "verified"
    assert loop.read_state(project).round == 1


def test_second_verify_scopes_all_stale_tasks_to_changed_items(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    document["units"][0]["questions"][0].update(level="apply", blocks=[])
    path.write_text(json.dumps(document))
    loop.start(project, workspaces=("study",))
    check_all(project)
    key = edit_first_block(project)
    first = packets(project, loop.verify_round(project))
    for packet in first:
        loop.record(project, answer(packet, fail={key: "clarity.one_reading"}), "fresh")
    finding = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    loop.change(project, key, finding.id, "fixed")
    expected = loop.item_tasks(loop.load(project), key)
    assert all(expected[task] for task in ("needs", "visuals", "verify", "rule"))
    monkeypatch.setattr(loop, "PACKET_VERDICTS", 8)

    second = packets(project, loop.verify_round(project))

    assert {e["item"] for p in second for e in p["items"]} == {key}
    assert {p["id"] for p in first}.isdisjoint(p["id"] for p in second)
    for task in ("needs", "visuals", "rule"):
        assert [v for p in second for e in p["items"] for v in e[task]] == expected[task]
    assert [f["id"] for p in second for e in p["items"] for f in e["verify"]] == [finding.id]
    for packet in second:
        loop.record(project, answer(packet), "fresh")
    assert loop.load(project).record(key).findings[0].status == "verified"
    assert loop.read_state(project).round == 1
    with pytest.raises(CampusError, match="student.*another round"):
        loop.verify_round(project)


def test_second_verify_does_not_retry_unchanged_uncertainty(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    check_all(project)
    key = edit_first_block(project)
    for packet in packets(project, loop.verify_round(project)):
        response = answer(packet)
        check = next(iter(response["items"][0]["checks"]))
        response["items"][0]["checks"][check].update(
            verdict="uncertain", missing="slides.pdf page 4 cannot be opened: file missing."
        )
        loop.record(project, response, "fresh")

    assert loop.verify_round(project)["packets"] == []
    assert loop.item_tasks(loop.load(project), key)["needs"] == [check]
    with pytest.raises(CampusError, match="student.*another round"):
        loop.verify_round(project)


def test_bulk_fix_validates_all_before_changing_any(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    loop.record(project, answer(packet, fail={key: "clarity.one_reading"}), "fresh")
    finding = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    with pytest.raises(CampusError, match="no finding"):
        loop.fix_many(project, key, (finding.id, "F999"))
    assert loop.load(project).record(key).findings[0].status == "open"


def test_unique_mislocated_finding_quote_is_relocated(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    key = packet["items"][0]["item"]
    response = answer(packet, fail={key: "clarity.one_reading"})
    finding = response["items"][0]["findings"][0]
    original_location = finding["location"]
    finding["location"] = "title"
    loop.record(project, response, "fresh")
    assert loop.load(project).record(key).findings[0].location == original_location


def test_uncertain_verdict_is_asked_again_in_verify_pass(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    key = original[0]["items"][0]["item"]
    check = original[0]["items"][0]["needs"][0]
    for packet in original:
        response = answer(packet)
        if packet is original[0]:
            response["items"][0]["checks"][check]["verdict"] = "uncertain"
            response["items"][0]["checks"][check]["missing"] = (
                "slides/search.pdf page 4: the cached image and PDF cannot be opened."
            )
        loop.record(project, response, "fresh")
    assert loop.load(project).record(key).checks[check].missing == (
        "slides/search.pdf page 4: the cached image and PDF cannot be opened."
    )
    verification = packets(project, loop.verify_round(project))
    entry = next(e for p in verification for e in p["items"] if e["item"] == key)
    assert check in entry["needs"]


def test_close_names_late_fixed_findings_and_stale_items(project: Path) -> None:
    loop.start(project, workspaces=("study",))
    for packet in packets(project, loop.next_round(project)):
        loop.record(project, answer(packet), "fresh")
    key = edit_first_block(project)
    for packet in packets(project, loop.verify_round(project)):
        loop.record(project, answer(packet, fail={key: "clarity.one_reading"}), "fresh")
    finding = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    loop.change(project, key, finding.id, "fixed")

    card = loop.close_round(project)

    assert card["fixed_unverified"] == [
        {
            "item": key,
            "finding": finding.id,
            "check": finding.check,
            "location": finding.location,
            "why": finding.why,
        }
    ]
    assert key in card["stale_items"]
    assert next(row for row in card["items"] if row["item"] == key)["scores"] == {}
    markdown = (project / ".tum-mcp/loop/scorecard.md").read_text()
    assert f"{key} {finding.id}" in markdown
    assert f"Stale or incomplete verdicts: {key}" in markdown


def test_verify_reports_added_and_removed_blocks(project: Path) -> None:
    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    document["units"][0]["blocks"][0]["key"] = "old-block"
    path.write_text(json.dumps(document))
    loop.start(project, workspaces=("study",))
    original = packets(project, loop.next_round(project))
    for packet in original:
        loop.record(project, answer(packet), "fresh")
    document["units"][0]["blocks"][0]["key"] = "new-block"
    path.write_text(json.dumps(document))

    verification = packets(project, loop.verify_round(project))

    key = f"study/{document['units'][0]['key']}"
    changed = next(e["changed"] for p in verification for e in p["items"] if e["item"] == key)
    assert {"blocks:old-block", "blocks:new-block"} <= set(changed)


def test_partial_checker_repair_preserves_other_verdicts_and_logs_problems(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.course.review import runner

    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    complete = answer(packet)
    first = complete["items"][0]
    missing = next(iter(first["checks"]))
    partial = {"items": [{"item": first["item"], "checks": {missing: first["checks"][missing]}}]}
    del first["checks"][missing]
    replies = iter((complete, partial))
    monkeypatch.setattr(runner, "_ask", lambda *args: next(replies))

    runner.run(project, packet["id"], "codex")

    stored = loop.load(project).record(first["item"])
    assert set(stored.checks) == set(packet["items"][0]["needs"])
    history = json.loads(
        (project / f".tum-mcp/review/packets/{packet['id']}.problems.json").read_bytes()
    )
    assert {(p["item"], p["kind"], p["id"]) for p in history[0]} == {
        (first["item"], "check", missing)
    }


@pytest.mark.parametrize(
    "missing",
    [
        None,
        "",
        "not independently verified",
        "did not inspect every cited page",
    ],
)
def test_uncertain_requires_specific_unavailable_evidence(
    project: Path, missing: str | None
) -> None:
    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    response = answer(packet)
    check = next(iter(response["items"][0]["checks"]))
    response["items"][0]["checks"][check].update(verdict="uncertain", missing=missing)
    with pytest.raises(loop.AnswerError, match="likeliest failures pass"):
        loop.record(project, response, "fresh")


@pytest.mark.parametrize("complete_second_repair", [True, False])
def test_checker_uses_two_targeted_repairs_and_saves_valid_remainder(
    project: Path, monkeypatch: pytest.MonkeyPatch, complete_second_repair: bool
) -> None:
    from copy import deepcopy

    from tum_mcp.course.review import runner

    loop.start(project, workspaces=("study",))
    packet = packets(project, loop.next_round(project))[0]
    complete = answer(packet)
    first = complete["items"][0]
    key = first["item"]
    checks = list(first["checks"])[:2]
    initial = deepcopy(complete)
    for check in checks:
        initial["items"][0]["checks"].pop(check)
    repair = {"items": [{"item": key, "checks": {checks[0]: first["checks"][checks[0]]}}]}
    last = (
        {"items": [{"item": key, "checks": {checks[1]: first["checks"][checks[1]]}}]}
        if complete_second_repair
        else {"items": []}
    )
    replies = iter((initial, repair, last))
    prompts = []

    def checker(_root, prompt, _host, _command):
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr(runner, "_ask", checker)
    if complete_second_repair:
        result = runner.run(project, packet["id"], "codex")
        assert not result.get("problems")
    else:
        with pytest.raises(loop.AnswerError) as refused:
            runner.run(project, packet["id"], "codex")

    stored = loop.load(project).record(key)
    expected = set(first["checks"]) - (set() if complete_second_repair else {checks[1]})
    assert set(stored.checks) == expected
    assert len(prompts) == 3
    if not complete_second_repair:
        assert [(p["item"], p["kind"], p["id"]) for p in refused.value.problems] == [
            (key, "check", checks[1])
        ]
        assert packet["id"] in loop.read_state(project).rounds[-1].pending_packets
        assert f"{checks[1]}: no current verdict" in loop.item_gate(loop.load(project), key)


def test_packet_renders_cited_pages_and_supplies_prior_definitions(tmp_path: Path) -> None:
    from material_fixture import material_project, minimal_unit, pdf_bytes

    from tum_mcp.course.project.store import load_state

    project = material_project(
        tmp_path, {"slides": ("content", pdf_bytes([f"Page {i}" for i in range(1, 14)]))}
    )
    state = load_state(project)
    source = state.resources[0].sha256
    first = minimal_unit("first", "slides", source)
    first["blocks"][0] = {
        "kind": "definition",
        "title": "A term",
        "term": "Previous term",
        "statement": "An earlier definition.",
        "sources": ["slides"],
    }
    second = minimal_unit("second", "slides", source)
    second["blocks"][0]["pages"] = "1-14"
    content_file(project, "study").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course_key": state.course.key,
                "organization": "topics",
                "introduction": "Synthetic content.",
                "units": [first, second],
            }
        )
    )
    loop.start(project, workspaces=("study",))

    sent = packets(project, loop.next_round(project))

    item = next(e for p in sent for e in p["items"] if e["item"] == "study/second")
    assert item["outline"] == [{"title": "Idea", "level": 1}]
    assert item["earlier_terms"] == ["Previous term"]
    pages = item["source_pages"][0]
    assert set(pages["cached"]) == {str(i) for i in range(1, 14)}
    assert set(pages["failed"]) == {"14"}
    assert all((project / path).is_file() for path in pages["cached"].values())


@pytest.mark.parametrize("evidence", ["current", "stale-draft", "missing-phone"])
def test_visual_packet_links_the_current_captures(project: Path, evidence: str) -> None:
    key = next(key for key, visuals in loop.load(project).visuals.items() if visuals)
    build, managed = build_files(project)
    identity = BrowserBuild(
        build=build, shell="c" * 64, checks="a" * 64, browser="b" * 64, managed=managed
    )
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
    response["items"][0]["findings"][0].update(
        why="The same defect described differently.", fix="A reworded repair.", score=1
    )
    assert loop.record(project, response, "fresh")["opened"] == 0
    assert loop.load(project).record(key) == before


@pytest.mark.parametrize("status", ["open", "fixed"])
def test_reworded_retry_keeps_existing_defect_across_rounds(project: Path, status: str) -> None:
    loop.start(project, budget=2, workspaces=("study",))
    check_all(project, fail={"study/graphs": "clarity.one_reading"})
    key = "study/graphs"
    original = loop.load(project).record(key).findings[0]
    edit_first_block(project)
    if status == "fixed":
        loop.change(project, key, original.id, "fixed")
    original = loop.load(project).record(key).findings[0]
    loop.close_round(project)
    packet = packets(project, loop.next_round(project))[0]
    response = answer(packet, fail={key: original.check})
    entry = next(e for e in response["items"] if e["item"] == key)
    entry["findings"] = [
        {
            "check": original.check,
            "quote": original.quote,
            "location": original.location,
            "why": "Reworded after a partial reply.",
            "fix": "Restated repair.",
            "score": 1,
        }
    ]
    for verification in entry["verify"]:
        verification["resolved"] = False

    result = loop.record(project, response, "fresh")

    assert result["opened"] == 0
    findings = loop.load(project).record(key).findings
    assert len(findings) == 1
    assert findings[0].id == original.id
    assert (findings[0].why, findings[0].fix, findings[0].score) == (
        original.why,
        original.fix,
        original.score,
    )


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


def test_a_packet_asks_no_more_verdicts_than_one_checker_reply_can_hold(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Trial checkers gave up on packets asking for 100 to 312 quoted verdicts.
    monkeypatch.setattr(loop, "PACKET_VERDICTS", 8)
    loop.start(project, workspaces=("study",))
    context = loop.load(project)
    expected = {key: loop.item_tasks(context, key) for key in loop.read_state(project).scope}
    opened = packets(project, loop.next_round(project))
    assert len(opened) > 1
    for packet in opened:
        counts = [
            sum(len(entry[task]) for task in ("needs", "verify", "visuals", "rule"))
            for entry in packet["items"]
        ]
        assert sum(counts) <= loop.PACKET_VERDICTS
    for key, tasks in expected.items():
        entries = [e for p in opened for e in p["items"] if e["item"] == key]
        for task in ("needs", "verify", "visuals", "rule"):
            assert [v for e in entries for v in e[task]] == tasks[task]
        for entry in entries:
            assert entry["fingerprint"] == loop.packet_fingerprint(context.items[key])
            assert entry["passages"] == loop._passages(context.items[key])
            for field in ("outline", "earlier_terms", "source_pages", "digests", "visual_sheets"):
                assert entry.get(field) == entries[0].get(field)
            assert {flag["key"] for flag in entry["report"] if flag.get("needs_ruling")} == set(
                entry["rule"]
            )


@pytest.mark.parametrize("bound", [1, len(registry.judged("study-unit"))])
def test_item_needs_every_batch_before_scores_are_current(
    project: Path, monkeypatch: pytest.MonkeyPatch, bound: int
) -> None:
    monkeypatch.setattr(loop, "PACKET_VERDICTS", bound)
    loop.start(project, workspaces=("study",))
    before = loop.load(project)
    expected = {key: loop.item_tasks(before, key) for key in loop.read_state(project).scope}
    sent = packets(project, loop.next_round(project))
    first = sent[0]
    key = first["items"][0]["item"]
    loop.record(project, answer(first), "fresh")

    context = loop.load(project)
    assert set(loop.item_tasks(context, key)["needs"]) == (
        set(expected[key]["needs"]) - set(first["items"][0]["needs"])
    )
    assert loop.item_tasks(context, key)["visuals"] or loop.item_tasks(context, key)["rule"]
    assert any("unanswered" in p for p in loop.item_gate(context, key))
    card = loop.scorecard(context, loop.read_state(project))
    assert next(row for row in card["items"] if row["item"] == key)["scores"] == {}
    for packet in reversed(sent[1:]):
        loop.record(project, answer(packet), "fresh")
    context = loop.load(project)
    assert loop.item_tasks(context, key) == {"needs": [], "verify": [], "visuals": [], "rule": []}
    assert not any("unanswered" in p for p in loop.item_gate(context, key))
    card = loop.scorecard(context, loop.read_state(project))
    assert next(row for row in card["items"] if row["item"] == key)["scores"]
    for item, visuals in context.visuals.items():
        assert {v.visual for v in context.record(item).visuals} == set(visuals)


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


def test_selected_examples_reach_review_with_their_actual_teaching_blocks(project: Path) -> None:
    from tum_mcp.course.app.build import read_content

    path = content_file(project, "study")
    document = json.loads(path.read_bytes())
    unit = document["units"][0]
    key = f"study/{unit['key']}"
    examples = [
        {
            "name": "Goal test",
            "kind": "algorithm",
            "instance": "Start at A, goal B, stop when B is generated.",
            "example": {
                "origin": "source",
                "source": unit["sources"][0]["key"],
                "pages": "1-2",
                "shows": "Draw the A-B tree and test B on generation before adding successors.",
                "endpoint": "Return A-B without expanding B.",
                "block": "goal-run",
            },
        },
        {
            "name": "Heat accumulation",
            "kind": "rule",
            "instance": "Two cells contribute 2 and 3 joules, for 5 joules in total.",
            "example": {
                "origin": "source",
                "source": unit["sources"][0]["key"],
                "pages": "3-4",
                "shows": "Draw the cells and add each cell's contribution to the running sum.",
                "endpoint": "The final sum is 5 joules.",
                "block": "heat-grid",
            },
        },
    ]
    catalogue = json.loads((files("tum_mcp.bundled") / "exemplars/blocks.json").read_bytes())
    graph = catalogue["walkthrough-tree"] | {
        "key": "goal-run",
        "sources": [unit["sources"][0]["key"]],
    }
    graph["steps"][-1].update(
        action="Generate B and return A-B.",
        why="B passes the goal test on generation.",
        active=["b"],
        cutoff=[],
    )
    grid = {
        "kind": "walkthrough",
        "key": "heat-grid",
        "sources": graph["sources"],
        "stage": {
            "kind": "grid",
            "description": "Two cells with heat contributions.",
            "grids": [{"key": "heat", "cells": [["2", "3"]]}],
        },
        "steps": [
            {
                "action": "Add the first cell.",
                "why": "The running sum is 2 joules.",
                "grid_marks": [{"grid": "heat", "cell": "1:1"}],
            },
            {
                "action": "Add the second cell.",
                "why": r"The final sum is \(2 + 3 = 5\) joules.",
                "grid_marks": [{"grid": "heat", "cell": "1:2"}],
            },
        ],
    }
    unit["blocks"].extend([graph, grid])
    path.write_text(json.dumps(document))
    planned = {"item": key, "concepts": examples}
    target = project / ".tum-mcp/plans" / f"{key}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(planned))
    loop.start(project, workspaces=("study",))
    sent = packets(project, loop.next_round(project))
    packet = next(p for p in sent if p["items"][0]["item"] == key)
    entry = packet["items"][0]
    actual = next(u for u in read_content(project).units if u.key == unit["key"])
    paired = zip(entry["concepts"], examples, actual.blocks[-2:], strict=True)
    for concept, expected, block in paired:
        assert concept["example"] == expected["example"]
        assert concept["example_block"]["content"] == block.model_dump(mode="json")
        index = len(unit["blocks"]) - 2 + examples.index(expected)
        assert concept["example_block"]["location"] == f"blocks[{index}]"
    response = answer(packet)
    checks = response["items"][0]["checks"]
    checks["intuition.concepts_instanced"]["evidence"] = "Goal test; Heat accumulation."
    checks["coverage.examples_selected"]["evidence"] = "Both concepts are mentioned."
    with pytest.raises(CampusError, match="needs a comparison of each planned example"):
        loop.record(project, response, "fresh")
    checks["coverage.examples_selected"]["evidence"] = (
        "Goal test: goal-run draws A-B and returns when B is generated."
    )
    with pytest.raises(CampusError, match=r"missing Heat accumulation \(heat-grid\)"):
        loop.record(project, response, "fresh")
    checks["coverage.examples_selected"]["evidence"] = (
        "Goal test: goal-run draws A-B and returns when B is generated. "
        "Heat accumulation: heat-grid marks each cell, adds 2 and 3 and concludes 5 joules."
    )
    loop.record(project, response, "fresh")
    for other in sent:
        if other["id"] != packet["id"]:
            loop.record(project, answer(other), "fresh")
    # A later change to the selected endpoint must invalidate this review, even with no edit
    # to the lesson itself. Gate provenance alone must not do so.
    planned["concepts"][0]["example"]["endpoint"] = "Also show the reached set."
    target.write_text(json.dumps(planned))
    waiting = loop.verify_round(project)
    entries = [e for p in packets(project, waiting) for e in p["items"] if e["item"] == key]
    assert entries and "coverage.examples_selected" in entries[0]["needs"]


@pytest.mark.parametrize("repair_valid", [True, False])
def test_a_refused_checker_answer_repairs_or_reports_saved_partial_results(
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
        "    result['items'][0]['checks'][next(iter(result['items'][0]['checks']))]['quote']"
        " = 'absent evidence'\n"
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
    assert set(saved["items"][0]["checks"]) == set(expected)


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
