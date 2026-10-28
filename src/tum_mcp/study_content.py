"""Source-linked study content with editable LaTeX and legacy MathML inputs."""

from typing import Annotated, Literal, assert_never

from pydantic import AfterValidator, Field, FiniteFloat, JsonValue, field_validator, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_math import compile_latex, safe_mathml, validate_inline
from tum_mcp.study_models import Digest, Key

Text = Annotated[str, Field(min_length=1, max_length=10000), AfterValidator(validate_inline)]


class Objective(Frozen):
    key: Key
    text: Text


class Sourced(Frozen):
    title: Text
    sources: tuple[Key, ...] = Field(min_length=1)


class TextBlock(Sourced):
    kind: Literal["text"]
    paragraphs: tuple[Text, ...] = ()
    points: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def nonempty(self) -> "TextBlock":
        if not self.paragraphs and not self.points:
            raise ValueError("A text section needs an explanation.")
        return self


class Symbol(Frozen):
    symbol: Text
    meaning: Text


class FormulaBlock(Sourced):
    kind: Literal["formula"]
    mathml: Annotated[str, Field(max_length=20000)] | None = None
    latex: Annotated[str, Field(min_length=1, max_length=5000)] | None = None
    plain: Text
    symbols: tuple[Symbol, ...] = Field(min_length=1, max_length=30)
    conditions: Text

    @field_validator("mathml")
    @classmethod
    def safe_math(cls, value: str | None) -> str | None:
        if value is not None:
            safe_mathml(value)
        return value

    @model_validator(mode="after")
    def expression(self) -> "FormulaBlock":
        if (self.latex is None) == (self.mathml is None):
            raise ValueError("Supply LaTeX or legacy MathML, not both.")
        if self.latex is not None:
            compile_latex(self.latex)
        return self


class TableBlock(Sourced):
    kind: Literal["table"]
    columns: tuple[Text, ...] = Field(min_length=2, max_length=8)
    rows: tuple[tuple[Text, ...], ...] = Field(min_length=1, max_length=100)
    caption: Text

    @model_validator(mode="after")
    def rectangular(self) -> "TableBlock":
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Every table row must match the columns.")
        return self


class CodeBlock(Sourced):
    kind: Literal["code"]
    language: Annotated[str, Field(min_length=1, max_length=30)]
    code: Annotated[str, Field(min_length=1, max_length=20000)]
    explanation: Text
    line_numbers: bool = False


class Node(Frozen):
    key: Key
    label: Annotated[str, Field(min_length=1, max_length=30)]
    x: float = Field(ge=30, le=570)
    y: float = Field(ge=30, le=290)
    shape: Literal["circle", "box"] = "circle"

    @model_validator(mode="after")
    def fits(self) -> "Node":
        if self.shape == "circle" and len(self.label) > 4:
            raise ValueError("Use a box for labels longer than four characters.")
        if self.shape == "box" and not 70 <= self.x <= 530:
            raise ValueError("Keep a labelled box inside the diagram canvas.")
        return self


class Edge(Frozen):
    start: Key
    end: Key
    directed: bool = False
    label: Annotated[str, Field(max_length=50)] = ""


class Frame(Frozen):
    caption: Text
    active: tuple[Key, ...] = ()
    frontier: tuple[Key, ...] = ()
    visited: tuple[Key, ...] = ()


