"""Source-linked study content with editable LaTeX and legacy MathML inputs."""

from collections.abc import Iterator
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


class UmlBlock(Sourced):
    """A UML class, sequence or state diagram, laid out by the app from its structure."""

    kind: Literal["uml"]
    diagram: Literal["class", "sequence", "state"]
    description: Text
    classes: tuple[UmlClass, ...] = Field(default=(), max_length=20)
    relations: tuple[UmlRelation, ...] = Field(default=(), max_length=40)
    participants: tuple[UmlParticipant, ...] = Field(default=(), max_length=10)
    messages: tuple[UmlMessage, ...] = Field(default=(), max_length=40)
    fragments: tuple[UmlFragment, ...] = Field(default=(), max_length=10)
    states: tuple[UmlState, ...] = Field(default=(), max_length=20)
    transitions: tuple[UmlTransition, ...] = Field(default=(), max_length=40)

    @model_validator(mode="after")
    def consistent(self) -> "UmlBlock":
        if self.diagram != "state" and (self.states or self.transitions):
            raise ValueError("Only a UML state diagram has states and transitions.")
        if self.diagram == "state":
            return self._state_machine()
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


Block = Annotated[
    TextBlock
    | FormulaBlock
    | TableBlock
    | DiagramBlock
    | CodeBlock
    | PlotBlock
    | UmlBlock
    | FilesBlock
    | TreeBlock,
    Field(discriminator="kind"),
]


# Authored questions pair their text with at least one of these, because prose alone
# makes code, structures and calculations hard to picture.
VISUAL_KINDS = frozenset({"formula", "table", "diagram", "code", "plot", "uml", "files", "tree"})
VISUAL_RULE = "a code snippet, diagram, UML diagram, tree, formula, table or plot beside its text"


def has_visual(blocks: tuple[Block, ...]) -> bool:
    return any(block.kind in VISUAL_KINDS for block in blocks)


def render_blocks(blocks: tuple[Block, ...]) -> list[dict[str, JsonValue]]:
    """Project safe blocks for both workspaces without rewriting authored notation."""
    result: list[dict[str, JsonValue]] = []
    for block in blocks:
        value = block.model_dump(mode="json", exclude_none=True)
        match block:
            case FormulaBlock():
                value["mathml"] = block.mathml or compile_latex(block.latex or "")
            case (
                TextBlock()
                | TableBlock()
                | CodeBlock()
                | DiagramBlock()
                | PlotBlock()
                | UmlBlock()
                | FilesBlock()
                | TreeBlock()
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
