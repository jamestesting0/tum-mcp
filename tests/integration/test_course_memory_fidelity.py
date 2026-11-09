"""Course Memory reads every authored link and cites only the sources each entry cites."""

import json
import typing
from pathlib import Path

import pytest
from knowledge_annotations import write_registry
from knowledge_fixture import fidelity_project
from pydantic import BaseModel

from tum_mcp.course.content.exam import ExamContent
from tum_mcp.course.content.exercises import ExerciseContent
from tum_mcp.course.content.study import StudyContent
from tum_mcp.course.lecture.content import LectureContent
from tum_mcp.course.memory.packet import encoded
from tum_mcp.course.memory.query import context, impact
from tum_mcp.course.project.models import Key

pytestmark = pytest.mark.usefixtures("course_memory")

PAST = "exam/sitting/ws23/variant/ws23-a/question/ws23-a-1"
BLOCK = "study/unit/observer/block/observer-definition"
PRACTICE = "exercises/set/sheet-1/exercise/observer-practice"

# (family, item that authors the link, item it names)
LINKS = (
    ("unit.lectures", "study/unit/observer", "lectures/lecture/observer-lecture"),
    ("exercise.prerequisites", PRACTICE, BLOCK),
    ("exercise.distilled_from", "exercises/set/sheet-1/exercise/observer-drill", PRACTICE),
    ("concept.units", "exam/concept/observer", "study/unit/observer"),
    ("concept.passages", "exam/concept/observer", BLOCK),
    ("concept.exercises", "exam/concept/observer", PRACTICE),
    ("concept.workflow_from", "exam/concept/observer", "exam/pattern/observer-design"),
    ("exam.links", "exam/concept/loose-coupling", "exam/concept/observer"),
    ("pattern.concepts", "exam/pattern/strategy-swap", "exam/concept/strategy"),
    ("pattern.examples.question", "exam/pattern/observer-design", PAST),
    (
        "question.concepts",
        "exam/sitting/ws23/variant/ws23-b/question/ws23-b-1",
        "exam/concept/observer",
    ),
    (
        "question.patterns",
        "exam/sitting/ws22/variant/ws22-a/question/ws22-2",
        "exam/pattern/composite-tree",
    ),
    ("mock.varies_from", "exam/mock/forecast-1/question/f1-1", PAST),
    ("past.guidance.prerequisites", PAST, BLOCK),
    ("lecture.passage", "lectures/lecture/observer-lecture/section/registration", BLOCK),
)

