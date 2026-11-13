"""Source-linked study content with editable LaTeX and legacy MathML inputs."""

import re
from collections.abc import Iterator
from typing import Annotated, Literal, assert_never

from pydantic import (
    AfterValidator,
    Field,
    FiniteFloat,
    JsonValue,
    field_validator,
    model_validator,
)

from tum_mcp.course.content.figures import FIGURE_IMAGE, safe_svg
from tum_mcp.course.content.latex import (
    INLINE_SPANS,
    compile_latex,
    decorated_variants,
    normalize_symbol,
    symbol_occurs,
    validate_inline,
)
from tum_mcp.course.content.plot import compile_expression, sample
from tum_mcp.course.project.models import Digest, Key, PageRange
from tum_mcp.settings import Frozen

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
    # Optional depth beside the section title (an application, a deeper why). What a student
    # needs to follow the page stays in the text, never here.
    insight: (
        Annotated[str, Field(min_length=1, max_length=400), AfterValidator(validate_inline)] | None
    ) = None

    @model_validator(mode="after")
    def titled_insight(self) -> "Sourced":
        if self.insight and not self.title:
            raise ValueError("An insight sits beside a section title; give the block a title.")
        return self


class TextBlock(Sourced):
    kind: Literal["text"]
    paragraphs: tuple[Text, ...] = ()
    # A hard idea one claim at a time, shown as a numbered sequence after the paragraphs.
    steps: tuple[Text, ...] = Field(default=(), max_length=12)
    steps_marker: Literal["decimal", "lower-alpha"] = Field(
        default="decimal", exclude_if=lambda marker: marker == "decimal"
    )
    points: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def nonempty(self) -> "TextBlock":
        if not self.paragraphs and not self.steps and not self.points:
            raise ValueError("A text section needs an explanation.")
        return self


class Symbol(Frozen):
    symbol: Text
    meaning: Text


def declared_meanings(value: object) -> list[dict[str, str]]:
    """The variable meanings a context (a unit, an exercise, a pattern) declares, in document
    order: those of derivations and applied formulas. Formula blocks and cheatsheet formulas
    keep their own visible lists and do not count."""
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        if value.get("symbols") and (value.get("kind") == "derivation" or "math" in value):
            found.extend(value["symbols"])
        for item in value.values():
            found.extend(declared_meanings(item))
    elif isinstance(value, list | tuple):
        for item in value:
            found.extend(declared_meanings(item))
    return found


def resolve_meanings(context: object) -> None:
    """Give every derivation and applied formula of one context the declared meanings of the
    variables it contains, so a meaning is written once; a formula's own meaning wins."""
    declared: dict[str, dict[str, str]] = {}
    for item in declared_meanings(context):
        declared.setdefault(normalize_symbol(item["symbol"]), item)
    if not declared:
        return

    def visit(value: object) -> None:
        if isinstance(value, dict):
            formulas: list[str] = []
            if value.get("kind") == "derivation":
                formulas = [line["latex"] for group in value["groups"] for line in group["lines"]]
            elif isinstance(value.get("math"), list):
                formulas = [line for line in value["math"] if isinstance(line, str)]
            if formulas:
                own = list(value.get("symbols") or [])
                keys = {normalize_symbol(item["symbol"]) for item in own}
                own += [
                    item
                    for key, item in declared.items()
                    if key not in keys and any(symbol_occurs(f, item["symbol"]) for f in formulas)
                ]
                if own:
                    value["symbols"] = own
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(context)


def check_meanings(symbols: tuple[Symbol, ...], formulas: list[str], where: str) -> None:
    """Each listed variable appears in its formula as written, once per list."""
    seen: set[str] = set()
    for item in symbols:
        key = normalize_symbol(item.symbol)
        if key in seen:
            raise ValueError(f"{where} lists {item.symbol} twice.")
        seen.add(key)
        if not any(symbol_occurs(latex, item.symbol) for latex in formulas):
            raise ValueError(
                f"{where}: {item.symbol} does not appear in its formula; write the variable "
                "exactly as the formula spells it."
            )


