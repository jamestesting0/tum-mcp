from pathlib import Path

import pytest
from pydantic import ValidationError

from tum_mcp.course.checks.plans import Plan, example_problems, example_state_flags, plan_problems

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
    ("name", "source", "operations"),
    [
        (
            "Search with individual child insertions",
            "search",
            [
                ("Select", ["Initial stack A", "Remove A"]),
                ("Generate", ["Insert B", "Insert C"]),
            ],
        ),
        (
            "Solving a linear equation",
            "algebra",
            [
                ("Given", [r"\(2x+4=10\)"]),
                ("Solve", [r"Subtract four: \(2x=6\)", r"Divide by two: \(x=3\)"]),
            ],
        ),
        (
            "Search with source-atomic expansion",
            "search",
            [
                ("Given", ["Initial node A"]),
                ("Expand", ["Expand A, adding B and C together as one source operation"]),
            ],
        ),
        (
            "One matrix row operation changes several entries",
            "linear-algebra",
            [
                ("Given", [r"\(\begin{pmatrix}1&2\\3&4\end{pmatrix}\)"]),
                ("Transform", [r"\(R_2 \gets R_2 - 3R_1\)"]),
            ],
        ),
    ],
)
def test_source_states_are_a_floor_in_one_grouped_walkthrough(
    name: str, source: str, operations: list[tuple[str, list[str]]]
) -> None:
    phases = [phase for phase, _ in operations]
    steps = [
        {"subgoal": phase, "action": action} for phase, actions in operations for action in actions
    ]
    current = plan(
        name=name,
        example=UCS | {"source": source, "states": len(steps), "phases": phases},
        blocks=["ucs-romania"],
    )
    block = {"key": "ucs-romania", "kind": "walkthrough", "steps": steps}
    assert plan_problems(current, {"blocks": [block]}, None) == []
    frames = [{"subgoal": phase, "action": "; ".join(actions)} for phase, actions in operations]
    flags = example_state_flags(current, {"blocks": [block | {"steps": frames}]})
    assert [flag["flag"] for flag in flags] == (
        ["source_states_missing"] if len(steps) > len(frames) else []
    )
    assert [
        flag["flag"]
        for flag in example_state_flags(current, {"blocks": [block | {"steps": steps[:-1]}]})
        if flag["flag"] == "source_states_missing"
    ] == ["source_states_missing"]
    assert plan_problems(current, {"blocks": [block | {"steps": steps + [steps[-1]]}]}, None) == []
    assert plan_problems(
        current, {"blocks": [block | {"steps": [{"subgoal": phases[0]}] * len(steps)}]}, None
    )
    assert plan_problems(current, {"blocks": [block | {"steps": [*steps, {}]}]}, None)


@pytest.mark.parametrize(
    ("name", "source", "shows", "endpoint"),
    [
        (
            "Growing search tree",
            "search",
            "Draw the root, its children, then the next expansion.",
            "The same state occurs on two distinct paths.",
        ),
        (
            "Gaussian elimination",
            "linear-algebra",
            "Show the initial matrix and each row operation.",
            "The triangular system has the same solutions.",
        ),
    ],
)
def test_source_walkthrough_requires_a_state_count_even_with_phases(
    name: str, source: str, shows: str, endpoint: str
) -> None:
    current = plan(
        name=name,
        example=UCS
        | {
            "source": source,
            "shows": shows,
            "endpoint": endpoint,
            "phases": ["Prepare", "Compute"],
        },
        blocks=["ucs-romania"],
    )
    value = {
        "blocks": [
            {
                "key": "ucs-romania",
                "kind": "walkthrough",
                "steps": [{"subgoal": "Prepare"}, {"subgoal": "Compute"}],
            }
        ]
    }
    flags = example_state_flags(current, value)
    assert [flag["flag"] for flag in flags] == ["source_states_missing"]
    assert plan_problems(current, value, None) == [flags[0]["detail"]]


def test_finished_picture_and_constructed_run_need_no_source_state_count() -> None:
    summary = plan(kind="rule", example=UCS, blocks=["ucs-romania"])
    constructed = plan(
        example=UCS | {"origin": "constructed", "why": "The source gives no worked run."},
        blocks=["ucs-romania"],
    )
    value = {"blocks": [{"key": "ucs-romania", "kind": "walkthrough", "steps": [{}]}]}
    picture = {"blocks": [{"key": "ucs-romania", "kind": "figure"}]}
    assert plan_problems(summary, picture, None) == []
    assert plan_problems(constructed, value, None) == []
    assert "states" not in summary.model_dump(mode="json")["concepts"][0]["example"]
    assert "phases" not in summary.model_dump(mode="json")["concepts"][0]["example"]


@pytest.mark.parametrize("states", [0, -1, 1.5, True])
def test_source_state_count_is_a_positive_whole_number(states: int | float) -> None:
    with pytest.raises(ValidationError):
        plan(example=UCS | {"states": states})


@pytest.mark.parametrize(
    ("name", "script"),
    [
        (
            "Repeated states in tree and graph search",
            [
                "p.15: the root Arad",
                "p.16: expanding Arad adds Sibiu, Timisoara and Zerind",
                "p.17: tree search keeps the second Arad under Sibiu",
                "p.18: graph search discards the second Arad as reached",
            ],
        ),
        (
            "Reducing a resistor network",
            [
                "p.30: the network with all six resistors",
                "p.31: R2 and R3 in series become R23",
                "p.31: R23 and R4 in parallel become R234",
            ],
        ),
    ],
)
def test_a_script_sets_one_step_per_source_state(name: str, script: list[str]) -> None:
    current = plan(name=name, example=UCS | {"script": script}, blocks=["ucs-romania"])
    assert current.concepts[0].example is not None
    assert current.concepts[0].example.state_count == len(script)
    block = {"key": "ucs-romania", "kind": "walkthrough", "steps": [{}] * len(script)}
    assert example_state_flags(current, {"blocks": [block]}) == []
    short = block | {"steps": [{}] * (len(script) - 1)}
    flags = example_state_flags(current, {"blocks": [short]})
    assert [flag["flag"] for flag in flags] == ["source_states_missing"]
    assert f"for {len(script)} planned source states" in str(flags[0]["detail"])


