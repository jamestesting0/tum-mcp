import math

import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.study_content import Block, compile_formulas
from tum_mcp.study_plot import compile_expression, sample

BLOCK = TypeAdapter(Block)


def diagram(**overrides: object) -> dict:
    value = {
        "kind": "diagram",
        "title": "One-state MDP",
        "sources": ["s"],
        "description": "Stop ends in T; continue stays in S.",
        "nodes": [
            {"key": "s", "label": "S", "row": 0, "col": 0},
            {"key": "t", "label": "T", "row": 0, "col": 1},
        ],
        "edges": [
            {"start": "s", "end": "t", "directed": True, "label": "stop: 3"},
            {"start": "s", "end": "s", "directed": True, "label": "continue: 1"},
        ],
        "frames": [{"caption": "Stop earns 3; continue earns 1."}],
    }
    return value | overrides


def test_a_lattice_diagram_may_loop_back_to_a_node() -> None:
    block = BLOCK.validate_python(diagram())
    assert [(node.row, node.col) for node in block.nodes] == [(0, 0), (0, 1)]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            diagram(
                nodes=[
                    {"key": "s", "label": "S", "row": 0, "col": 0},
                    {"key": "t", "label": "T", "row": 0, "col": 0},
                ]
            ),
            "own row and column",
        ),
        (
            diagram(edges=[{"start": "s", "end": "t"}, {"start": "s", "end": "t"}]),
            "each diagram edge once",
        ),
        (diagram(nodes=[{"key": "s", "label": "S", "row": 6, "col": 0}]), "less than or equal"),
    ],
)
def test_lattice_diagrams_reject_shared_cells_and_repeated_edges(value: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        BLOCK.validate_python(value)


def plot(**overrides: object) -> dict:
    value = {
        "kind": "plot",
        "title": "1/x",
        "sources": ["s"],
        "description": "y = 1/x has no value at x = 0.",
        "x_label": "x",
        "y_label": "y = 1/x",
        "x_min": -3,
        "x_max": 3,
        "y_min": -5,
        "y_max": 5,
        "series": [{"key": "f", "label": "1/x", "function": "1/x"}],
    }
    return value | overrides


def test_a_function_is_sampled_at_build_into_pieces_split_at_its_pole() -> None:
    built = compile_formulas(BLOCK.validate_python(plot()).model_dump(mode="json"))
    pieces = built["series"][0]["pieces"]
    assert len(pieces) == 2
    assert max(x for x, _ in pieces[0]) < 0 < min(x for x, _ in pieces[1])
    assert all(-5.2 <= y <= 5.2 for piece in pieces for _, y in piece)


def test_typed_series_areas_notes_and_a_log_axis_validate() -> None:
    block = BLOCK.validate_python(
        plot(
            y_label="nodes",
            x_min=0,
            x_max=4,
            y_min=1,
            y_max=10000,
            y_scale="log",
            legend="direct",
            series=[
                {
                    "key": "a",
                    "label": "b = 3",
                    "style": "markers",
                    "points": [{"x": d, "y": 3**d} for d in range(5)],
                },
                {"key": "f", "label": "2^x", "function": "2^x"},
            ],
            areas=[{"series": "f", "x_from": 1, "x_to": 2, "label": "area"}],
            notes=[{"x": 2, "y": 9, "text": "3² = 9"}],
        )
    )
    assert block.y_scale == "log"
    assert block.sampled()[1][0][0][1] == pytest.approx(1)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (plot(y_label="\\(y\\)"), "Unicode"),
        (plot(y_min=0, y_scale="log"), "above zero"),
        (
            plot(
                series=[{"key": "f", "label": "f", "function": "x", "points": [{"x": 0, "y": 0}]}]
            ),
            "either points or a function",
        ),
        (plot(series=[{"key": "f", "label": "f", "function": "__import__('os')"}]), "may use only"),
        (
            plot(series=[{"key": "f", "label": "f", "function": "x", "style": "stems"}]),
            "drawn as a line",
        ),
        (
            plot(
                series=[
                    {
                        "key": "s",
                        "label": "s",
                        "style": "steps",
                        "points": [{"x": 1, "y": 0}, {"x": 0, "y": 1}],
                    }
                ]
            ),
            "increasing x",
        ),
        (plot(areas=[{"series": "missing", "x_from": 0, "x_to": 1}]), "under a line series"),
        (plot(notes=[{"x": 9, "y": 0, "text": "outside"}]), "inside the axes"),
    ],
)
def test_plots_reject_latex_labels_bad_functions_and_misplaced_marks(
    value: dict, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        BLOCK.validate_python(value)


def test_the_sampler_survives_overflow_and_domain_errors() -> None:
    assert compile_expression("9^9^9")(1.0) is None
    assert compile_expression("sqrt(x)")(-1.0) is None
    pieces = sample("floor(x)", (-2, 2), (-3, 3))
    assert len(pieces) >= 4
    assert all(math.isclose(y, math.floor(x)) for piece in pieces for x, y in piece[1:-1])
