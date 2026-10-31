"""Source-linked study content with editable LaTeX and legacy MathML inputs."""

import re
from collections.abc import Iterator
from typing import Annotated, Literal, assert_never

from pydantic import AfterValidator, Field, FiniteFloat, JsonValue, field_validator, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_figures import FIGURE_IMAGE, safe_svg
from tum_mcp.study_math import INLINE_SPANS, compile_latex, safe_mathml, validate_inline
from tum_mcp.study_models import Digest, Key, PageRange
from tum_mcp.study_plot import compile_expression, sample

Text = Annotated[str, Field(min_length=1, max_length=10000), AfterValidator(validate_inline)]
Label = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(validate_inline)]


class Objective(Frozen):
    key: Key
    text: Text


class Sourced(Frozen):
    # Without a title the block continues the section above it, under that heading.
    title: Text | None = None
    # 1 opens a section, 2 a subsection, 3 a sub-subsection; titled blocks never skip a level.
    level: Literal[1, 2, 3] = 1
    sources: tuple[Key, ...] = Field(min_length=1)
    # An address for links into this block, unique within its unit or exercise.
    key: Key | None = None
    # The pages or slides of the cited material that this block draws on.
    pages: PageRange | None = None


class TextBlock(Sourced):
    kind: Literal["text"]
    paragraphs: tuple[Text, ...] = ()
    # A hard idea one claim at a time, shown as a numbered sequence after the paragraphs.
    steps: tuple[Text, ...] = Field(default=(), max_length=12)
    points: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def nonempty(self) -> "TextBlock":
        if not self.paragraphs and not self.steps and not self.points:
            raise ValueError("A text section needs an explanation.")
        return self


class Symbol(Frozen):
    symbol: Text
    meaning: Text


class DefinitionBlock(Sourced):
    """A term students must learn, set apart from explanation; its title defaults to the term."""

    kind: Literal["definition"]
    term: Label
    statement: Text
    conditions: tuple[Text, ...] = Field(default=(), max_length=6)


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


LineRange = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,4}(-[1-9][0-9]{0,4})?$")]
FilePath = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*(/[A-Za-z0-9_][A-Za-z0-9_.\-]*)*$",
    ),
]


def line_span(value: str) -> tuple[int, int]:
    first, _, last = value.partition("-")
    return int(first), int(last or first)


def check_lines(value: str, code: str, where: str) -> None:
    first, last = line_span(value)
    if first > last or last > code.count("\n") + 1:
        raise ValueError(f"Lines {value} are outside {where}.")


class CodeStep(Frozen):
    """One stop of a walkthrough: the lines to look at and what they do."""

    lines: LineRange
    note: Text


class CodeBlock(Sourced):
    kind: Literal["code"]
    language: Annotated[str, Field(min_length=1, max_length=30)]
    code: Annotated[str, Field(min_length=1, max_length=20000)]
    explanation: Text
    line_numbers: bool = False
    walkthrough: tuple[CodeStep, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def steps_fit(self) -> "CodeBlock":
        for step in self.walkthrough:
            check_lines(step.lines, self.code, "the code")
        return self


class ProjectFile(Frozen):
    path: FilePath
    code: Annotated[str, Field(max_length=50000)]
    editable: bool = False
    language: Annotated[str, Field(min_length=1, max_length=30)] | None = None


class FilesBlock(Sourced):
    """A small project, such as an Artemis exercise's files, opened in a light code workspace."""

    kind: Literal["files"]
    key: Key
    description: Text
    files: tuple[ProjectFile, ...] = Field(min_length=1, max_length=60)
    open: FilePath | None = None

    @model_validator(mode="after")
    def tree(self) -> "FilesBlock":
        paths = [item.path for item in self.files]
        if len(set(paths)) != len(paths):
            raise ValueError("Workspace file paths must be distinct.")
        if any(other.startswith(f"{path}/") for path in paths for other in paths):
            raise ValueError("A workspace path cannot be both a file and a folder.")
        if self.open is not None and self.open not in paths:
            raise ValueError("The workspace opens a file it does not contain.")
        if sum(len(item.code) for item in self.files) > 400_000:
            raise ValueError("Keep a workspace below 400,000 characters of code.")
        return self


class TreeNode(Frozen):
    """One entry of a hierarchy; `folder` and `file` entries show file-system icons."""

    label: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(validate_inline)]
    note: Annotated[str, Field(max_length=40), AfterValidator(validate_inline)] = ""
    kind: Literal["item", "folder", "file"] = "item"
    children: "tuple[TreeNode, ...]" = Field(default=(), max_length=30)