def check_variants(formulas: list[str] | tuple[str, ...], symbols: list[str], where: str) -> None:
    """A decorated form of a listed variable (K_j^\\dagger beside K_j) needs its own meaning; the
    app never shows the plain variable's meaning for it."""
    for latex in formulas:
        if variants := decorated_variants(latex, symbols):
            raise ValueError(
                f"{where}: {variants[0]} has no meaning of its own; list it with what it means "
                "here."
            )


class DefinitionBlock(Sourced):
    """A term students must learn, set apart from explanation; its title defaults to the term."""

    kind: Literal["definition"]
    term: Label
    statement: Text
    conditions: tuple[Text, ...] = Field(default=(), max_length=6)


class FormulaBlock(Sourced):
    kind: Literal["formula"]
    latex: Annotated[str, Field(min_length=1, max_length=5000)]
    plain: Text
    symbols: tuple[Symbol, ...] = Field(min_length=1, max_length=30)
    # When the formula holds, only where that is not obvious.
    conditions: Text | None = None

    @field_validator("latex")
    @classmethod
    def compiles(cls, value: str) -> str:
        compile_latex(value)
        return value


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
    """A node on the diagram's lattice: the app sizes it from its label and spaces the cells.
    A tree diagram places its nodes from the edges instead, so its nodes give no cell."""

    key: Key
    label: Annotated[str, Field(min_length=1, max_length=40)]
    row: int | None = Field(default=None, ge=0, le=5, exclude_if=lambda value: value is None)
    col: int | None = Field(default=None, ge=0, le=5, exclude_if=lambda value: value is None)
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


class Region(Frozen):
    """A part of a figure image a step points at, in fractions of the image from its top left."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)
    label: Label | None = None

    @model_validator(mode="after")
    def inside(self) -> "Region":
        if self.x + self.w > 1.001 or self.y + self.h > 1.001:
            raise ValueError("A region lies inside its image: x + w and y + h are at most 1.")
        return self


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


def check_tree(nodes: tuple[Node, ...], edges: tuple[Edge, ...]) -> None:
    if any(node.row is not None or node.col is not None for node in nodes):
        raise ValueError("A tree diagram places its nodes from its edges; drop row and col.")
    if any(not edge.directed or edge.start == edge.end for edge in edges):
        raise ValueError("A tree's edges are directed from a parent to a child.")
    parents = [edge.end for edge in edges]
    if len(set(parents)) != len(parents):
        raise ValueError("In a tree each node has one parent; draw a repeated state as a new node.")
    roots = [node.key for node in nodes if node.key not in parents]
    if len(roots) != 1:
        raise ValueError("A tree diagram needs exactly one root.")
    children: dict[str, list[str]] = {}
    for edge in edges:
        children.setdefault(edge.start, []).append(edge.end)
    reached, waiting = set(), [roots[0]]
    while waiting:
        key = waiting.pop()
        reached.add(key)
        waiting.extend(children.get(key, []))
    if len(reached) != len(nodes):
        raise ValueError("Every node of a tree diagram hangs below its root.")


class DiagramBlock(Sourced):
    kind: Literal["diagram"]
    description: Text
    nodes: tuple[Node, ...] = Field(min_length=1, max_length=30)
    edges: tuple[Edge, ...] = Field(max_length=80)
    frames: tuple[Frame, ...] = Field(min_length=1, max_length=100)
    state_labels: Literal["traversal", "caption"] = "traversal"
    layout: Literal["lattice", "tree"] = Field(
        default="lattice",
        exclude_if=lambda value: value == "lattice",
        description=(
            "tree for a search, game or recursion tree: edges run parent to child in child "
            "order and the app places the levels; nodes then need no row or col."
        ),
    )

    @model_validator(mode="after")
    def linked(self) -> "DiagramBlock":
        ids = {node.key for node in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("Diagram nodes must have unique keys.")
        if any(edge.start not in ids or edge.end not in ids for edge in self.edges):
            raise ValueError("Diagram edge references an unknown node.")
        if self.layout == "tree":
            check_tree(self.nodes, self.edges)
        else:
            cells = [(node.row, node.col) for node in self.nodes]
            if any(row is None or col is None for row, col in cells):
                raise ValueError("Give each lattice node its row and column, or use a tree.")
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
    # Variables a reader may need to recall here; each opens its meaning in the formula.
    symbols: tuple[Symbol, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def stepped(self) -> "DerivationBlock":
        lines = [line for group in self.groups for line in group.lines]
        if self.walkthrough and len(lines) < 2:
            raise ValueError("A walkthrough needs at least two lines to step through.")
        if not self.walkthrough and any(line.visual for line in lines):
            raise ValueError("Per-line visuals belong to a walkthrough; set walkthrough.")
        if len(self.groups) > 1 and not all(group.label for group in self.groups):
            raise ValueError("Label each group when one derivation works out several results.")
        check_meanings(self.symbols, [line.latex for line in lines], "A derivation")
        return self


class Step(Frozen):
    """One step of a worked process: what is done and why, in the student's order."""

    # Consecutive steps sharing a subgoal form one stage of the process.
    subgoal: Label | None = None
    action: Annotated[str, Field(min_length=1, max_length=300), AfterValidator(validate_inline)]
    why: Annotated[str, Field(min_length=1, max_length=600), AfterValidator(validate_inline)]
    # The mistake a student makes at this moment, when there is a typical one.
    note: (
        Annotated[str, Field(min_length=1, max_length=400), AfterValidator(validate_inline)] | None
    ) = None
    # Seconds into the recording where the step is explained (lecture highlights only).
    at: FiniteFloat | None = Field(default=None, ge=0, le=28800)


