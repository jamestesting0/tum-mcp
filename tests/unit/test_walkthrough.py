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


def test_a_long_process_fits_in_one_walkthrough() -> None:
    block = graph()
    steps = [copy.deepcopy(block["steps"][i % len(block["steps"])]) for i in range(120)]
    for i, step in enumerate(steps):
        step["subgoal"] = f"Phase {i // 30 + 1}"
    block["steps"] = steps

    walk = TypeAdapter(Block).validate_python(block)

    assert isinstance(walk, WalkthroughBlock)
    assert len(walk.steps) == 120


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


def test_answer_keys_check_the_values_written_under_nodes() -> None:
    from tum_mcp.course.checks.answers import compare

    block = {"kind": "walkthrough", "key": "astar", "steps": [{"node_values": {"s": "f = 393"}}]}

    def check(values: dict) -> tuple[list[str], int]:
        return compare(block, {"walkthroughs": {"astar": {"primary": [{"@node_values": values}]}}})

    assert check({"s": "f = 393"}) == ([], 1)
    assert "the key computes 'f = 392'" in check({"s": "f = 392"})[0][0]
    assert "under each node" in check({"s": "f = 393", "t": "f = 447"})[0][0]


@pytest.mark.parametrize("mark", ["cutoff", "discarded"])
def test_answer_keys_compare_node_roles_when_supplied(mark: str) -> None:
    from tum_mcp.course.checks.answers import compare

    block = {"kind": "walkthrough", "key": "dls", "steps": [{mark: ["b"]}]}

    def key(nodes: list[str]) -> dict:
        return {"walkthroughs": {"dls": {"primary": [{f"@{mark}": nodes}]}}}

    assert compare(block, key(["b"])) == ([], 1)
    assert compare(block, key(["c"]))[0]


def tree(**change) -> dict:
    nodes = [{"key": key, "label": key.upper()} for key in "abc"]
    edges = [{"start": "a", "end": end, "directed": True} for end in "bc"]
    stage = {"kind": "diagram", "layout": "tree", "description": "Tree.", "nodes": nodes}
    step = {"action": "Expand A.", "why": "Root.", "active": ["a"], "visible_nodes": ["a"]}
    return {
        "kind": "walkthrough",
        "sources": ["s"],
        "stage": stage | {"edges": edges} | change,
        "steps": [step, step | {"visible_nodes": None, "node_values": {"b": "h = 1"}}],
    }


@pytest.mark.parametrize("mark", ["cutoff", "discarded"])
def test_node_roles_must_be_drawn_and_visible(mark: str) -> None:
    value = tree()
    value["steps"][1][mark] = ["b"]
    assert getattr(WalkthroughBlock.model_validate(value).steps[1], mark) == ("b",)
    value["steps"][1][mark] = ["z"]
    with pytest.raises(ValidationError, match="node the stage does not draw"):
        WalkthroughBlock.model_validate(value)
    value["steps"][1].update({mark: ["b"], "visible_nodes": ["a"]})
    with pytest.raises(ValidationError, match="node it does not show yet"):
        WalkthroughBlock.model_validate(value)


@pytest.mark.parametrize("mark", ["cutoff", "discarded"])
def test_the_current_node_may_also_carry_its_outcome(mark: str) -> None:
    value = tree()
    value["steps"][0][mark] = ["a"]
    step = WalkthroughBlock.model_validate(value).steps[0]
    assert step.active == ("a",) and getattr(step, mark) == ("a",)


def test_a_tree_stage_places_nodes_from_its_edges_and_reveals_them() -> None:
    WalkthroughBlock.model_validate(tree())
    early = tree()
    early["steps"][0]["active"] = ["b"]
    with pytest.raises(ValidationError, match="does not show yet"):
        WalkthroughBlock.model_validate(early)
    cases = [
        (
            {"nodes": [{"key": k, "label": k, "row": 0, "col": i} for i, k in enumerate("abc")]},
            "drop row and col",
        ),
        ({"edges": [{"start": "a", "end": "b"}, {"start": "a", "end": "c"}]}, "directed"),
        ({"edges": [{"start": "a", "end": "b", "directed": True}]}, "one root"),
        (
            {"edges": [{"start": s, "end": e, "directed": True} for s, e in ["ab", "cb", "ac"]]},
            "one parent",
        ),
    ]
    for change, message in cases:
        with pytest.raises(ValidationError, match=message):
            WalkthroughBlock.model_validate(tree(**change))


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


