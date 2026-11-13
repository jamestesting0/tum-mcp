import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.plans import Plan, example_problems

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


def test_a_study_algorithm_is_taught_on_a_chosen_example() -> None:
    assert example_problems(plan(example=UCS)) == []
    assert "choose the lecture example" in example_problems(plan())[0]
    assert example_problems(plan(skip="Only named here; taught in the next unit.")) == []
    assert example_problems(plan(item="exercise/sheet-1/1")) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"pages": None}, "names its source and pages"),
        ({"origin": "constructed", "source": None, "pages": None}, "why the lecture has none"),
    ],
)
def test_an_example_says_where_it_comes_from(change: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        plan(example=UCS | change)


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
    from tum_mcp.errors import CampusError

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
    with pytest.raises(CampusError, match="evidence"):
        record_gate(tmp_path, [answer | {"verdict": "fail", "reasons": [note.upper()]}], "fresh")
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
        (2, "reason", "open"),
    ]
    assert current.fingerprint() == Plan.model_validate_json(stored.read_bytes()).fingerprint()


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
