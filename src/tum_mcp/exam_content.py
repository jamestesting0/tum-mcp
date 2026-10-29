"""Exam Prep content: a past-exam registry, cheatsheet concepts, patterns and practice exams.

Agents author identities, classifications and teaching. Counts, rates, order and coverage
are always derived by code (exam_data), so the schema has no count fields.
"""

import json
import re
from collections import defaultdict
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, model_validator

from tum_mcp.exercise_checks import Check
from tum_mcp.exercise_content import (
    GuidanceStep,
    Prerequisite,
    TransferTask,
    WorkedSolution,
    check_steps_against_files,
)
from tum_mcp.settings import Frozen
from tum_mcp.study_content import (
    VISUAL_RULE,
    Block,
    CodeRef,
    SourceVersion,
    Symbol,
    Text,
    check_code_refs,
    check_target_file,
    has_visual,
    project_files,
    tree_nodes,
)
from tum_mcp.study_math import compile_latex
from tum_mcp.study_models import Digest, Key, PageRange
from tum_mcp.study_store import digest

QuestionFormat = Literal[
    "choice", "numeric", "short", "derivation", "proof", "code", "diagram", "essay", "other"
]
Points = Annotated[FiniteFloat, Field(gt=0, le=1000)]
Minutes = Annotated[int, Field(ge=1, le=600)]
Held = Annotated[
    str, Field(pattern=r"^(19|20)[0-9]{2}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$")
]
# Sittings that statistics consider; outdated ones stay visible as instances only.
CONSIDERED = frozenset({"current", "partial"})
# Only a forecast this close to a stored past statement is rejected; lower similarity is
# reported for the agent to judge (decision D11).
NEAR_VERBATIM = 0.9


class ExamProfile(Frozen):
    format: Literal["written", "online", "programming", "oral", "mixed"]
    duration_minutes: Minutes | None = None
    total_points: Points | None = None
    allowed_aids: Text | None = None
    languages: tuple[Annotated[str, Field(min_length=2, max_length=40)], ...] = Field(
        default=(), max_length=6
    )
    question_formats: tuple[QuestionFormat, ...] = Field(default=(), max_length=9)
    notes: Text | None = None
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=20)


class Topic(Frozen):
    key: Key
    title: Text
    order: int = Field(ge=0, le=1000)
    units: tuple[Key, ...] = Field(default=(), max_length=40)


class SourceRole(Frozen):
    key: Key
    sha256: Digest
    role: Literal[
        "paper", "official_solution", "student_solution", "marking_scheme", "recollection"
    ]
    pages: PageRange | None = None

    def page_span(self) -> tuple[int, int] | None:
        if self.pages is None:
            return None
        first, _, last = self.pages.partition("-")
        start, end = int(first), int(last or first)
        if end < start:
            raise ValueError("Page ranges must run forwards.")
        return start, end


class Criterion(Frozen):
    text: Text
    points: Points


class PastGuidance(Frozen):
    objectives: tuple[Text, ...] = Field(min_length=1, max_length=12)
    prerequisites: tuple[Prerequisite, ...] = Field(default=(), max_length=10)
    steps: tuple[GuidanceStep, ...] = Field(min_length=1, max_length=40)
    transfer: TransferTask | None = None


def _check_marking(marking: tuple[Criterion, ...], points: float | None) -> None:
    if not marking:
        return
    if points is None or abs(sum(item.points for item in marking) - points) > 1e-6:
        raise ValueError("Marking criteria must add up to the question's points.")