def test_a_script_and_a_count_must_agree() -> None:
    assert plan(example=UCS | {"script": ["p.52: start"], "states": 1})
    with pytest.raises(ValidationError, match="give the script alone"):
        plan(example=UCS | {"script": ["p.52: start", "p.53: pop S"], "states": 3})


ROADS = {"kind": "graph", "edges": 3, "directed": False}


def diagram(edges: int, *, directed: bool = False, layout: str = "lattice") -> dict:
    pairs = [{"start": f"n{i}", "end": f"n{i + 1}", "directed": directed} for i in range(edges)]
    return {"kind": "diagram", "layout": layout, "nodes": [], "edges": pairs}


@pytest.mark.parametrize(
    ("planned", "drawn", "missing"),
    [
        (ROADS, {"key": "map", **diagram(3)}, False),
        (ROADS, {"key": "map", "kind": "example", "blocks": [diagram(4)]}, False),
        (ROADS, {"key": "map", **diagram(2)}, True),
        (ROADS, {"key": "map", **diagram(3, directed=True)}, True),
        (ROADS, {"key": "map", **diagram(5, directed=True, layout="tree")}, True),
        (ROADS, {"key": "map", "kind": "table", "rows": [["S", "R", "80"]] * 3}, True),
        ({"kind": "grid", "grids": 2}, {"key": "map", "kind": "grid", "grids": [{}, {}]}, False),
        ({"kind": "grid", "grids": 2}, {"key": "map", "kind": "grid", "grids": [{}]}, True),
    ],
)
def test_a_planned_input_must_be_drawn_not_described_or_derived(
    planned: dict, drawn: dict, missing: bool
) -> None:
    current = plan(example=UCS | {"input": planned}, blocks=["ucs-romania"])
    walk = {
        "key": "ucs-romania",
        "kind": "walkthrough",
        "steps": [{}],
        "stage": diagram(1, directed=True, layout="tree"),
    }
    flags = example_state_flags(current, {"blocks": [walk, drawn]})
    assert [flag["flag"] for flag in flags if flag["flag"] == "source_input_missing"] == (
        ["source_input_missing"] if missing else []
    )


def test_a_walkthrough_stage_can_draw_its_own_input() -> None:
    current = plan(example=UCS | {"input": ROADS, "states": 1}, blocks=["ucs-romania"])
    walk = {"key": "ucs-romania", "kind": "walkthrough", "steps": [{}], "stage": diagram(3)}
    assert example_state_flags(current, {"blocks": [walk]}) == []


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
    assert {
        (entry["source"], entry["pages"], entry.get("overlaps_planned")) for entry in unused
    } == {
        ("uninformed", "50-52", "52-56"),
        ("uninformed", "57", None),
        ("other", "50-52", None),
        ("other", "57", None),
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


@pytest.mark.parametrize(
    ("planned", "inside"),
    [
        ("Two boards and their tile distances.", "The effort of a heuristic on 100 instances."),
        ("A full proof of the triangle inequality.", "A worked counterexample in two dimensions."),
    ],
)
def test_a_wider_planned_range_does_not_hide_a_separate_example_inside_it(
    tmp_path: Path, planned: str, inside: str
) -> None:
    import json

    from tum_mcp.course.checks.plans import plan_packet

    example = {
        "origin": "source",
        "source": "lecture",
        "pages": "42-47",
        "shows": planned,
        "endpoint": planned,
        "block": "picture",
    }
    stored = tmp_path / ".tum-mcp/plans/study/search.json"
    stored.parent.mkdir(parents=True)
    stored.write_text(plan(kind="rule", example=example).model_dump_json())
    digests = tmp_path / ".tum-mcp/digests"
    digests.mkdir()
    (digests / "lecture.json").write_text(
        json.dumps(
            {
                "source": "lecture",
                "sha256": "0" * 64,
                "examples": [
                    {"pages": "42-47", "text": planned},
                    {"pages": "44-45", "text": inside},
                ],
            }
        )
    )

    unused = plan_packet(tmp_path)["unused_examples"]

    assert unused == [
        {
            "source": "lecture",
            "kind": "example",
            "pages": "44-45",
            "text": inside,
            "overlaps_planned": "42-47",
        }
    ]


def test_changed_concept_can_escalate_advice_without_new_evidence(tmp_path: Path) -> None:
    import json

    from tum_mcp.course.checks.plans import gate_status, plan_packet, read_plan, record_gate
    from tum_mcp.errors import CampusError

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
    approved = read_plan(tmp_path, current.item)
    assert approved is not None
    assert gate_status(approved) == "approved"
    assert plan_packet(tmp_path)["plans"] == []
    body = json.loads(stored.read_text())
    body["concepts"][0]["instance"] = "A different Romania graph."
    stored.write_text(json.dumps(body))
    changed = read_plan(tmp_path, current.item)
    assert changed is not None
    assert gate_status(changed) == "changed"
    with pytest.raises(CampusError, match="changed since it was read"):
        record_gate(
            tmp_path,
            [{"item": current.item, "fingerprint": current.fingerprint(), "verdict": "pass"}],
            "fresh",
        )
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