# Every schema field holding another key: a link family above, a source citation, or a
# reference that never leaves its own item.
CITATION = "citation"
INTERNAL = "internal"
FIELDS = {
    "Unit.lectures": "unit.lectures",
    "Exercise.prerequisites": "exercise.prerequisites",
    "Exercise.distilled_from": "exercise.distilled_from",
    "Concept.units": "concept.units",
    "Concept.passages": "concept.passages",
    "Concept.exercises": "concept.exercises",
    "Concept.workflow_from": "concept.workflow_from",
    "Link.start": "exam.links",
    "Link.end": "exam.links",
    "Pattern.concepts": "pattern.concepts",
    "PatternExample.question": "pattern.examples.question",
    "PastQuestion.concepts": "question.concepts",
    "MockQuestion.concepts": "question.concepts",
    "PastQuestion.patterns": "question.patterns",
    "MockQuestion.patterns": "question.patterns",
    "MockQuestion.varies_from": "mock.varies_from",
    "PastGuidance.prerequisites": "past.guidance.prerequisites",
    "Note.passage": "lecture.passage",
    "Highlight.passage": "lecture.passage",
    # The semester map: a tag on concepts, patterns and units, not an edge.
    "Concept.topic": "topic",
    "Pattern.topic": "topic",
    "Topic.units": "topic",
    # Parts of the reference models classified above.
    "Prerequisite.unit": INTERNAL,
    "Prerequisite.block": INTERNAL,
    "StudyPassage.unit": INTERNAL,
    "StudyPassage.block": INTERNAL,
    "ExerciseLink.set": INTERNAL,
    "ExerciseLink.exercise": INTERNAL,
    "NotePassage.unit": INTERNAL,
    "NotePassage.block": INTERNAL,
    # Solutions stay out of navigation; the set's sheet is cited by each of its exercises.
    "WorkedSolution.official_source": INTERNAL,
    "ExerciseSet.sheet": INTERNAL,
    "ExamContent.course_key": INTERNAL,
    "ExerciseContent.course_key": INTERNAL,
    "LectureContent.course_key": INTERNAL,
    "StudyContent.course_key": INTERNAL,
    # Timed evidence is checked by the evidence layer, not navigated.
    "Evidence.source_key": INTERNAL,
    "Note.evidence": INTERNAL,
    "Highlight.evidence": INTERNAL,
    "NoteImage.evidence": INTERNAL,
    "Thumbnail.evidence": INTERNAL,
    # References inside one item's own content.
    "ChoiceCheck.correct": INTERNAL,
    "GraphCheck.answers": INTERNAL,
    "Question.correct": INTERNAL,
    "Question.objective": INTERNAL,
    "Flashcard.objective": INTERNAL,
    "DrillItem.cases": INTERNAL,
    "GuidedStep.code": INTERNAL,
    "GuidedStep.part": INTERNAL,
    "GuidanceStep.code": INTERNAL,
    "Exercise.part_blocks": INTERNAL,
    "Edge.start": INTERNAL,
    "Edge.end": INTERNAL,
    "EdgeRef.start": INTERNAL,
    "EdgeRef.end": INTERNAL,
    "Flow.start": INTERNAL,
    "Flow.end": INTERNAL,
    "UmlMessage.start": INTERNAL,
    "UmlMessage.end": INTERNAL,
    "UmlRelation.start": INTERNAL,
    "UmlRelation.end": INTERNAL,
    "UmlTransition.start": INTERNAL,
    "UmlTransition.end": INTERNAL,
    "Frame.active": INTERNAL,
    "Frame.edges": INTERNAL,
    "Frame.frontier": INTERNAL,
    "Frame.visited": INTERNAL,
    "WalkStep.active": INTERNAL,
    "WalkStep.edges": INTERNAL,
    "WalkStep.frontier": INTERNAL,
    "WalkStep.layers": INTERNAL,
    "WalkStep.series": INTERNAL,
    "WalkStep.visited": INTERNAL,
    "PlotArea.series": INTERNAL,
}
SOURCE_OWNERS = {
    "Unit",
    "ExploreMaterial",
    "Exercise",
    "GuidanceStep",
    "Concept",
    "Pattern",
    "Mock",
    "ExamProfile",
    "Variant",
    "Lecture",
    "Note",
    "Highlight",
    "Question",
    "Flashcard",
}


def workspace(ref: str) -> str:
    return ref.split("/", 1)[0]


def ids(packet: dict) -> list[str]:
    return [item["id"] for item in packet["items"]]


@pytest.fixture
def course(tmp_path: Path) -> Path:
    return fidelity_project(tmp_path)


@pytest.mark.parametrize("direction", ("forward", "reverse"))
@pytest.mark.parametrize(("family", "start", "end"), LINKS, ids=[row[0] for row in LINKS])
def test_authored_link_reaches_its_other_end(course, family, start, end, direction):
    seed, other = (start, end) if direction == "forward" else (end, start)
    packet = context(course, item=seed, purpose=workspace(other), limit=12, max_bytes=24000)
    assert other in ids(packet)


@pytest.mark.parametrize(
    ("seed", "purpose", "authored"),
    (
        ("exam/concept/observer", "exercises", {PRACTICE}),
        ("exam/concept/observer", "study", {BLOCK, "study/unit/observer"}),
        (PRACTICE, "exam", {"exam/concept/observer"}),
        (BLOCK, "lectures", {"lectures/lecture/observer-lecture/section/registration"}),
    ),
)
def test_teaching_packet_puts_authored_links_before_weaker_items(course, seed, purpose, authored):
    packet = context(course, item=seed, purpose=purpose, limit=4, max_bytes=8000)
    others = [ref for ref in ids(packet) if ref != seed]
    assert set(others[: len(authored)]) == authored


def test_path_steps_carry_the_authors_link_explanation(course):
    packet = context(course, item=PRACTICE, purpose="study", limit=4, max_bytes=8000)
    step = next(
        step
        for path in packet["paths"]
        for step in path["steps"]
        if step["relation"] == "prerequisite_of" and step["from"] == BLOCK
    )
    assert step["note"] == "Use the notification contract."


def test_entry_locators_name_only_the_sources_the_entry_cites(course):
    cited = {
        BLOCK: {"slides"},
        "study/unit/observer/block/exam-link": {"exam-ws23"},
        f"{PRACTICE}/step/registration": {"slides"},
        "lectures/lecture/observer-lecture/section/registration": {"slides"},
    }
    for ref, sources in cited.items():
        packet = context(course, item=ref, purpose=workspace(ref), limit=4, max_bytes=8000)
        view = next(item for item in packet["items"] if item["id"] == ref)
        named = {loc["source"] for loc in view["locators"] if loc["kind"] == "source"}
        assert named == sources, ref