def tree_nodes(item: TreeNode, depth: int = 0) -> Iterator[tuple[TreeNode, int]]:
    yield item, depth
    for child in item.children:
        yield from tree_nodes(child, depth + 1)


class FigureBlock(Sourced):
    """A picture of what the idea looks like: an SVG drawing or an image in the app's figures/."""

    kind: Literal["figure"]
    alt: Text
    caption: Text | None = None
    svg: str | None = Field(default=None, max_length=40000)
    image: str | None = None

    @model_validator(mode="after")
    def drawn(self) -> "FigureBlock":
        if (self.svg is None) == (self.image is None):
            raise ValueError("A figure has either svg or image.")
        if self.image is not None and not FIGURE_IMAGE.fullmatch(self.image):
            raise ValueError("A figure image is a file in figures/ ending .png, .jpg or .webp.")
        if self.svg is not None:
            safe_svg(self.svg)
        return self


class TreeBlock(Sourced):
    """A hierarchy drawn as an indented tree: a file structure, an object tree or a call tree."""

    kind: Literal["tree"]
    # Optional: the tree is readable text itself, so a caption only says what to notice.
    description: Text | None = None
    root: TreeNode

    @model_validator(mode="after")
    def bounded(self) -> "TreeBlock":
        found = list(tree_nodes(self.root))
        if len(found) > 120 or max(depth for _, depth in found) > 8:
            raise ValueError("Keep a tree to at most 120 entries and 8 levels.")
        if any(item.kind == "file" and item.children for item, _ in found):
            raise ValueError("A file entry of a tree cannot contain other entries.")
        return self


class CodeRef(Frozen):
    """A step's pointer into the question's workspace: a file and optionally its lines."""

    path: FilePath
    lines: LineRange | None = None


def project_files(blocks: "tuple[Block, ...]") -> dict[str, ProjectFile]:
    files: dict[str, ProjectFile] = {}
    for block in blocks:
        if isinstance(block, FilesBlock):
            for item in block.files:
                if item.path in files:
                    raise ValueError(f"{item.path} appears in two workspaces of one question.")
                files[item.path] = item
    return files


def check_code_refs(files: dict[str, ProjectFile], refs: "tuple[CodeRef, ...]") -> None:
    for ref in refs:
        item = files.get(ref.path)
        if item is None:
            raise ValueError(f"The step refers to {ref.path}, which the question does not show.")
        if ref.lines:
            check_lines(ref.lines, item.code, ref.path)


def check_target_file(files: dict[str, ProjectFile], path: str) -> None:
    item = files.get(path)
    if item is None or not item.editable:
        raise ValueError(
            f"A code step writes into {path}, which must be an editable workspace file."
        )


class Node(Frozen):
    """A node on the diagram's lattice: the app sizes it from its label and spaces the cells."""

    key: Key
    label: Annotated[str, Field(min_length=1, max_length=40)]
    row: int = Field(ge=0, le=5)
    col: int = Field(ge=0, le=5)
    shape: Literal["circle", "box"] = "circle"

    @model_validator(mode="after")
    def fits(self) -> "Node":
        if self.shape == "circle" and len(self.label) > 4:
            raise ValueError("Use a box for labels longer than four characters.")
        return self


