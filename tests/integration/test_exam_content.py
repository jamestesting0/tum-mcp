import copy
from collections.abc import Callable
from pathlib import Path

import pytest
from material_fixture import exam_document, exam_project
from pydantic import ValidationError

from tum_mcp.exam_content import ExamContent, concept_revision


@pytest.fixture(scope="module")
def document(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return exam_document(exam_project(tmp_path_factory.mktemp("exam")))


def test_the_synthetic_exam_document_is_valid(document: dict) -> None:
    content = ExamContent.model_validate(document)
    assert len(content.past_questions()) == 7
    assert content.concept_coverage()["observer"] == {"ws23", "ws22"}
    assert "composite" in content.concept_coverage()


def change(document: dict, mutate: Callable[[dict], None]) -> dict:
    value = copy.deepcopy(document)
    mutate(value)
    return value


def sitting(value: dict, key: str) -> dict:
    return next(item for item in value["sittings"] if item["key"] == key)


def mock_question(value: dict, index: int = 0) -> dict:
    return value["mocks"][0]["questions"][index]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda v: sitting(v, "ss19")["variants"][0]["sources"].append(
                copy.deepcopy(sitting(v, "ws22")["variants"][0]["sources"][0])
            ),
            "appears in several sittings",
        ),
        (
            lambda v: v["concepts"][4].update(basis="tested"),
            "marked tested but no current past question",
        ),
        (lambda v: v["concepts"][0].update(basis="untested_core"), "marked untested but past"),
        (
            lambda v: v.update(links=[link for link in v["links"] if link["kind"] == "contrasts"]),
            "must link to a tested",
        ),
        (
            lambda v: v["links"].append(
                {"start": "observer", "end": "loose-coupling", "kind": "requires"}
            ),
            "form a cycle: loose-coupling -> observer -> loose-coupling",
        ),
        (lambda v: mock_question(v).update(varies_from=["ws22-2"]), "same pattern"),
        (
            lambda v: mock_question(v, 1).update(concepts=["observer"]),
            "marked untested but past exams",
        ),
        (
            lambda v: mock_question(v)["statement"].__setitem__(
                0, copy.deepcopy(sitting(v, "ws23")["variants"][0]["questions"][0]["statement"][0])
            ),
            "cites only the exam's sources",
        ),
        (lambda v: mock_question(v)["marking"][0].update(points=7), "add up"),
        (
            lambda v: sitting(v, "ws23")["variants"][0]["questions"][0]["solution"].update(
                official_source="exam-ws23"
            ),
            "official solution source",
        ),
        (lambda v: sitting(v, "ss19").pop("relevance_note"), "Explain partial or outdated"),
        (
            lambda v: v["patterns"][0]["example"].update(question="ws23-b-1"),
            "without a stored statement",
        ),
        (
            lambda v: v["patterns"][0]["example"]["steps"].pop(1),
            "applies every workflow step, in order",
        ),
        (lambda v: v["concepts"][0].update(topic="missing"), "declared topic"),
        (lambda v: v.update(count=3), "Extra inputs are not permitted"),
        (lambda v: mock_question(v)["statement"].pop(), "needs a code snippet, diagram"),
        (lambda v: v["patterns"][0]["drill"][0].pop("blocks"), "Drill d1 needs a code snippet"),
        (
            lambda v: v["patterns"][1]["example"]["blocks"].pop(),
            "worked practice question needs a code snippet",
        ),
        (
            lambda v: v["patterns"][0]["example"]["steps"][1].update(
                answer=[{"kind": "text", "title": "I", "sources": ["slides"], "paragraphs": ["x"]}]
            ),
            "the past question is text only",
        ),
    ],
)
def test_hard_rules_reject_wrong_data(document: dict, mutate: Callable, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ExamContent.model_validate(change(document, mutate))


def test_bundled_files_may_serve_several_sittings_through_disjoint_pages(document: dict) -> None:
    def bundle(value: dict) -> None:
        shared = sitting(value, "ws22")["variants"][0]["sources"][0]
        shared["pages"] = "1-2"
        moved = copy.deepcopy(shared) | {"pages": "3-4"}
        sitting(value, "ss19")["variants"][0]["sources"].append(moved)

    ExamContent.model_validate(change(document, bundle))

    def overlap(value: dict) -> None:
        bundle(value)
        sitting(value, "ss19")["variants"][0]["sources"][-1]["pages"] = "2-5"

    with pytest.raises(ValidationError, match="overlap"):
        ExamContent.model_validate(change(document, overlap))


def test_a_near_verbatim_forecast_is_rejected_but_a_variant_is_not(document: dict) -> None:
    past = sitting(document, "ws23")["variants"][0]["questions"][0]["statement"][0]

    def copied(value: dict) -> None:
        block = copy.deepcopy(past) | {"sources": ["slides"]}
        mock_question(value)["statement"][0] = block

    with pytest.raises(ValidationError, match="nearly copies past question ws23-a-1"):
        ExamContent.model_validate(change(document, copied))


def test_concept_progress_survives_detail_edits(document: dict) -> None:
    base = ExamContent.model_validate(document).concepts[0]
    edited = ExamContent.model_validate(
        change(document, lambda v: v["concepts"][0]["details"][0].update(paragraphs=["Edited."]))
    ).concepts[0]
    assert concept_revision(base) == concept_revision(edited)
    reworded = ExamContent.model_validate(
        change(
            document, lambda v: v["concepts"][0].update(line="Observers subscribe to a subject.")
        )
    ).concepts[0]
    assert concept_revision(base) != concept_revision(reworded)


def test_empty_exam_prep_is_rejected(document: dict, tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="needs past exams"):
        ExamContent.model_validate({"course_key": document["course_key"]})