def check_subgoals(steps: tuple[Step, ...]) -> None:
    seen: list[str | None] = []
    for step in steps:
        if not seen or seen[-1] != step.subgoal:
            if step.subgoal is not None and step.subgoal in seen:
                raise ValueError(
                    f"Subgoal '{step.subgoal}' returns after another one; keep its steps together."
                )
            seen.append(step.subgoal)


CellRef = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,2}:[1-9]$")]


class WalkStep(Step):
    """A step over the walkthrough's stage, with what the stage shows once it is done."""

    state: tuple[StateRow, ...] = Field(default=(), max_length=6)
    # A graph stage: the nodes and edges marked at this step.
    active: tuple[Key, ...] = ()
    frontier: tuple[Key, ...] = ()
    visited: tuple[Key, ...] = ()
    cutoff: tuple[Key, ...] = ()
    edges: tuple[EdgeRef, ...] = Field(default=(), max_length=20)
    node_values: dict[Key, Label] = Field(
        default_factory=dict,
        exclude_if=lambda value: not value,
        description=(
            "What the slide writes beside a node at this step, with its arithmetic "
            "(f = 140 + 253 = 393, a domain, a depth); keep node labels to the name."
        ),
    )
    visible_nodes: tuple[Key, ...] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "The nodes generated so far, so a search tree grows step by step. When omitted, "
            "every node is drawn and a tree's nodes no step has reached yet stay faint."
        ),
    )
    # A table stage: the rows filled so far and the cells this step changed ("row:column").
    # A formula stage: the lines of working written so far.
    shown: int | None = Field(default=None, ge=1)
    cells: tuple[CellRef, ...] = Field(default=(), max_length=20)
    # A code stage: the lines running at this step.
    lines: LineRange | None = None
    # A plot stage: the series drawn so far; a figure stage: the layers (SVG ids) shown.
    series: tuple[Key, ...] | None = None
    layers: tuple[Key, ...] | None = None
    regions: tuple[Region, ...] = Field(
        default=(),
        max_length=8,
        exclude_if=lambda value: not value,
        description=(
            "On a figure image: the parts this step works on, outlined while the rest dims "
            "(a tile and its goal square, a city on the lecture's map)."
        ),
    )
    frame: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "On a figure image: another crop from figures/ shown at this step, for a picture "
            "the lecture builds up over several slides."
        ),
    )


