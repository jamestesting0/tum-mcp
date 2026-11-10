import copy
import json
from importlib.resources import files

import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.course.content.study import Block, WalkthroughBlock, compile_formulas, render_blocks

EXAMPLE = json.loads((files("tum_mcp") / "bundled/course_app/example/content.json").read_bytes())
WALKS = {
    block["key"]: block for block in EXAMPLE["units"][0]["blocks"] if block["kind"] == "walkthrough"
}


def graph() -> dict:
    return copy.deepcopy(WALKS["walkthrough-graph"])


def table() -> dict:
    return copy.deepcopy(WALKS["walkthrough-table"])


def test_run_keyed_answers_check_exact_state_in_each_run() -> None:
    from tum_mcp.course.checks.answers import compare

    block = {
        "kind": "walkthrough",
        "key": "queue",
        "steps": [{"state": [{"label": "Frontier", "value": "A"}]}],
        "variant": {"steps": [{"state": [{"label": "Frontier", "value": "Empty"}]}]},
    }
    expected = {"primary": [{"Frontier": "A"}], "variant": [{"Frontier": "Empty"}]}

    def check(runs: dict) -> tuple[list[str], int]:
        return compare(block, {"walkthroughs": {"queue": runs}})

    assert check(expected) == ([], 2)
    assert "queue/primary step 1" in check(expected | {"primary": [{"Frontier": "AA"}]})[0][0]
    assert "queue/variant step 1" in check(expected | {"variant": [{"Frontier": "A"}]})[0][0]
    assert "authored variant" in check({"primary": expected["primary"]})[0][0]


def test_the_shipped_walkthroughs_render_their_stage() -> None:
    blocks = TypeAdapter(tuple[Block, ...]).validate_python(list(WALKS.values()))
    rendered = render_blocks(blocks)
    assert rendered[0]["stage"]["kind"] == "diagram"
    assert rendered[0]["variant"]["label"] == "Depth-first"
    assert rendered[1]["stage"]["rows"][3] == ["3", "1", "3"]


def test_a_plot_stage_is_sampled_and_a_formula_stage_compiled_wherever_it_sits() -> None:
    plot = {
        "kind": "plot",
        "description": "Growth.",
        "x_label": "n",
        "y_label": "f(n)",
        "x_min": 0,
        "x_max": 4,
        "y_min": 0,
        "y_max": 16,
        "series": [
            {"key": "lin", "label": "n", "function": "x"},
            {"key": "sq", "label": "n²", "function": "x^2"},
        ],
    }
    walk = {
        "kind": "walkthrough",
        "title": "Growth",
        "sources": ["s"],
        "stage": plot,
        "steps": [
            {"action": "Draw \\(n\\).", "why": "The baseline.", "series": ["lin"]},
            {"action": "Add \\(n^2\\).", "why": "It overtakes.", "series": ["lin", "sq"]},
        ],
    }
    WalkthroughBlock.model_validate(walk)
    compiled = compile_formulas(walk)
    assert all(line.get("pieces") for line in compiled["stage"]["series"])
    working = {
        "kind": "derivation",
        "groups": [{"lines": [{"latex": "x = 1 + 1"}, {"latex": "= 2"}]}],
    }
    walk |= {
        "stage": working,
        "steps": [
            {"action": "Add.", "why": "Both terms are known.", "shown": 1},
            {"action": "Simplify.", "why": "One plus one is two.", "shown": 2},
        ],
    }
    WalkthroughBlock.model_validate(walk)
    assert "mathml" in compile_formulas(walk)["stage"]["groups"][0]["lines"][1]


def edit(change):
    def apply(value: dict) -> dict:
        change(value)
        return value

    return apply


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (edit(lambda b: b["steps"][1].update(lines="1-2")), "lines, which a diagram stage"),
        (edit(lambda b: b["steps"][1].update(active=["z"])), "node the stage does not draw"),
        (edit(lambda b: b["steps"][1].update(edges=[{"start": "a", "end": "g"}])), "edge"),
        (edit(lambda b: b.pop("contrast")), "states the contrast"),
        (edit(lambda b: b["variant"].update(steps=copy.deepcopy(b["steps"]))), "different step"),
        (edit(lambda b: b["steps"][4].update(subgoal="Start")), "returns after another one"),
        (edit(lambda b: b["steps"][0].update(at=12)), "lecture highlight steps"),
        (edit(lambda b: b.pop("stage")), "without a stage"),
    ],
)
def test_graph_steps_must_fit_their_stage_and_runs(make, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        WalkthroughBlock.model_validate(make(graph()))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"shown": 6}, "outside the shown rows"),
        ({"shown": 2, "cells": ["3:2"]}, "outside the shown rows"),
        ({"cells": ["1:4"]}, "outside the shown rows"),
    ],
)
def test_table_steps_mark_only_rows_already_filled(change: dict, message: str) -> None:
    value = table()
    value["steps"][1].update(change)
    with pytest.raises(ValidationError, match=message):
        WalkthroughBlock.model_validate(value)


def test_a_variant_differing_only_in_reasons_is_not_a_variant() -> None:
    value = graph()
    value["variant"]["steps"] = [step | {"why": "Reworded."} for step in value["steps"]]
    with pytest.raises(ValidationError, match="different step"):
        WalkthroughBlock.model_validate(value)