class Edge(Frozen):
    start: Key
    end: Key
    directed: bool = False
    label: Annotated[str, Field(max_length=50)] = ""


class StateRow(Frozen):
    """One named part of an algorithm's state at a step, such as its queue or a domain."""

    label: Label
    value: Annotated[str, Field(min_length=1, max_length=300), AfterValidator(validate_inline)]


class EdgeRef(Frozen):
    start: Key
    end: Key


class Frame(Frozen):
    caption: Text
    active: tuple[Key, ...] = ()
    frontier: tuple[Key, ...] = ()
    visited: tuple[Key, ...] = ()
    state: tuple[StateRow, ...] = Field(default=(), max_length=6)
    edges: tuple[EdgeRef, ...] = Field(default=(), max_length=20)


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
        cells = [(node.row, node.col) for node in self.nodes]
        if len(set(cells)) != len(cells):
            raise ValueError("Each diagram node needs its own row and column.")
        if len({(edge.start, edge.end) for edge in self.edges}) != len(self.edges):
            raise ValueError("Draw each diagram edge once.")
        if any(
            not set(frame.active + frame.frontier + frame.visited) <= ids for frame in self.frames
        ):
            raise ValueError("Diagram frame references an unknown node.")
        pairs = {(edge.start, edge.end) for edge in self.edges}
        pairs |= {(edge.end, edge.start) for edge in self.edges if not edge.directed}
        if any(
            (item.start, item.end) not in pairs for frame in self.frames for item in frame.edges
        ):
            raise ValueError("Diagram frame highlights an edge the diagram does not draw.")
        for frame in self.frames:
            if len({row.label for row in frame.state}) != len(frame.state):
                raise ValueError("Each state row in a frame needs its own label.")
        return self


class PlotPoint(Frozen):
    x: FiniteFloat = Field(ge=-1e12, le=1e12)
    y: FiniteFloat = Field(ge=-1e12, le=1e12)


class PlotSeries(Frozen):
    """Data `points` or a `function` of x sampled at build. `style` says how it is drawn:
    `line`, `markers` (line with a dot per point), `points`, `steps` (each value holds until
    the next x; a CDF) or `stems` (a dot on a line per value; a PMF)."""

    key: Key
    label: Text
    points: tuple[PlotPoint, ...] = Field(default=(), max_length=200)
    function: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    style: Literal["line", "markers", "points", "steps", "stems"] = "line"
    values: bool = False

    @model_validator(mode="after")
    def drawn(self) -> "PlotSeries":
        if (self.function is None) == (not self.points):
            raise ValueError("A plot series has either points or a function.")
        if self.function is not None:
            if self.style != "line" or self.values:
                raise ValueError("A function series is drawn as a line without value labels.")
            compile_expression(self.function)
        elif len(self.points) < (1 if self.style in ("points", "stems") else 2):
            raise ValueError("A line needs at least two points.")
        xs = [point.x for point in self.points]
        if self.style in ("steps", "stems", "markers") and xs != sorted(set(xs)):
            raise ValueError("Steps, stems and markers need distinct increasing x values.")
        return self


class PlotArea(Frozen):
    """Shade under a series between two x values, such as a probability under a density."""

    series: Key
    x_from: FiniteFloat
    x_to: FiniteFloat
    label: Annotated[str, Field(max_length=30), AfterValidator(validate_inline)] = ""


class PlotNote(Frozen):
    """A marked point with a short label, such as the value the text is about."""

    x: FiniteFloat
    y: FiniteFloat
    text: Annotated[str, Field(min_length=1, max_length=40), AfterValidator(validate_inline)]


AxisLabel = Annotated[str, Field(min_length=1, max_length=30), AfterValidator(validate_inline)]
AxisTicks = tuple[Annotated[float, Field(allow_inf_nan=False)], ...]