class PastQuestion(Frozen):
    key: Key
    number: Annotated[str, Field(min_length=1, max_length=20)]
    points: Points | None = None
    format: QuestionFormat
    patterns: tuple[Key, ...] = Field(default=(), max_length=3)
    concepts: tuple[Key, ...] = Field(default=(), max_length=12)
    status: Literal["classified", "out_of_scope", "unreadable"] = "classified"
    reason: Text | None = None
    confidence: Literal["high", "medium", "low"] = "high"
    difficulty: int | None = Field(default=None, ge=1, le=3)
    minutes: Minutes | None = None
    locator: Annotated[str, Field(min_length=1, max_length=200)]
    statement: tuple[Block, ...] = Field(default=(), max_length=40)
    solution: WorkedSolution | None = None
    guidance: PastGuidance | None = None
    check: Check | None = None
    marking: tuple[Criterion, ...] = Field(default=(), max_length=20)
    marking_basis: Literal["official", "authored"] | None = None

    @model_validator(mode="after")
    def consistent(self) -> "PastQuestion":
        if (self.status == "classified") == (self.reason is not None):
            raise ValueError("Only out-of-scope or unreadable questions carry a reason.")
        if self.status == "classified" and not self.patterns:
            raise ValueError("A classified question belongs to at least one pattern.")
        if len(set(self.patterns)) != len(self.patterns) or len(set(self.concepts)) != len(
            self.concepts
        ):
            raise ValueError("Question patterns and concepts must be distinct.")
        if (self.guidance or self.check) and not (self.statement and self.solution):
            raise ValueError("Guided practice needs the stored statement and a solution.")
        if bool(self.marking) != (self.marking_basis is not None):
            raise ValueError("Marking criteria declare whether they are official or authored.")
        _check_marking(self.marking, self.points)
        return self