def image_walk(**step_change) -> dict:
    step = {"action": "Measure tile 1.", "why": "Two rows and one column away."}
    return {
        "kind": "walkthrough",
        "key": "tiles",
        "sources": ["notes"],
        "stage": {"kind": "figure", "alt": "Start and goal boards.", "image": "figures/boards.png"},
        "steps": [
            step | {"regions": [{"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.3, "label": "3"}]},
            step | step_change,
        ],
    }


def test_an_image_stage_marks_regions_and_swaps_frames() -> None:
    walk = WalkthroughBlock.model_validate(image_walk(frame="figures/boards-2.png"))
    assert walk.steps[0].regions[0].label == "3" and walk.steps[1].frame == "figures/boards-2.png"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"regions": [{"x": 0.8, "y": 0, "w": 0.3, "h": 0.1}]}, "inside its image"),
        ({"frame": "../boards.png"}, "file in figures/"),
    ],
)
def test_image_marks_stay_on_the_image(change: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        WalkthroughBlock.model_validate(image_walk(**change))


def test_a_drawn_figure_takes_layers_not_regions() -> None:
    walk = image_walk()
    walk["stage"] = {
        "kind": "figure",
        "alt": "A box.",
        "svg": '<svg viewBox="0 0 320 200"><rect id="a" x="1" y="1" width="9" height="9"/></svg>',
    }
    with pytest.raises(ValidationError, match="Regions and frames mark an image"):
        WalkthroughBlock.model_validate(walk)


def grid_walk() -> dict:
    return {
        "kind": "walkthrough",
        "key": "maze",
        "sources": [WALKS["walkthrough-graph"]["sources"][0]],
        "stage": {
            "kind": "grid",
            "description": "A two by two maze.",
            "grids": [{"key": "maze", "cells": [["S", ""], ["", "G"]], "shaded": ["1:2"]}],
        },
        "steps": [
            {
                "action": "Start.",
                "why": "S is distance 0.",
                "grid_marks": [{"grid": "maze", "cell": "1:1"}],
            },
            {
                "action": "Reach the cell below.",
                "why": "One move from S.",
                "grid_marks": [{"grid": "maze", "cell": "2:1", "mark": "frontier"}],
                "grid_values": [{"grid": "maze", "cell": "2:1", "value": "1"}],
                "grid_arrows": [
                    {
                        "start": {"grid": "maze", "cell": "1:1"},
                        "end": {"grid": "maze", "cell": "2:1"},
                    }
                ],
            },
        ],
    }


def test_a_grid_stage_accepts_cells_inside_its_grids_only() -> None:
    adapter = TypeAdapter(Block)
    adapter.validate_python(grid_walk())
    outside = grid_walk()
    outside["steps"][1]["grid_marks"][0]["cell"] = "3:1"
    unknown = grid_walk()
    unknown["steps"][1]["grid_arrows"][0]["end"]["grid"] = "goal"
    ragged = grid_walk()
    ragged["stage"]["grids"][0]["cells"] = [["S", ""], ["G"]]
    on_graph = graph()
    on_graph["steps"][0]["grid_marks"] = [{"grid": "maze", "cell": "1:1"}]
    for bad, message in (
        (outside, "outside the grid"),
        (unknown, "No grid 'goal'"),
        (ragged, "rows of equal length"),
        (on_graph, "grid_marks"),
    ):
        with pytest.raises(ValidationError, match=message):
            adapter.validate_python(bad)


def test_a_grid_cell_may_be_current_and_discarded_in_one_step() -> None:
    value = grid_walk()
    mark = {"grid": "maze", "cell": "1:1", "mark": "discarded"}
    value["steps"][0]["grid_marks"] = [mark, mark | {"mark": "active"}]
    marks = WalkthroughBlock.model_validate(value).steps[0].grid_marks
    assert {item.mark for item in marks} == {"active", "discarded"}


def test_answer_keys_compare_grid_cells_after_each_step() -> None:
    from tum_mcp.course.checks.answers import compare

    def check(cells: dict) -> tuple[list[str], int]:
        runs = {"primary": [{"@grid": {"maze:2:1": ""}}, {"@grid": cells}]}
        return compare(grid_walk(), {"walkthroughs": {"maze": runs}})

    assert check({"maze:2:1": "1", "maze:1:1": "S"}) == ([], 3)
    assert "cell maze:2:1 shows '1', the key computes '2'" in check({"maze:2:1": "2"})[0][0]
