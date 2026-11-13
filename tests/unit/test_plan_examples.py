from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.plans import Plan, example_problems, plan_problems

UCS = {
    "origin": "source",
    "source": "uninformed",
    "pages": "52-56",
    "shows": "B is found at 310, then improved to 278 before it is removed.",
    "endpoint": "B removed with g = 278.",
    "block": "ucs-romania",
}


def plan(item: str = "study/search", **concept) -> Plan:
    base = {"name": "Uniform-cost search", "kind": "algorithm", "instance": "Romania subgraph."}
    return Plan.model_validate({"item": item, "concepts": [base | concept]})


@pytest.mark.parametrize("kind", ["procedure", "algorithm", "model"])
def test_a_worked_study_concept_requires_an_example_or_skip(kind: str) -> None:
    assert example_problems(plan(kind=kind, example=UCS)) == []
    assert "choose the lecture example" in example_problems(plan(kind=kind))[0]
    assert example_problems(plan(kind=kind, skip="Only named here; taught next.")) == []
    assert example_problems(plan(item="exercise/sheet-1/1", kind=kind)) == []


def test_a_comparison_without_a_source_demonstration_needs_no_example() -> None:
    current = plan(
        name="Civil and criminal burdens of proof",
        kind="comparison",
        instance="An evenly balanced civil claim fails because neither side is more likely.",
        blocks=["burdens"],
    )
    assert example_problems(current) == []
    assert plan_problems(current, {"blocks": [{"key": "burdens", "kind": "table"}]}, None) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"pages": None}, "names its source and pages"),
        ({"origin": "constructed", "source": None, "pages": None}, "why the lecture has none"),
    ],
)
@pytest.mark.parametrize("kind", ["algorithm", "rule", "comparison"])
def test_an_example_says_where_it_comes_from(kind: str, change: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        plan(kind=kind, example=UCS | change)


@pytest.mark.parametrize("field", ["shows", "endpoint", "block"])
def test_a_rule_example_requires_its_teaching_payload(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        plan(kind="rule", example={key: value for key, value in UCS.items() if key != field})
    assert error.value.errors()[0]["loc"] == ("concepts", 0, "example", field)


def test_the_next_checker_sees_the_rejected_reasons_and_a_pass_carries_advice(tmp_path) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet, record_gate

    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    stored.write_text(plan(example=UCS).model_dump_json(), encoding="utf-8")
    fingerprint = plan(example=UCS).fingerprint()
    reasons = ["The UCS run stops before B is improved to 278."]
    record_gate(
        tmp_path,
        [
            {
                "item": "study/search",
                "fingerprint": fingerprint,
                "verdict": "fail",
                "reasons": reasons,
            }
        ],
        "fresh",
    )
    packet = plan_packet(tmp_path)
    assert packet["plans"][0]["previous"] == reasons
    assert packet["answer"]["items"][0]["advice"] == []

    advice = ["Name the tie-break in the frontier caption."]
    result = record_gate(
        tmp_path,
        [{"item": "study/search", "fingerprint": fingerprint, "verdict": "pass", "advice": advice}],
        "fresh",
    )
    assert result["verdicts"]["study/search"]["advice"] == advice
    saved = json.loads(stored.read_text(encoding="utf-8"))["gate"]
    assert saved["verdict"] == "pass" and saved["advice"] == advice
    assert plan_packet(tmp_path)["plans"] == []


def test_gate_history_preserves_reasons_and_guards_advice_escalation(tmp_path) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet, record_gate

    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    current = plan(example=UCS)
    stored.write_text(current.model_dump_json(), encoding="utf-8")
    answer = {"item": current.item, "fingerprint": current.fingerprint()}
    note = "Uniform-cost search should name the tie-break."
    record_gate(
        tmp_path,
        [answer | {"verdict": "fail", "reasons": ["Missing input."], "advice": [note]}],
        "fresh",
    )
    packet = plan_packet(tmp_path)
    history = packet["plans"][0]["history"]
    assert [(entry["check"], entry["kind"], entry["state"]) for entry in history] == [
        (1, "reason", "open"),
        (1, "advice", "open"),
    ]
    assert packet["plans"][0]["concepts"][0]["changed"] is False
    demoted = record_gate(
        tmp_path, [answer | {"verdict": "fail", "reasons": [note.upper()]}], "fresh"
    )
    assert demoted["verdicts"][current.item] == {
        "verdict": "pass",
        "reasons": [],
        "advice": [note.upper()],
    }
    record_gate(
        tmp_path,
        [
            answer
            | {
                "verdict": "fail",
                "reasons": [note],
                "resolved": ["Missing input."],
                "evidence": {note: "The source fixes the tie-break."},
            }
        ],
        "fresh",
    )
    history = json.loads(stored.read_text())["gate"]["history"]
    assert [(entry["check"], entry["kind"], entry["state"]) for entry in history] == [
        (1, "reason", "resolved"),
        (1, "advice", "escalated"),
        (2, "advice", "escalated"),
        (3, "reason", "open"),
    ]
    assert current.fingerprint() == Plan.model_validate_json(stored.read_bytes()).fingerprint()


@pytest.mark.parametrize(
    ("changed", "reason", "evidence", "expected"),
    [
        (False, "Uniform-cost search omits a cost.", {}, "pass"),
        (
            False,
            "Uniform-cost search omits a cost.",
            {"Uniform-cost search omits a cost.": "Slide 53 gives edge S-R as 80."},
            "fail",
        ),
        (True, "Uniform-cost search omits a cost.", {}, "fail"),
        (True, "A new unrelated blocker.", {}, "pass"),
        (False, "Original blocker.", {}, "fail"),
    ],
)
def test_later_blocker_needs_a_named_changed_concept_or_source_evidence(
    tmp_path: Path, changed: bool, reason: str, evidence: dict[str, str], expected: str
) -> None:
    import json

    from tum_mcp.course.checks.plans import read_plan, record_gate

    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    current = plan(example=UCS)
    stored.write_text(current.model_dump_json())
    first = {"item": current.item, "fingerprint": current.fingerprint()}
    result = record_gate(
        tmp_path, [first | {"verdict": "fail", "reasons": ["Original blocker."]}], "fresh"
    )
    assert result["verdicts"][current.item]["verdict"] == "fail"
    if changed:
        body = json.loads(stored.read_text())
        body["concepts"][0]["instance"] = "A changed search input."
        stored.write_text(json.dumps(body))
    current = read_plan(tmp_path, current.item)
    assert current is not None
    result = record_gate(
        tmp_path,
        [
            {
                "item": current.item,
                "fingerprint": current.fingerprint(),
                "verdict": "fail",
                "reasons": [reason],
                "evidence": evidence,
            }
        ],
        "fresh",
    )
    verdict = result["verdicts"][current.item]
    assert verdict["verdict"] == expected
    assert verdict.get("advice", []) == ([reason] if expected == "pass" else [])


def test_unused_digest_examples_respect_source_and_page_overlap(tmp_path) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet

    directory = tmp_path / ".tum-mcp/plans/study"
    directory.mkdir(parents=True)
    (directory / "search.json").write_text(plan(example=UCS).model_dump_json())
    digests = tmp_path / ".tum-mcp/digests"
    digests.mkdir()
    for source in ("uninformed", "other"):
        (digests / f"{source}.json").write_text(
            json.dumps(
                {
                    "source": source,
                    "sha256": "0" * 64,
                    "examples": [
                        {"pages": "50-52", "text": "Overlap."},
                        {"pages": "57", "text": "Unused."},
                    ],
                }
            )
        )
    unused = plan_packet(tmp_path)["unused_examples"]
    assert {(entry["source"], entry["pages"]) for entry in unused} == {
        ("uninformed", "57"),
        ("other", "50-52"),
        ("other", "57"),
    }


@pytest.mark.parametrize(
    ("name", "source", "shows", "endpoint"),
    [
        (
            "A-star contour thresholds",
            "informed",
            "Draw the map's nested 380, 400 and 420 contours and locate the goal at cost 418.",
            "The goal lies inside 420; regions above 418 cannot improve that route.",
        ),
        (
            "Kirchhoff current law",
            "circuits",
            "Draw the labelled junction with 2 A and 3 A entering and one unknown current leaving.",
            "The outgoing current is 5 A by charge conservation.",
        ),
    ],
)
def test_a_rule_source_example_is_digest_matched_and_linked_to_its_picture(
    tmp_path: Path, name: str, source: str, shows: str, endpoint: str
) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet

    example = {
        "origin": "source",
        "source": source,
        "pages": "3-5",
        "shows": shows,
        "endpoint": endpoint,
        "block": "picture",
    }
    current = plan(name=name, kind="rule", instance=endpoint, example=example)
    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    stored.write_text(current.model_dump_json())
    digests = tmp_path / ".tum-mcp/digests"
    digests.mkdir()
    (digests / f"{source}.json").write_text(
        json.dumps(
            {
                "source": source,
                "sha256": "0" * 64,
                "examples": [
                    {"pages": "3-5", "text": shows},
                    {"pages": "8", "text": "Another demonstration."},
                ],
            }
        )
    )
    packet = plan_packet(tmp_path)
    assert packet["unused_examples"] == [
        {"source": source, "kind": "example", "pages": "8", "text": "Another demonstration."}
    ]
    assert packet["plans"][0]["concepts"][0]["example"] == example
    assert plan_problems(current, {"blocks": []}, None) == [
        f"{name}: the example block picture is missing"
    ]
    assert plan_problems(current, {"blocks": [{"key": "picture", "kind": "figure"}]}, None) == []


@pytest.mark.parametrize(
    "description",
    [
        "The phase diagram shows when a conservation argument stops applying.",
        "The class diagram shows which object owns the lifecycle transition.",
    ],
)
def test_figures_only_digest_entries_reach_selection_even_on_a_selected_page(
    tmp_path: Path, description: str
) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet

    directory = tmp_path / ".tum-mcp/plans/study"
    directory.mkdir(parents=True)
    (directory / "search.json").write_text(plan(example=UCS).model_dump_json())
    digests = tmp_path / ".tum-mcp/digests"
    digests.mkdir()
    (digests / "uninformed.json").write_text(
        json.dumps(
            {
                "source": "uninformed",
                "sha256": "0" * 64,
                "figures": [{"pages": "53", "text": description}],
            }
        )
    )
    packet = plan_packet(tmp_path)
    assert packet["unused_examples"] == [
        {"source": "uninformed", "pages": "53", "text": description, "kind": "figure"}
    ]
    assert packet["answer"]["items"][0]["reasons"] == []


def test_changed_concept_can_escalate_advice_without_new_evidence(tmp_path) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet, record_gate

    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    current = plan(example=UCS)
    stored.write_text(current.model_dump_json())
    note = "Uniform-cost search should name the tie-break."
    record_gate(
        tmp_path,
        [
            {
                "item": current.item,
                "fingerprint": current.fingerprint(),
                "verdict": "pass",
                "advice": [note],
            }
        ],
        "fresh",
    )
    body = json.loads(stored.read_text())
    body["concepts"][0]["instance"] = "A different Romania graph."
    stored.write_text(json.dumps(body))
    packet = plan_packet(tmp_path)
    assert packet["plans"][0]["concepts"][0]["changed"] is True
    answer = packet["answer"]["items"][0] | {"verdict": "fail", "reasons": [note]}
    record_gate(tmp_path, [answer], "fresh")
    assert json.loads(stored.read_text())["gate"]["history"][0]["state"] == "escalated"


def test_legacy_approval_remains_valid_and_history_accepts_indices(tmp_path) -> None:
    import json

    from tum_mcp.course.checks.plans import gate_status, plan_packet, record_gate

    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    current = plan(example=UCS)
    body = current.model_dump(mode="json")
    body["gate"] = {
        "fingerprint": current.fingerprint(),
        "verdict": "fail",
        "reasons": ["Missing input."],
        "advice": ["Name the tie-break."],
        "provenance": "fresh",
    }
    stored.write_text(json.dumps(body))
    assert gate_status(Plan.model_validate_json(stored.read_bytes())) == "rejected"
    packet = plan_packet(tmp_path)
    assert [entry["text"] for entry in packet["plans"][0]["history"]] == [
        "Missing input.",
        "Name the tie-break.",
    ]
    record_gate(
        tmp_path,
        [
            {
                "item": current.item,
                "fingerprint": current.fingerprint(),
                "verdict": "pass",
                "resolved": [0, 1],
            }
        ],
        "fresh",
    )
    saved = Plan.model_validate_json(stored.read_bytes())
    assert gate_status(saved) == "approved"
    assert saved.fingerprint() == current.fingerprint()
    assert saved.gate is not None
    assert [entry.state for entry in saved.gate.history] == ["resolved", "resolved"]