# A stage is the picture the steps move over; it borrows the visual it is, without the
# section fields (the walkthrough itself is the cited section).
class GraphStage(DiagramBlock):
    sources: tuple[Key, ...] = ()
    frames: tuple[Frame, ...] = Field(default=(), max_length=0)


class TableStage(TableBlock):
    sources: tuple[Key, ...] = ()


class CodeStage(CodeBlock):
    sources: tuple[Key, ...] = ()
    explanation: Text | None = None
    walkthrough: tuple[CodeStep, ...] = Field(default=(), max_length=0)


class FormulaStage(DerivationBlock):
    sources: tuple[Key, ...] = ()

    @model_validator(mode="after")
    def reasons_in_steps(self) -> "FormulaStage":
        if self.walkthrough or any(line.reason or line.visual for line in self.lines):
            raise ValueError("A formula stage is plain working; each step gives the reason.")
        return self

    @property
    def lines(self) -> list[DerivationLine]:
        return [line for group in self.groups for line in group.lines]


class PlotStage(PlotBlock):
    sources: tuple[Key, ...] = ()


class FigureStage(FigureBlock):
    sources: tuple[Key, ...] = ()


Stage = Annotated[
    GraphStage | TableStage | CodeStage | FormulaStage | PlotStage | FigureStage,
    Field(discriminator="kind"),
]
MARKS = {
    "diagram": {"active", "frontier", "visited", "cutoff", "edges", "node_values", "visible_nodes"},
    "table": {"shown", "cells"},
    "code": {"lines"},
    "derivation": {"shown"},
    "plot": {"series"},
    "figure": {"layers", "regions", "frame"},
}


def check_marks(stage: Stage | None, step: WalkStep) -> None:
    marked = {
        name for name in set().union(*MARKS.values()) if getattr(step, name) not in ((), None, {})
    }
    allowed = MARKS[stage.kind] if stage is not None else set()
    if extra := marked - allowed:
        where = f"a {stage.kind} stage" if stage is not None else "a walkthrough without a stage"
        raise ValueError(
            f"Step '{step.action}' marks {', '.join(sorted(extra))}, which {where} does not have."
        )
    if len({row.label for row in step.state}) != len(step.state):
        raise ValueError("Each state row in a step needs its own label.")
    match stage:
        case GraphStage():
            keys = {item.key for item in stage.nodes}
            pairs = {(edge.start, edge.end) for edge in stage.edges}
            pairs |= {(edge.end, edge.start) for edge in stage.edges if not edge.directed}
            marked = set(step.active + step.frontier + step.visited + step.cutoff)
            if not marked | set(step.node_values) | set(step.visible_nodes or ()) <= keys:
                raise ValueError(f"Step '{step.action}' marks a node the stage does not draw.")
            if any((edge.start, edge.end) not in pairs for edge in step.edges):
                raise ValueError(f"Step '{step.action}' marks an edge the stage does not draw.")
            if step.visible_nodes is not None:
                shown = set(step.visible_nodes)
                if not (marked | set(step.node_values)) <= shown or any(
                    not {edge.start, edge.end} <= shown for edge in step.edges
                ):
                    raise ValueError(f"Step '{step.action}' marks a node it does not show yet.")
        case TableStage():
            rows = step.shown or len(stage.rows)
            if rows > len(stage.rows) or any(
                int(row) > rows or int(column) > len(stage.columns)
                for row, _, column in (cell.partition(":") for cell in step.cells)
            ):
                raise ValueError(f"Step '{step.action}' marks a cell outside the shown rows.")
        case CodeStage():
            if step.lines is not None:
                check_lines(step.lines, stage.code, "the stage's code")
        case FormulaStage():
            if (step.shown or 0) > len(stage.lines):
                raise ValueError(f"Step '{step.action}' shows more lines than the working has.")
        case PlotStage():
            if not set(step.series or ()) <= {line.key for line in stage.series}:
                raise ValueError(f"Step '{step.action}' shows a series the plot does not have.")
        case FigureStage():
            if stage.svg is None and step.layers:
                raise ValueError("Figure layers are SVG groups; an image has none.")
            if stage.image is None and (step.regions or step.frame):
                raise ValueError("Regions and frames mark an image; a drawn figure uses layers.")
            if step.frame is not None and not FIGURE_IMAGE.fullmatch(step.frame):
                raise ValueError("A frame is a file in figures/ ending .png, .jpg or .webp.")
            if any(f'id="{layer}"' not in (stage.svg or "") for layer in step.layers or ()):
                raise ValueError(f"Step '{step.action}' shows a layer the figure does not draw.")
        case None:
            pass
        case unreachable:
            assert_never(unreachable)