class PlotBlock(Sourced):
    kind: Literal["plot"]
    description: Text
    x_label: AxisLabel
    y_label: AxisLabel
    x_min: FiniteFloat = Field(ge=-1e12, le=1e12)
    x_max: FiniteFloat = Field(ge=-1e12, le=1e12)
    y_min: FiniteFloat = Field(ge=-1e12, le=1e12)
    y_max: FiniteFloat = Field(ge=-1e12, le=1e12)
    y_scale: Literal["linear", "log"] = "linear"
    x_ticks: AxisTicks = Field(default=(), max_length=12)
    y_ticks: AxisTicks = Field(default=(), max_length=12)
    series: tuple[PlotSeries, ...] = Field(default=(), max_length=5)
    areas: tuple[PlotArea, ...] = Field(default=(), max_length=3)
    notes: tuple[PlotNote, ...] = Field(default=(), max_length=4)
    legend: Literal["auto", "direct"] = "auto"

    @model_validator(mode="after")
    def bounds(self) -> "PlotBlock":
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("Plot axes require increasing bounds.")
        if self.y_scale == "log" and self.y_min <= 0:
            raise ValueError("A log axis starts above zero.")
        for label in (self.x_label, self.y_label):
            if "\\(" in label or "$" in label:
                raise ValueError("Write axis labels in Unicode (σ(z), x²), not LaTeX.")
        if len({line.key for line in self.series}) != len(self.series):
            raise ValueError("Plot series keys must be distinct.")

        def inside(x: float, y: float) -> bool:
            return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

        if any(not inside(point.x, point.y) for line in self.series for point in line.points):
            raise ValueError("Plot points must fit the declared axes.")
        if any(not inside(note.x, note.y) for note in self.notes):
            raise ValueError("Plot notes must sit inside the axes.")
        if any(not self.x_min <= tick <= self.x_max for tick in self.x_ticks) or any(
            not self.y_min <= tick <= self.y_max for tick in self.y_ticks
        ):
            raise ValueError("Plot ticks must lie inside the axes.")
        keys = {line.key: line for line in self.series}
        for area in self.areas:
            line = keys.get(area.series)
            if line is None or line.style != "line":
                raise ValueError("A shaded area lies under a line series of the plot.")
            if not self.x_min <= area.x_from < area.x_to <= self.x_max:
                raise ValueError("A shaded area spans increasing x values inside the axes.")
        return self

    def sampled(self) -> list[list[list[list[float]]]]:
        """The visible pieces of each function series, one list per series (empty for data)."""
        return [
            [
                [[x, y] for x, y in piece]
                for piece in sample(
                    line.function,
                    (self.x_min, self.x_max),
                    (self.y_min, self.y_max),
                    log_y=self.y_scale == "log",
                )
            ]
            if line.function
            else []
            for line in self.series
        ]


UmlLine = Annotated[str, Field(min_length=1, max_length=120)]
UmlShort = Annotated[str, Field(max_length=20)]


class UmlMember(Frozen):
    """One attribute or operation in UML notation, such as `+ update(t: double): void`."""

    text: UmlLine
    static: bool = False
    abstract: bool = False


class UmlClass(Frozen):
    key: Key
    name: Annotated[str, Field(min_length=1, max_length=60)]
    stereotype: Literal["interface", "abstract", "enumeration"] | None = None
    attributes: tuple[UmlMember, ...] = Field(default=(), max_length=20)
    operations: tuple[UmlMember, ...] = Field(default=(), max_length=20)


class UmlRelation(Frozen):
    """`start` is the child, the whole (diamond) or the client; `end` the other side."""

    start: Key
    end: Key
    kind: Literal[
        "inheritance",
        "realization",
        "association",
        "directed_association",
        "aggregation",
        "composition",
        "dependency",
    ]
    label: Annotated[str, Field(max_length=40)] = ""
    start_multiplicity: UmlShort = ""
    end_multiplicity: UmlShort = ""


class UmlParticipant(Frozen):
    key: Key
    name: Annotated[str, Field(min_length=1, max_length=40)]
    kind: Literal["object", "actor"] = "object"