def test_impact_names_entries_by_their_own_sources(course):
    packet = impact(course, "exam-ws23", limit=30, max_bytes=65536)
    assert "study/unit/observer/block/exam-link" in packet["direct"]
    assert BLOCK not in packet["direct"]


def test_concept_selector_resolves_exam_concepts(course):
    packet = context(course, concept="observer", purpose="exam", limit=4, max_bytes=8000)
    assert ids(packet)[0] == "exam/concept/observer"


def test_concept_selector_seeds_exam_and_registry_concepts_sharing_a_key(course):
    write_registry(course, [])
    packet = context(course, concept="observer", purpose="exam", limit=4, max_bytes=8000)
    assert packet["status"] == "ok"
    assert ids(packet)[0] == "exam/concept/observer"


def test_link_decisions_appear_as_gaps(course):
    packet = context(
        course, item="exam/concept/decorator", purpose="exercises", limit=4, max_bytes=8000
    )
    assert packet["gaps"] == [
        {
            "item": "concept:decorator",
            "target": "exercises",
            "reason": "No sheet exercise trains Decorator yet.",
        }
    ]


def test_every_reference_field_is_classified():
    pattern = next(
        m.pattern for m in typing.get_args(Key)[1].metadata if getattr(m, "pattern", None)
    )
    found: dict[str, bool] = {}
    seen: set[type] = set()

    def models(annotation) -> list[type[BaseModel]]:
        nested = (
            [annotation]
            if isinstance(annotation, type) and issubclass(annotation, BaseModel)
            else []
        )
        return nested + [m for arg in typing.get_args(annotation) for m in models(arg)]

    def walk(model: type[BaseModel]) -> None:
        if model in seen:
            return
        seen.add(model)
        for subclass in model.__subclasses__():
            walk(subclass)
        for name, field in model.model_fields.items():
            nested = models(field.annotation)
            if name != "key" and (
                pattern in str(field.annotation)
                or any(pattern in str(item) for item in field.metadata)
                or any(
                    m.__name__
                    in {
                        "StudyPassage",
                        "ExerciseLink",
                        "Prerequisite",
                        "NotePassage",
                        "CaseRef",
                        "CodeRef",
                        "SourceVersion",
                        "SourceRole",
                        "EdgeRef",
                    }
                    for m in nested
                )
            ):
                found[f"{model.__name__}.{name}"] = True
            for item in nested:
                walk(item)

    for root in (StudyContent, ExerciseContent, ExamContent, LectureContent):
        walk(root)
    citations = {name for name in found if name.endswith(".sources")}
    assert {name.split(".")[0] for name in citations} - SOURCE_OWNERS <= {
        model.__name__ for model in seen if model.__name__.endswith(("Block", "Stage"))
    }
    assert set(found) - citations == set(FIELDS)
    assert {value for value in FIELDS.values() if value not in {INTERNAL, CITATION, "topic"}} == {
        row[0] for row in LINKS
    }


def test_topic_tags_name_the_semester_map_region(course):
    packet = context(course, item="exam/concept/observer", purpose="exam", limit=4, max_bytes=8000)
    assert packet["items"][0]["tags"]["topic"] == "behavioral"
    unit = context(course, item="study/unit/observer", purpose="study", limit=4, max_bytes=8000)
    assert unit["items"][0]["tags"]["topic"] == "behavioral"


def test_gaps_give_way_to_items_under_a_tight_byte_budget(course):
    roomy = context(
        course, item="exam/concept/decorator", purpose="exercises", limit=4, max_bytes=8000
    )
    tight_bytes = len(encoded(roomy)) - 40
    tight = context(
        course, item="exam/concept/decorator", purpose="exercises", limit=4, max_bytes=tight_bytes
    )
    assert ids(tight) == ids(roomy)
    assert tight["gaps"] == [] and tight["omitted"]["gaps"] == 1


def test_links_file_is_read_through_the_snapshot(course):
    links = course / ".tum-mcp" / "links.json"
    value = json.loads(links.read_bytes())
    value["decisions"][0]["reason"] = "Changed reason after the decision was recorded."
    links.write_text(json.dumps(value))
    packet = context(
        course, item="exam/concept/decorator", purpose="exercises", limit=4, max_bytes=8000
    )
    assert packet["gaps"][0]["reason"] == "Changed reason after the decision was recorded."