class Variant(Frozen):
    """A second run over the same stage, such as another algorithm or another input."""

    label: Label
    steps: tuple[WalkStep, ...] = Field(min_length=2, max_length=40)


class WalkthroughBlock(Sourced):
    """A worked process step by step: each step's action and reason, over an optional stage
    (a graph, table, code, working, plot or figure) that shows the state it reaches."""

    kind: Literal["walkthrough"]
    stage: Stage | None = None
    steps: tuple[WalkStep, ...] = Field(min_length=2, max_length=40)
    # With a variant: the name of each run and what differs where they part.
    label: Label | None = None
    variant: Variant | None = None
    contrast: Text | None = None

    @model_validator(mode="after")
    def consistent(self) -> "WalkthroughBlock":
        runs = (self.steps, *((self.variant.steps,) if self.variant else ()))
        for steps in runs:
            check_subgoals(steps)
            for step in steps:
                if step.at is not None:
                    raise ValueError("Recording times belong to lecture highlight steps.")
                check_marks(self.stage, step)
        if self.variant is None:
            if self.label or self.contrast:
                raise ValueError("A run label and contrast compare a variant; add the variant.")
            return self
        if not self.label or not self.contrast:
            raise ValueError("A walkthrough with a variant names its run and states the contrast.")
        if self.label == self.variant.label:
            raise ValueError("The two runs need different labels.")
        if divergence(self) is None:
            raise ValueError("A variant takes a different step somewhere; otherwise drop it.")
        return self


def divergence(block: WalkthroughBlock) -> int | None:
    """The first step where the two runs differ, where the contrast is shown."""
    if block.variant is None:
        return None
    first, second = block.steps, block.variant.steps
    for index, (a, b) in enumerate(zip(first, second, strict=False)):
        if a.model_dump(exclude={"why", "note"}) != b.model_dump(exclude={"why", "note"}):
            return index
    return min(len(first), len(second)) if len(first) != len(second) else None


class ExampleBlock(Sourced):
    """A worked case read whole: what is given, the working and the result it reaches. A case
    that changes a state step by step is a walkthrough; a calculation to redo, a derivation."""

    kind: Literal["example"]
    given: tuple[Text, ...] = Field(default=(), max_length=8)
    steps: tuple[Text, ...] = Field(default=(), max_length=10)
    result: Text


class CalloutBlock(Sourced):
    """One idea set apart from the running text: a pitfall, or a condition or limit."""

    kind: Literal["callout"]
    tone: Literal["pitfall", "note"]
    # A note: a condition or limit in one or two sentences, never a repeat of the text above.
    text: Text | None = None
    # A pitfall reads as in Exam patterns: the moment it happens, the wrong and right move, why.
    situation: Text | None = None
    wrong: Text | None = None
    right: Text | None = None
    why: Text | None = None

    @model_validator(mode="after")
    def shaped(self) -> "CalloutBlock":
        pitfall = (self.situation, self.wrong, self.right, self.why)
        if self.tone == "pitfall" and (self.text or not all(pitfall)):
            raise ValueError("A pitfall callout gives situation, wrong, right and why only.")
        if self.tone != "pitfall" and (not self.text or any(pitfall)):
            raise ValueError("A note callout holds one text.")
        return self


