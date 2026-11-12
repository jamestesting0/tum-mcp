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