class UmlMessage(Frozen):
    start: Key
    end: Key
    text: Annotated[str, Field(min_length=1, max_length=80)]
    kind: Literal["call", "return", "async", "create"] = "call"


class UmlFragment(Frozen):
    """A combined fragment over messages `first`..`last` (0-based, inclusive)."""

    kind: Literal["loop", "alt", "opt", "par"]
    condition: Annotated[str, Field(max_length=60)] = ""
    first: int = Field(ge=0)
    last: int = Field(ge=0)


class UmlState(Frozen):
    """A state; `initial` and `final` are the UML pseudostates and need no name."""

    key: Key
    name: Annotated[str, Field(max_length=40)] = ""
    kind: Literal["state", "initial", "final"] = "state"
    activity: Annotated[str, Field(max_length=60)] = ""


class UmlTransition(Frozen):
    """A transition, labelled `event [guard] / action` in UML notation; it may loop."""

    start: Key
    end: Key
    label: Annotated[str, Field(max_length=60)] = ""


class FlowStep(Frozen):
    """One box of a flowchart: `start`/`end` terminals, an `action`, `io`, or a `decision`."""

    key: Key
    kind: Literal["start", "end", "action", "io", "decision"] = "action"
    text: Annotated[str, Field(min_length=1, max_length=80)]


class Flow(Frozen):
    """An arrow between flowchart steps; every exit of a decision carries its answer."""

    start: Key
    end: Key
    label: Annotated[str, Field(max_length=30)] = ""


class UmlBlock(Sourced):
    """A UML class, sequence or state diagram or a flowchart, laid out by the app."""

    kind: Literal["uml"]
    diagram: Literal["class", "sequence", "state", "flowchart"]
    description: Text
    classes: tuple[UmlClass, ...] = Field(default=(), max_length=20)
    relations: tuple[UmlRelation, ...] = Field(default=(), max_length=40)
    participants: tuple[UmlParticipant, ...] = Field(default=(), max_length=10)
    messages: tuple[UmlMessage, ...] = Field(default=(), max_length=40)
    fragments: tuple[UmlFragment, ...] = Field(default=(), max_length=10)
    states: tuple[UmlState, ...] = Field(default=(), max_length=20)
    transitions: tuple[UmlTransition, ...] = Field(default=(), max_length=40)
    steps: tuple[FlowStep, ...] = Field(default=(), max_length=24)
    flows: tuple[Flow, ...] = Field(default=(), max_length=40)

    @model_validator(mode="after")
    def consistent(self) -> "UmlBlock":
        if self.diagram != "state" and (self.states or self.transitions):
            raise ValueError("Only a UML state diagram has states and transitions.")
        if self.diagram != "flowchart" and (self.steps or self.flows):
            raise ValueError("Only a flowchart has steps and flows.")
        if self.diagram == "state":
            return self._state_machine()
        if self.diagram == "flowchart":
            return self._flowchart()
        if self.diagram == "class":
            if not self.classes or self.participants or self.messages or self.fragments:
                raise ValueError("A UML class diagram has classes and relations only.")
            keys = [item.key for item in self.classes]
            if len(set(keys)) != len(keys):
                raise ValueError("UML class keys must be distinct.")
            for relation in self.relations:
                if relation.start not in keys or relation.end not in keys:
                    raise ValueError("A UML relation names an unknown class.")
                if relation.start == relation.end and relation.kind in (
                    "inheritance",
                    "realization",
                ):
                    raise ValueError("A class cannot inherit from itself.")
            return self
        if not self.participants or not self.messages or self.classes or self.relations:
            raise ValueError("A UML sequence diagram has participants and messages only.")
        keys = [item.key for item in self.participants]
        if len(set(keys)) != len(keys):
            raise ValueError("UML participant keys must be distinct.")
        if any(item.start not in keys or item.end not in keys for item in self.messages):
            raise ValueError("A UML message names an unknown participant.")
        if any(
            item.first > item.last or item.last >= len(self.messages) for item in self.fragments
        ):
            raise ValueError("A UML fragment must cover existing messages in order.")
        return self

    def _flowchart(self) -> "UmlBlock":
        if not self.steps or self.classes or self.relations or self.participants or self.messages:
            raise ValueError("A flowchart has steps and flows only.")
        kinds = {item.key: item.kind for item in self.steps}
        if len(kinds) != len(self.steps):
            raise ValueError("Flowchart step keys must be distinct.")
        if list(kinds.values()).count("start") != 1 or "end" not in kinds.values():
            raise ValueError("A flowchart has one start and at least one end.")
        if len({(item.start, item.end) for item in self.flows}) != len(self.flows):
            raise ValueError("Draw each flowchart arrow once.")
        for item in self.flows:
            if item.start not in kinds or item.end not in kinds:
                raise ValueError("A flow names an unknown step.")
            if kinds[item.start] == "end" or kinds[item.end] == "start":
                raise ValueError("Flows leave the start and enter an end, never the reverse.")
        for key, kind in kinds.items():
            exits = [item for item in self.flows if item.start == key]
            if kind == "decision" and (len(exits) < 2 or not all(item.label for item in exits)):
                raise ValueError(
                    "A decision has at least two exits, each labelled with its answer."
                )
            if kind in ("start", "action", "io") and len(exits) != 1:
                raise ValueError("A start, action or input/output step has exactly one exit.")
        return self

    def _state_machine(self) -> "UmlBlock":
        if not self.states or self.classes or self.relations or self.participants or self.messages:
            raise ValueError("A UML state diagram has states and transitions only.")
        kinds = {item.key: item.kind for item in self.states}
        if len(kinds) != len(self.states):
            raise ValueError("UML state keys must be distinct.")
        if any(item.kind == "state" and not item.name for item in self.states):
            raise ValueError("Every UML state needs a name.")
        if sum(kind == "initial" for kind in kinds.values()) > 1:
            raise ValueError("A UML state diagram has at most one initial state.")
        for item in self.transitions:
            if item.start not in kinds or item.end not in kinds:
                raise ValueError("A UML transition names an unknown state.")
            if kinds[item.end] == "initial" or kinds[item.start] == "final":
                raise ValueError("Transitions leave the initial state and enter the final state.")
        return self