class DiagramBlock(Sourced):
    kind: Literal["diagram"]
    description: Text
    nodes: tuple[Node, ...] = Field(min_length=1, max_length=30)
    edges: tuple[Edge, ...] = Field(max_length=80)
    frames: tuple[Frame, ...] = Field(min_length=1, max_length=100)
    state_labels: Literal["traversal", "caption"] = "traversal"

    @model_validator(mode="after")
    def linked(self) -> "DiagramBlock":
        ids = {node.key for node in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("Diagram nodes must have unique keys.")
        if any(edge.start not in ids or edge.end not in ids for edge in self.edges):
            raise ValueError("Diagram edge references an unknown node.")
        if any(edge.start == edge.end for edge in self.edges):
            raise ValueError("Self-loop diagrams need a renderer extension before use.")
        if any(
            not set(frame.active + frame.frontier + frame.visited) <= ids for frame in self.frames
        ):
            raise ValueError("Diagram frame references an unknown node.")
        return self


class PlotPoint(Frozen):
    x: FiniteFloat = Field(ge=-1e12, le=1e12)
    y: FiniteFloat = Field(ge=-1e12, le=1e12)


class PlotSeries(Frozen):
    key: Key
    label: Text
    points: tuple[PlotPoint, ...] = Field(min_length=2, max_length=200)


class PlotBlock(Sourced):
    kind: Literal["plot"]
    description: Text
    x_label: Text = Field(max_length=30)
    y_label: Text = Field(max_length=30)
    x_min: FiniteFloat = Field(ge=-1e12, le=1e12)
    x_max: FiniteFloat = Field(ge=-1e12, le=1e12)
    y_min: FiniteFloat = Field(ge=-1e12, le=1e12)
    y_max: FiniteFloat = Field(ge=-1e12, le=1e12)
    series: tuple[PlotSeries, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def bounds(self) -> "PlotBlock":
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("Plot axes require increasing bounds.")
        if len({line.key for line in self.series}) != len(self.series):
            raise ValueError("Plot series keys must be distinct.")
        if any(
            not (self.x_min <= point.x <= self.x_max and self.y_min <= point.y <= self.y_max)
            for line in self.series
            for point in line.points
        ):
            raise ValueError("Plot points must fit the declared axes.")
        return self


Block = Annotated[
    TextBlock | FormulaBlock | TableBlock | DiagramBlock | CodeBlock | PlotBlock,
    Field(discriminator="kind"),
]


def render_blocks(blocks: tuple[Block, ...]) -> list[dict[str, JsonValue]]:
    """Project safe blocks for both workspaces without rewriting authored notation."""
    result: list[dict[str, JsonValue]] = []
    for block in blocks:
        value = block.model_dump(mode="json", exclude_none=True)
        match block:
            case FormulaBlock():
                value["mathml"] = block.mathml or compile_latex(block.latex or "")
            case TextBlock() | TableBlock() | CodeBlock() | DiagramBlock() | PlotBlock():
                pass
            case unreachable:
                assert_never(unreachable)
        result.append(value)
    return result


class Flashcard(Frozen):
    key: Key
    objective: Key
    front: Text
    back: Text
    sources: tuple[Key, ...] = Field(min_length=1)


class Option(Frozen):
    key: Key
    text: Text
    feedback: Text


class Question(Frozen):
    key: Key
    objective: Key
    prompt: Text
    level: Literal["recall", "apply", "reason"]
    options: tuple[Option, ...] = Field(min_length=3, max_length=5)
    correct: Key
    explanation: Text
    sources: tuple[Key, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def choices(self) -> "Question":
        ids = {item.key for item in self.options}
        if len(ids) != len(self.options) or self.correct not in ids:
            raise ValueError("Question needs distinct options and one correct key.")
        if len({item.text.strip().casefold() for item in self.options}) != len(ids):
            raise ValueError("Question options must have different meanings/text.")
        return self


class SourceVersion(Frozen):
    key: Key
    sha256: Digest


class Unit(Frozen):
    key: Key
    path: tuple[Annotated[str, Field(min_length=1, max_length=150)], ...] = Field(
        default=(), max_length=4
    )
    label: Text
    title: Text
    summary: Text
    minutes: int = Field(ge=1, le=240)
    objectives: tuple[Objective, ...] = Field(min_length=1, max_length=12)
    sources: tuple[SourceVersion, ...] = Field(min_length=1)
    blocks: tuple[Block, ...] = Field(min_length=1, max_length=40)
    flashcards: tuple[Flashcard, ...] = Field(min_length=1, max_length=80)
    questions: tuple[Question, ...] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def coverage(self) -> "Unit":
        source_ids = {source.key for source in self.sources}
        objectives = {objective.key for objective in self.objectives}
        for items in (self.objectives, self.sources, self.flashcards, self.questions):
            if len({item.key for item in items}) != len(items):
                raise ValueError("Unit item keys must be unique within their collection.")
        for item in (*self.blocks, *self.flashcards, *self.questions):
            if not set(item.sources) <= source_ids:
                raise ValueError("Unit cites an undeclared source.")
        if any(item.objective not in objectives for item in (*self.flashcards, *self.questions)):
            raise ValueError("Assessment references an unknown learning objective.")
        if {question.objective for question in self.questions} != objectives:
            raise ValueError("Each learning objective needs a practice question.")
        return self


class StudyContent(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    organization: Literal["lectures", "weeks", "topics"]
    introduction: Text
    units: tuple[Unit, ...] = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def unit_keys(self) -> "StudyContent":
        if len({unit.key for unit in self.units}) != len(self.units):
            raise ValueError("Study units must have unique keys.")
        return self