Block = Annotated[
    TextBlock
    | DefinitionBlock
    | ExampleBlock
    | CalloutBlock
    | FormulaBlock
    | DerivationBlock
    | TableBlock
    | DiagramBlock
    | CodeBlock
    | PlotBlock
    | UmlBlock
    | FilesBlock
    | TreeBlock
    | FigureBlock
    | WalkthroughBlock,
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
    return any(
        block.kind in VISUAL_KINDS
        or (isinstance(block, WalkthroughBlock) and block.stage is not None)
        for block in blocks
    )


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
                value["mathml"] = compile_latex(block.latex)
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
            case WalkthroughBlock():
                if block.stage is not None:
                    value["stage"] = render_blocks((block.stage,))[0]
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


class TermAnnotation(Frozen):
    term: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^{}\r\n]+$")]
    meaning: Annotated[str, Field(min_length=1, max_length=240)]

    @model_validator(mode="after")
    def plain(self) -> "TermAnnotation":
        if self.term != self.term.strip() or not self.meaning.strip() or "{{" in self.meaning:
            raise ValueError("An annotation needs a trimmed term and a plain meaning.")
        return self


class StudyContent(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    organization: Literal["lectures", "weeks", "topics"]
    introduction: Text
    units: tuple[Unit, ...] = Field(min_length=1, max_length=300)
    annotations: tuple[TermAnnotation, ...] = Field(
        default=(), max_length=200, exclude_if=lambda v: not v
    )

    @model_validator(mode="after")
    def unit_keys(self) -> "StudyContent":
        if len({unit.key for unit in self.units}) != len(self.units):
            raise ValueError("Study units must have unique keys.")
        terms = [term.casefold() for term in self.definitions()]
        names = terms + [entry.term.casefold() for entry in self.annotations]
        if len(set(names)) != len(names):
            raise ValueError("Define each term once across the course.")
        value = self.model_dump(mode="json", exclude={"annotations"})
        if unknown := term_markers(value) - set(names):
            raise ValueError(
                f"Marked terms need a definition block or annotation: {sorted(unknown)[:5]}."
            )
        if misplaced := self.annotation_problems(value):
            raise ValueError(f"Annotations belong in explanatory prose: {sorted(misplaced)[:5]}.")
        if unknown := term_markers(value, fold=False) - self.annotation_names():
            mismatched = {term for term in unknown if term.casefold() in set(names) - set(terms)}
            if mismatched:
                raise ValueError(f"Use the annotation's spelling: {sorted(mismatched)[:5]}.")
        return self

    def annotation_names(self) -> set[str]:
        return {entry.term.lower() for entry in self.annotations}

    def annotation_problems(self, value: JsonValue, *, prose: bool = False) -> set[str]:
        return misplaced_annotations(value, self.annotation_names(), prose=prose)

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
LITERAL_FIELDS = frozenset({"code", "starter_code", "latex", "math", "mathml", "svg"})


def term_markers(value: JsonValue, *, fold: bool = True) -> set[str]:
    """Every marked term in authored text, outside code, inline code and math."""
    match value:
        case str():
            text = INLINE_SPANS.sub(" ", value)
            names = (match[1].strip() for match in TERM_MARKER.finditer(text))
            return {name.casefold() if fold else name.lower() for name in names}
        case list():
            return {term for item in value for term in term_markers(item, fold=fold)}
        case dict():
            return {
                term
                for field, item in value.items()
                if field not in LITERAL_FIELDS
                for term in term_markers(item, fold=fold)
            }
        case _:
            return set()


ANNOTATION_PROSE = frozenset(
    {
        "paragraphs",
        "explanation",
        "note",
        "hint",
        "hints",
        "introduction",
        "summary",
    }
)


def misplaced_annotations(value: JsonValue, terms: set[str], *, prose: bool = False) -> set[str]:
    if not terms:
        return set()
    match value:
        case str():
            return set() if prose else term_markers(value, fold=False) & terms
        case list():
            return {
                term for entry in value for term in misplaced_annotations(entry, terms, prose=prose)
            }
        case dict():
            return {
                term
                for field, entry in value.items()
                if field not in LITERAL_FIELDS
                for term in misplaced_annotations(entry, terms, prose=field in ANNOTATION_PROSE)
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
                # A plot stage carries no sources of its own; the axes and series are the same.
                plot = PlotStage.model_validate(
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