StepVisual = Annotated[
    TableBlock | DiagramBlock | PlotBlock | FigureBlock, Field(discriminator="kind")
]


class DerivationLine(Frozen):
    """One meaningful transformation; a line opening with a relation continues the one above."""

    latex: Annotated[str, Field(min_length=1, max_length=2000)]
    # Why this line follows: the rule, substitution or condition it uses.
    reason: Text | None = None
    # In a walkthrough, the state this line reaches, drawn beside it.
    visual: StepVisual | None = None

    @field_validator("latex")
    @classmethod
    def compiles(cls, value: str) -> str:
        compile_latex(value)
        return value


class DerivationGroup(Frozen):
    # The requested result this working computes, when one answer gives several.
    label: Label | None = None
    lines: tuple[DerivationLine, ...] = Field(min_length=1, max_length=24)


class DerivationBlock(Sourced):
    """Working shown line by line, aligned on its relations, each line with its reason."""

    kind: Literal["derivation"]
    groups: tuple[DerivationGroup, ...] = Field(min_length=1, max_length=8)
    # A walkthrough reveals one line at a time with Previous and Next, and the reader can
    # show every step at once; without it the whole working is shown.
    walkthrough: bool = False

    @model_validator(mode="after")
    def stepped(self) -> "DerivationBlock":
        lines = [line for group in self.groups for line in group.lines]
        if self.walkthrough and len(lines) < 2:
            raise ValueError("A walkthrough needs at least two lines to step through.")
        if not self.walkthrough and any(line.visual for line in lines):
            raise ValueError("Per-line visuals belong to a walkthrough; set walkthrough.")
        if len(self.groups) > 1 and not all(group.label for group in self.groups):
            raise ValueError("Label each group when one derivation works out several results.")
        return self


