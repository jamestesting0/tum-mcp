"""Prepared response contracts: bounded checks, never program or proof execution."""

from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_content import DiagramBlock, Option, PlotBlock, Text
from tum_mcp.study_models import Key


class ChoiceCheck(Frozen):
    kind: Literal["choice"]
    options: tuple[Option, ...] = Field(min_length=4, max_length=4)
    correct: Key

    @model_validator(mode="after")
    def distinct(self) -> "ChoiceCheck":
        keys = {item.key for item in self.options}
        texts = {item.text.strip().casefold() for item in self.options}
        if len(keys) != 4 or len(texts) != 4 or self.correct not in keys:
            raise ValueError("Use four distinct choices and a declared correct key.")
        return self


class NumericCheck(Frozen):
    """A number worked out on paper, then compared with the shown answer."""

    kind: Literal["numeric"]
    answer: FiniteFloat = Field(strict=True)
    unit: Text | None = None
    feedback: Text


class SelfCheck(Frozen):
    kind: Literal["self_check"]
    format: Literal["text", "code"] = "text"
    language: str | None = Field(default=None, min_length=1, max_length=30)
    starter_code: str | None = Field(default=None, min_length=1, max_length=20000)
    rubric: tuple[Text, ...] = Field(min_length=1, max_length=12)
    model_answer: Text

    @model_validator(mode="after")
    def code_only(self) -> "SelfCheck":
        if self.format != "code" and (self.language or self.starter_code):
            raise ValueError("Language and starter code belong to code responses only.")
        return self


class GivenCell(Frozen):
    kind: Literal["given"]
    text: Text


class NumericCell(Frozen):
    kind: Literal["numeric"]
    key: Key
    answer: FiniteFloat = Field(strict=True)
    unit: Text | None = None


class TextCell(Frozen):
    kind: Literal["text"]
    key: Key
    answer: Text


Cell = Annotated[GivenCell | NumericCell | TextCell, Field(discriminator="kind")]


class TableRow(Frozen):
    label: Text
    cells: tuple[Cell, ...] = Field(min_length=1, max_length=8)


class TableCheck(Frozen):
    kind: Literal["table"]
    caption: Text
    columns: tuple[Text, ...] = Field(min_length=1, max_length=8)
    rows: tuple[TableRow, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def cells(self) -> "TableCheck":
        keys = [cell.key for row in self.rows for cell in row.cells if cell.kind != "given"]
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("Use distinct keys for every editable table cell.")
        if any(len(row.cells) != len(self.columns) for row in self.rows):
            raise ValueError("Every row must match the table columns.")
        if len({row.label for row in self.rows}) != len(self.rows):
            raise ValueError("Table row labels must be distinct.")
        return self


class GraphCheck(Frozen):
    kind: Literal["graph"]
    graph: DiagramBlock
    mode: Literal["nodes", "edges", "path"]
    answers: tuple[tuple[Key, ...], ...] = Field(min_length=1, max_length=20)
    feedback: Text

    @model_validator(mode="after")
    def linked_answers(self) -> "GraphCheck":
        nodes = {node.key for node in self.graph.nodes}
        edges = {f"{edge.start}--{edge.end}" for edge in self.graph.edges}
        if len(edges) != len(self.graph.edges):
            raise ValueError("Graph checks require distinct edges.")
        allowed = edges if self.mode == "edges" else nodes
        for answer in self.answers:
            if not answer or len(answer) > 100 or not set(answer) <= allowed:
                raise ValueError("Graph answers must reference displayed nodes or edges.")
            if self.mode != "path" and len(set(answer)) != len(answer):
                raise ValueError("Graph selection answers must be distinct.")
            if self.mode == "path":
                for start, end in zip(answer, answer[1:], strict=False):
                    if not any(
                        (edge.start == start and edge.end == end)
                        or (not edge.directed and edge.start == end and edge.end == start)
                        for edge in self.graph.edges
                    ):
                        raise ValueError("A graph path must follow the displayed edges.")
        return self


class PlotCheck(Frozen):
    kind: Literal["plot"]
    plot: PlotBlock
    x_values: tuple[FiniteFloat, ...] = Field(min_length=2, max_length=20)
    answer: tuple[FiniteFloat, ...] = Field(min_length=2, max_length=20)
    tolerance: FiniteFloat = Field(ge=0, strict=True)
    snap: FiniteFloat = Field(default=1, gt=0)
    feedback: Text

    @model_validator(mode="after")
    def coordinates(self) -> "PlotCheck":
        if len(self.x_values) != len(self.answer) or list(self.x_values) != sorted(
            set(self.x_values)
        ):
            raise ValueError("Use distinct increasing x positions and one target y per position.")
        if any(not self.plot.x_min <= x <= self.plot.x_max for x in self.x_values):
            raise ValueError("Response x positions must fit the plot.")
        if any(not self.plot.y_min <= y <= self.plot.y_max for y in self.answer):
            raise ValueError("Response y targets must fit the plot.")
        return self


class TextCheck(Frozen):
    """A short answer, such as a name or one line of code, compared with the shown answer."""

    kind: Literal["text"]
    format: Literal["text", "code"] = "text"
    language: str | None = Field(default=None, min_length=1, max_length=30)
    answer: Annotated[str, Field(min_length=1, max_length=500)]
    feedback: Text

    @model_validator(mode="after")
    def code_language(self) -> "TextCheck":
        if self.format != "code" and self.language:
            raise ValueError("Language belongs to code answers only.")
        return self


Check = Annotated[
    ChoiceCheck | NumericCheck | SelfCheck | TableCheck | GraphCheck | PlotCheck | TextCheck,
    Field(discriminator="kind"),
]