class Variant(Frozen):
    key: Key
    label: Text
    sources: tuple[SourceRole, ...] = Field(min_length=1, max_length=10)
    total_points: Points | None = None
    questions: tuple[PastQuestion, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def provenance(self) -> "Variant":
        keys = {item.key for item in self.sources}
        if len(keys) != len(self.sources):
            raise ValueError("A variant lists each source once.")
        if not any(item.role == "paper" for item in self.sources):
            raise ValueError("A variant needs its question paper among its sources.")
        roles = {item.key: item.role for item in self.sources}
        numbers = [question.number for question in self.questions]
        if len(set(numbers)) != len(numbers):
            raise ValueError("Question numbers repeat within a variant.")
        for question in self.questions:
            blocks = (*question.statement, *(question.solution.blocks if question.solution else ()))
            if question.guidance:
                blocks += tuple(block for step in question.guidance.steps for block in step.blocks)
            if any(not set(block.sources) <= keys for block in blocks):
                raise ValueError("Past statements and solutions cite only their variant's sources.")
            if question.guidance and any(
                not set(step.sources) <= keys for step in question.guidance.steps
            ):
                raise ValueError("Guidance steps cite only their variant's sources.")
            official = question.solution and question.solution.official_source
            if official and roles.get(official) != "official_solution":
                raise ValueError("An official solution must come from an official solution source.")
            if question.marking_basis == "official" and not {
                "official_solution",
                "marking_scheme",
            } & set(roles.values()):
                raise ValueError("Official marking needs a marking scheme or official solution.")
        return self

    @property
    def replayable(self) -> bool:
        return all(question.statement and question.solution for question in self.questions)


class Sitting(Frozen):
    key: Key
    label: Text
    held: Held
    kind: Literal["final", "retake", "midterm", "official_mock", "unofficial_mock", "recollection"]
    relevance: Literal["current", "partial", "outdated"] = "current"
    relevance_note: Text | None = None
    variants: tuple[Variant, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def explained(self) -> "Sitting":
        if (self.relevance != "current") != (self.relevance_note is not None):
            raise ValueError("Explain partial or outdated relevance, and only then.")
        return self


class CompactFormula(Frozen):
    latex: Annotated[str, Field(min_length=1, max_length=5000)]
    plain: Text
    symbols: tuple[Symbol, ...] = Field(default=(), max_length=20)
    conditions: Text | None = None

    @model_validator(mode="after")
    def compiles(self) -> "CompactFormula":
        compile_latex(self.latex)
        return self


class Concept(Frozen):
    key: Key
    topic: Key
    title: Text
    kind: Literal[
        "definition",
        "theorem",
        "formula",
        "algorithm",
        "procedure",
        "fact",
        "distinction",
        "pitfall",
    ]
    tier: Literal["core", "supporting"] = "core"
    line: Text
    formula: CompactFormula | None = None
    trigger: Text | None = None
    pitfall: Text | None = None
    basis: Literal["tested", "prerequisite", "emphasized", "untested_core"]
    on_map: bool = True
    units: tuple[Key, ...] = Field(default=(), max_length=20)
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=20)
    details: tuple[Block, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def cited(self) -> "Concept":
        keys = {item.key for item in self.sources}
        if any(not set(block.sources) <= keys for block in self.details):
            raise ValueError("Concept details cite only the concept's sources.")
        return self


class Link(Frozen):
    """An arrow from a foundation (start) to what builds on it (end)."""

    start: Key
    end: Key
    kind: Literal["requires", "derives", "contrasts"]
    note: Text | None = None


class PatternStep(Frozen):
    do: Text
    why: Text | None = None


class DrillItem(Frozen):
    key: Key
    prompt: Text
    blocks: tuple[Block, ...] = Field(default=(), max_length=20)
    check: Check | None = None
    explanation: Text

    @model_validator(mode="after")
    def shown(self) -> "DrillItem":
        if not has_visual(self.blocks):
            raise ValueError(f"Drill {self.key} needs {VISUAL_RULE}.")
        return self


class GuidedStep(Frozen):
    """One move of the worked practice: applies workflow step `step` (1-based)."""

    step: int = Field(ge=1, le=40)
    prompt: Text
    hint: Text | None = None
    code: tuple[CodeRef, ...] = Field(default=(), max_length=3)
    check: Check | None = None
    answer: tuple[Block, ...] = Field(min_length=1, max_length=10)


class PatternExample(Frozen):
    question: Key | None = None
    blocks: tuple[Block, ...] = Field(default=(), max_length=20)
    solution: WorkedSolution | None = None
    steps: tuple[GuidedStep, ...] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def one_form(self) -> "PatternExample":
        authored = bool(self.blocks) and self.solution is not None
        if (self.question is None) != authored or (
            self.question and (self.blocks or self.solution)
        ):
            raise ValueError(
                "An example is a past question key or authored blocks with a solution."
            )
        if self.blocks and not has_visual(self.blocks):
            raise ValueError(f"A worked practice question needs {VISUAL_RULE}.")
        return self

    def blocks_cited(self) -> tuple[Block, ...]:
        return (
            *self.blocks,
            *(self.solution.blocks if self.solution else ()),
            *(block for step in self.steps for block in step.answer),
        )


class Pattern(Frozen):
    key: Key
    topic: Key
    title: Text
    summary: Text
    cues: tuple[Text, ...] = Field(min_length=1, max_length=12)
    workflow: tuple[PatternStep, ...] = Field(min_length=1, max_length=40)
    template: tuple[Block, ...] = Field(default=(), max_length=10)
    marking: tuple[Text, ...] = Field(default=(), max_length=20)
    marking_basis: Literal["official", "inferred"] | None = None
    pitfalls: tuple[Text, ...] = Field(default=(), max_length=20)
    variations: tuple[Text, ...] = Field(default=(), max_length=20)
    concepts: tuple[Key, ...] = Field(min_length=1, max_length=30)
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=30)
    example: PatternExample
    drill: tuple[DrillItem, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def cited(self) -> "Pattern":
        keys = {item.key for item in self.sources}
        blocks = (
            *self.template,
            *self.example.blocks_cited(),
            *(block for item in self.drill for block in item.blocks),
        )
        if any(not set(block.sources) <= keys for block in blocks):
            raise ValueError("Pattern content cites only the pattern's sources.")
        applied = [item.step for item in self.example.steps]
        if applied != sorted(applied) or set(applied) != set(range(1, len(self.workflow) + 1)):
            raise ValueError(
                "The worked practice applies every workflow step, in order "
                f"(steps 1-{len(self.workflow)})."
            )
        if bool(self.marking) != (self.marking_basis is not None):
            raise ValueError("Marking points declare whether they are official or inferred.")
        if len({item.key for item in self.drill}) != len(self.drill):
            raise ValueError("Drill keys repeat within a pattern.")
        return self


class MockQuestion(Frozen):
    key: Key
    number: Annotated[str, Field(min_length=1, max_length=20)]
    points: Points
    format: QuestionFormat
    patterns: tuple[Key, ...] = Field(default=(), max_length=3)
    concepts: tuple[Key, ...] = Field(min_length=1, max_length=12)
    novelty: Literal["variant", "untested"]
    varies_from: tuple[Key, ...] = Field(default=(), max_length=10)
    change: (
        Literal["cue", "constraint", "representation", "combination", "reversal", "scale"] | None
    ) = None
    change_note: Text | None = None
    statement: tuple[Block, ...] = Field(min_length=1, max_length=40)
    parts: tuple[Text, ...] = Field(default=(), max_length=30)
    marking: tuple[Criterion, ...] = Field(min_length=1, max_length=20)
    minutes: Minutes
    difficulty: int = Field(ge=1, le=3)
    solution: WorkedSolution

    @model_validator(mode="after")
    def novel(self) -> "MockQuestion":
        variant = self.novelty == "variant"
        if variant != bool(self.varies_from) or variant != (
            self.change is not None and self.change_note is not None
        ):
            raise ValueError(
                "A variant names its past questions and what changed; untested does not."
            )
        if variant and not self.patterns:
            raise ValueError("A variant shares a pattern with the past questions it varies.")
        if not has_visual(self.statement):
            raise ValueError(f"Practice question {self.key} needs {VISUAL_RULE}.")
        _check_marking(self.marking, self.points)
        return self


class Mock(Frozen):
    key: Key
    title: Text
    duration_minutes: Minutes
    instructions: Text
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=30)
    questions: tuple[MockQuestion, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def cited(self) -> "Mock":
        keys = {item.key for item in self.sources}
        for question in self.questions:
            blocks = (*question.statement, *question.solution.blocks)
            if any(not set(block.sources) <= keys for block in blocks):
                raise ValueError("Practice exam content cites only the exam's sources.")
            if question.solution.official_source:
                raise ValueError("Forecast solutions are authored, never official.")
        if len({item.number for item in self.questions}) != len(self.questions):
            raise ValueError("Question numbers repeat within a practice exam.")
        return self

    @property
    def points(self) -> float:
        return sum(question.points for question in self.questions)


def block_text(blocks: tuple[Block, ...]) -> str:
    """Plain words of safe blocks, for similarity checks; titles are excluded."""
    parts: list[str] = []
    for block in blocks:
        match block.kind:
            case "text":
                parts.extend((*block.paragraphs, *block.steps, *block.points))
            case "formula":
                parts.append(block.plain)
            case "table":
                parts.extend(cell for row in block.rows for cell in row)
            case "code":
                parts.append(block.code)
            case "diagram" | "plot":
                parts.append(block.description)
            case "uml":
                parts.append(block.description)
                parts.extend(
                    item.name for item in (*block.classes, *block.participants, *block.states)
                )
                parts.extend(item.text for item in block.messages)
            case "files":
                parts.extend(item.code for item in block.files)
            case "figure":
                parts.extend((block.alt, block.caption or ""))
            case "tree":
                parts.append(block.description or "")
                parts.extend(f"{item.label} {item.note}" for item, _ in tree_nodes(block.root))
    return " ".join(parts)


def shingles(text: str, size: int = 5) -> frozenset[str]:
    words = re.findall(r"[^\W_]+", text.casefold())
    if len(words) < size:
        return frozenset({" ".join(words)} if words else ())
    return frozenset(
        " ".join(words[index : index + size]) for index in range(len(words) - size + 1)
    )


def similarity(own: frozenset[str], past: frozenset[str]) -> float:
    """Share of a past statement's word sequences that reappear in a new one.

    Measured against the past statement alone, so text, code or tables added around a
    copied question cannot dilute it.
    """
    if not own or not past:
        return 0.0
    return len(own & past) / len(past)


class ExamContent(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    profile: ExamProfile | None = None
    topics: tuple[Topic, ...] = Field(default=(), max_length=40)
    sittings: tuple[Sitting, ...] = Field(default=(), max_length=60)
    concepts: tuple[Concept, ...] = Field(default=(), max_length=400)
    links: tuple[Link, ...] = Field(default=(), max_length=1200)
    patterns: tuple[Pattern, ...] = Field(default=(), max_length=120)
    mocks: tuple[Mock, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def consistent(self) -> "ExamContent":
        if not (self.sittings or self.concepts or self.patterns or self.mocks):
            raise ValueError("Exam Prep needs past exams, cheatsheet concepts, patterns or mocks.")
        self._unique()
        self._references()
        self._source_versions()
        self._documents()
        self._links()
        self._basis_and_novelty()
        return self

    def past_questions(self) -> dict[str, tuple[Sitting, Variant, PastQuestion]]:
        return {
            question.key: (sitting, variant, question)
            for sitting in self.sittings
            for variant in sitting.variants
            for question in variant.questions
        }

    def concept_coverage(self) -> dict[str, set[str]]:
        """Considered sittings in which each concept was tested by a classified question."""
        covered: dict[str, set[str]] = defaultdict(set)
        for sitting, _, question in self.past_questions().values():
            if sitting.relevance in CONSIDERED and question.status == "classified":
                for concept in question.concepts:
                    covered[concept].add(sitting.key)
        return covered

    def _unique(self) -> None:
        groups = {
            "topic": [item.key for item in self.topics],
            "sitting": [item.key for item in self.sittings],
            "variant": [v.key for s in self.sittings for v in s.variants],
            "past question": [
                q.key for s in self.sittings for v in s.variants for q in v.questions
            ],
            "concept": [item.key for item in self.concepts],
            "pattern": [item.key for item in self.patterns],
            "practice exam": [item.key for item in self.mocks],
            "practice question": [q.key for m in self.mocks for q in m.questions],
        }
        for name, keys in groups.items():
            if len(set(keys)) != len(keys):
                raise ValueError(f"Each {name} key must be unique.")

    def _references(self) -> None:
        topics = {item.key for item in self.topics}
        concepts = {item.key for item in self.concepts}
        patterns = {item.key for item in self.patterns}
        past = self.past_questions()
        if any(item.topic not in topics for item in (*self.concepts, *self.patterns)):
            raise ValueError("Concepts and patterns must belong to a declared topic.")
        for _, _, question in past.values():
            if not set(question.patterns) <= patterns or not set(question.concepts) <= concepts:
                raise ValueError(
                    f"Past question {question.key} references an unknown pattern or concept."
                )
        for _, _, question in past.values():
            if question.guidance:
                check_steps_against_files(question.statement, question.guidance.steps)
        for pattern in self.patterns:
            if not set(pattern.concepts) <= concepts:
                raise ValueError(f"Pattern {pattern.key} references an unknown concept.")
            shown = (
                past[pattern.example.question][2].statement
                if pattern.example.question in past
                else pattern.example.blocks
            )
            files = project_files(shown)
            for step in pattern.example.steps:
                check_code_refs(files, step.code)
                if step.check and step.check.kind == "self_check" and step.check.file:
                    check_target_file(files, step.check.file)
            if pattern.example.question:
                found = past.get(pattern.example.question)
                if found is None or not (found[2].statement and found[2].solution):
                    raise ValueError(
                        f"Pattern {pattern.key} shows a past question without a stored statement "
                        "and solution."
                    )
                if pattern.key not in found[2].patterns:
                    raise ValueError(f"Pattern {pattern.key} shows a question of another pattern.")
                # A printed question stays as printed; the worked steps add the picture.
                answers = tuple(block for step in pattern.example.steps for block in step.answer)
                if not has_visual(found[2].statement) and not has_visual(answers):
                    raise ValueError(
                        f"Pattern {pattern.key}: a worked step needs {VISUAL_RULE}, because "
                        "the past question is text only."
                    )
        for mock in self.mocks:
            for question in mock.questions:
                if not set(question.patterns) <= patterns or not set(question.concepts) <= concepts:
                    raise ValueError(
                        f"Practice question {question.key} references an unknown pattern or "
                        "concept."
                    )
                for key in question.varies_from:
                    found = past.get(key)
                    if found is None or not set(found[2].patterns) & set(question.patterns):
                        raise ValueError(
                            f"Practice question {question.key} must vary a past question of the "
                            "same pattern."
                        )

    def _source_versions(self) -> None:
        versions: dict[str, str] = {}
        cited = [
            *(self.profile.sources if self.profile else ()),
            *(
                source
                for item in (*self.concepts, *self.patterns, *self.mocks)
                for source in item.sources
            ),
            *(source for s in self.sittings for v in s.variants for source in v.sources),
        ]
        for source in cited:
            if versions.setdefault(source.key, source.sha256) != source.sha256:
                raise ValueError(f"Source {source.key} has conflicting versions.")

    def _documents(self) -> None:
        # One document belongs to one sitting unless disjoint page ranges split a bundle.
        uses: dict[str, list[tuple[str, tuple[int, int] | None]]] = defaultdict(list)
        for sitting in self.sittings:
            for variant in sitting.variants:
                for source in variant.sources:
                    span = source.page_span()
                    uses[f"key:{source.key}"].append((sitting.key, span))
                    uses[f"sha:{source.sha256}"].append((sitting.key, span))
        for identity, entries in uses.items():
            sittings = {sitting for sitting, _ in entries}
            if len(sittings) < 2:
                continue
            if any(span is None for _, span in entries):
                label = identity.split(":", 1)[1][:16]
                raise ValueError(
                    f"Document {label} appears in several sittings; give each its page range."
                )
            for left_index, (left_sitting, left) in enumerate(entries):
                for right_sitting, right in entries[left_index + 1 :]:
                    if (
                        left_sitting != right_sitting
                        and left[0] <= right[1]
                        and right[0] <= left[1]
                    ):
                        raise ValueError("Page ranges of one document overlap across sittings.")

    def _links(self) -> None:
        concepts = {item.key for item in self.concepts}
        seen: set[tuple[str, str, str]] = set()
        graph: dict[str, set[str]] = defaultdict(set)
        for link in self.links:
            if link.start not in concepts or link.end not in concepts:
                raise ValueError("Links connect declared concepts.")
            if link.start == link.end:
                raise ValueError("A concept cannot link to itself.")
            pair = (
                (link.kind, *sorted((link.start, link.end)))
                if link.kind == "contrasts"
                else (link.kind, link.start, link.end)
            )
            if pair in seen:
                raise ValueError("Each link appears once.")
            seen.add(pair)
            if link.kind != "contrasts":
                graph[link.start].add(link.end)
        state: dict[str, int] = {}
        path: list[str] = []

        def visit(node: str) -> None:
            state[node] = 1
            path.append(node)
            for following in sorted(graph[node]):
                if state.get(following) == 1:
                    cycle = path[path.index(following) :] + [following]
                    raise ValueError("Prerequisite links form a cycle: " + " -> ".join(cycle))
                if following not in state:
                    visit(following)
            path.pop()
            state[node] = 2

        for node in sorted(graph):
            if node not in state:
                visit(node)
        if sum(item.on_map for item in self.concepts) > 200:
            raise ValueError("The map can show at most 200 concepts.")

    def _basis_and_novelty(self) -> None:
        coverage = self.concept_coverage()
        tested = {item.key for item in self.concepts if item.basis == "tested"}
        for concept in self.concepts:
            if concept.basis == "tested" and not coverage.get(concept.key):
                raise ValueError(
                    f"Concept {concept.key} is marked tested but no current past question tests it."
                )
            if concept.basis == "untested_core" and coverage.get(concept.key):
                raise ValueError(
                    f"Concept {concept.key} is marked untested but past questions test it."
                )
        # Concepts that can reach a tested one: one reverse breadth-first search.
        preceding: dict[str, set[str]] = defaultdict(set)
        for link in self.links:
            if link.kind != "contrasts":
                preceding[link.end].add(link.start)
        supports, queue = set(), list(tested)
        while queue:
            for earlier in preceding[queue.pop()]:
                if earlier not in supports:
                    supports.add(earlier)
                    queue.append(earlier)
        for concept in self.concepts:
            if concept.basis == "prerequisite" and concept.key not in supports:
                raise ValueError(
                    f"Prerequisite {concept.key} must link to a tested concept it supports."
                )
        past_texts = {
            key: shingles(block_text(question.statement))
            for key, (_, _, question) in self.past_questions().items()
            if question.statement
        }
        for mock in self.mocks:
            for question in mock.questions:
                if question.novelty == "untested" and all(
                    coverage.get(concept) for concept in question.concepts
                ):
                    raise ValueError(
                        f"Practice question {question.key} is marked untested but past exams test "
                        "all its concepts."
                    )
                own = shingles(block_text(question.statement))
                for key, text in past_texts.items():
                    if similarity(own, text) >= NEAR_VERBATIM:
                        raise ValueError(
                            f"Practice question {question.key} nearly copies past question {key}; "
                            "write a genuine variant."
                        )


def _revision(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def concept_revision(concept: Concept) -> str:
    """Know/review marks survive edits to details, sources and links."""
    return _revision(concept.model_dump(mode="json", include={"key", "line", "formula", "trigger"}))


def pattern_revision(pattern: Pattern) -> str:
    return _revision(pattern.model_dump(mode="json", exclude={"sources", "title", "topic"}))


def mock_revision(mock: Mock) -> str:
    return _revision(mock.model_dump(mode="json", exclude={"sources", "title"}))


def variant_revision(variant: Variant) -> str:
    return _revision(variant.model_dump(mode="json", exclude={"sources", "label"}))