Block = Annotated[
    TextBlock
    | DefinitionBlock
    | FormulaBlock
    | DerivationBlock
    | TableBlock
    | DiagramBlock
    | CodeBlock
    | PlotBlock
    | UmlBlock
    | FilesBlock
    | TreeBlock
    | FigureBlock,
    Field(discriminator="kind"),
]


# Authored questions pair their text with at least one of these, because prose alone
# makes code, structures and calculations hard to picture.
VISUAL_KINDS = frozenset(
    {
        "formula",
        "derivation",
        "table",
        "diagram",
        "code",
        "plot",
        "uml",
        "files",
        "tree",
        "figure",
    }
)
VISUAL_RULE = (
    "a figure, code snippet, diagram, UML diagram, tree, formula, derivation, table or plot "
    "beside its text"
)


def has_visual(blocks: tuple[Block, ...]) -> bool:
    return any(block.kind in VISUAL_KINDS for block in blocks)


def check_heading_levels(blocks: tuple[Block, ...]) -> None:
    """Titled blocks form an outline: it starts at level 1 and descends one level at a time."""
    previous = 0
    for block in blocks:
        if block.kind == "definition" or not block.title:
            continue
        if block.level > previous + 1:
            raise ValueError(
                f"'{block.title}' is a level-{block.level} heading after level {previous}; "
                "headings start at level 1 and go one level deeper at a time."
            )
        previous = block.level


def render_blocks(blocks: tuple[Block, ...]) -> list[dict[str, JsonValue]]:
    """Project safe blocks for both workspaces without rewriting authored notation."""
    result: list[dict[str, JsonValue]] = []
    for block in blocks:
        value = block.model_dump(mode="json", exclude_none=True)
        match block:
            case FormulaBlock():
                value["mathml"] = block.mathml or compile_latex(block.latex or "")
            case DerivationBlock():
                for group, authored in zip(value["groups"], block.groups, strict=True):
                    for line, source in zip(group["lines"], authored.lines, strict=True):
                        line["mathml"] = compile_latex(source.latex)
                        if source.visual is not None:
                            line["visual"] = render_blocks((source.visual,))[0]
            case PlotBlock():
                for line, pieces in zip(value["series"], block.sampled(), strict=True):
                    if pieces:
                        line["pieces"] = pieces
            case (
                TextBlock()
                | DefinitionBlock()
                | TableBlock()
                | CodeBlock()
                | DiagramBlock()
                | UmlBlock()
                | FilesBlock()
                | TreeBlock()
                | FigureBlock()
            ):
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
    # The situation the question is about, shown beside it in Practice and Revision.
    # Optional: a question about a concept stands alone; a picture must carry information.
    blocks: tuple[Block, ...] = Field(default=(), max_length=3)
    options: tuple[Option, ...] = Field(min_length=3, max_length=5)
    correct: Key
    explanation: Text
    hint: Text | None = None
    sources: tuple[Key, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def choices(self) -> "Question":
        ids = {item.key for item in self.options}
        if len(ids) != len(self.options) or self.correct not in ids:
            raise ValueError("Question needs distinct options and one correct key.")
        if len({item.text.strip().casefold() for item in self.options}) != len(ids):
            raise ValueError("Question options must have different meanings/text.")
        if self.blocks and not has_visual(self.blocks):
            raise ValueError(f"A practice question's picture is {VISUAL_RULE}.")
        return self


class SourceVersion(Frozen):
    key: Key
    sha256: Digest


class ExploreMaterial(Frozen):
    key: Key
    title: Text
    sources: tuple[SourceVersion, ...] = Field(min_length=1)
    blocks: tuple[Block, ...] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def references(self) -> "ExploreMaterial":
        source_ids = {source.key for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("Explore source keys must be unique.")
        keys = [block.key for block in self.blocks]
        if None in keys or len(set(keys)) != len(keys):
            raise ValueError("Explore blocks need distinct stable keys.")
        if any(not set(block.sources) <= source_ids for block in self.blocks):
            raise ValueError("Explore cites an undeclared source.")
        check_heading_levels(self.blocks)
        return self


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
    # Lecture of the lectures this unit teaches, linked from the unit when prepared.
    lectures: tuple[Key, ...] = Field(default=(), max_length=6)
    explore: tuple[ExploreMaterial, ...] = Field(
        default=(), max_length=20, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def coverage(self) -> "Unit":
        source_ids = {source.key for source in self.sources}
        objectives = {objective.key for objective in self.objectives}
        for items in (self.objectives, self.sources, self.flashcards, self.questions, self.explore):
            if len({item.key for item in items}) != len(items):
                raise ValueError("Unit item keys must be unique within their collection.")
        cited = (*self.blocks, *self.flashcards, *self.questions)
        for item in (*cited, *(block for question in self.questions for block in question.blocks)):
            if not set(item.sources) <= source_ids:
                raise ValueError("Unit cites an undeclared source.")
        keys = [block.key for block in self.blocks if block.key]
        if len(set(keys)) != len(keys):
            raise ValueError("Block keys must be unique within a unit.")
        check_heading_levels(self.blocks)
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
        terms = [term.casefold() for term in self.definitions()]
        if len(set(terms)) != len(terms):
            raise ValueError("Define each term once across the course.")
        if unknown := term_markers(self.model_dump(mode="json")) - set(terms):
            raise ValueError(f"Marked terms need a definition block: {sorted(unknown)[:5]}.")
        return self

    def definitions(self) -> dict[str, dict[str, JsonValue]]:
        """Each defined term with where it is taught, for in-place explanations everywhere."""
        return {
            block.term: {
                "term": block.term,
                "statement": block.statement,
                "conditions": list(block.conditions),
                "unit": unit.key,
                "block": block.key,
                "sources": list(block.sources),
            }
            for unit in self.units
            for block in unit.blocks
            if isinstance(block, DefinitionBlock)
        }


# {{term}} marks a mention of a defined term; it opens the definition where it is used.
TERM_MARKER = re.compile(r"\{\{([^{}\n]{1,80})\}\}")
LITERAL_FIELDS = frozenset({"code", "starter_code", "latex", "mathml", "svg"})


def term_markers(value: JsonValue) -> set[str]:
    """Every marked term in authored text, outside code, inline code and math."""
    match value:
        case str():
            text = INLINE_SPANS.sub(" ", value)
            return {match[1].strip().casefold() for match in TERM_MARKER.finditer(text)}
        case list():
            return {term for item in value for term in term_markers(item)}
        case dict():
            return {
                term
                for field, item in value.items()
                if field not in LITERAL_FIELDS
                for term in term_markers(item)
            }
        case _:
            return set()


def compile_formulas(value: JsonValue) -> JsonValue:
    """Compile every formula's LaTeX and sample every plot function once at build, wherever
    the block sits (units, questions, exercise checks)."""
    match value:
        case dict():
            result = {key: compile_formulas(item) for key, item in value.items()}
            if isinstance(result.get("latex"), str) and "mathml" not in result:
                result["mathml"] = compile_latex(result["latex"])
            if result.get("kind") == "plot" and isinstance(result.get("series"), list):
                plot = PlotBlock.model_validate(
                    {
                        **result,
                        "series": [
                            {k: v for k, v in line.items() if k != "pieces"}
                            for line in result["series"]
                            if isinstance(line, dict)
                        ],
                    }
                )
                for line, pieces in zip(result["series"], plot.sampled(), strict=True):
                    if pieces and isinstance(line, dict):
                        line["pieces"] = pieces
            return result
        case list():
            return [compile_formulas(item) for item in value]
        case _:
            return value
