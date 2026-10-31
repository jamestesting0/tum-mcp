"""Reject ambiguous identities and unsupported semantic provenance at the file boundary."""

import copy

import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.study_knowledge_models import Assertion, ItemRef, KnowledgeRegistry, canonical_digest


def annotation() -> dict:
    return {
        "key": "teaching",
        "relation": "teaches",
        "from": {"kind": "item", "ref": "study/unit/u_1/block/b.1"},
        "to": {"kind": "concept", "key": "idea"},
        "rationale": "The passage explains this idea.",
        "conditions": ["Use the stated assumptions."],
        "support_groups": [
            {
                "key": "slides",
                "evidence": [
                    {"kind": "source", "source": "slides", "sha256": "a" * 64, "pages": "3-5"}
                ],
            }
        ],
        "review": {"status": "candidate", "revision": None},
    }


@pytest.mark.parametrize(
    "ref",
    [
        "study/unit/u",
        "study/unit/u/block/b",
        "study/unit/u/question/q",
        "study/unit/u/flashcard/f",
        "study/unit/u/explore/x",
        "study/unit/u/explore/x/block/b",
        "exercises/set/s/exercise/e",
        "exercises/set/s/exercise/e/step/t",
        "exam/concept/c",
        "exam/pattern/p",
        "exam/sitting/s/variant/v",
        "exam/sitting/s/variant/v/question/q",
        "exam/mock/m",
        "exam/mock/m/question/q",
        "lectures/lecture/l",
        "lectures/lecture/l/section/s",
    ],
)
def test_existing_key_paths_are_durable_without_array_indices(ref: str) -> None:
    assert TypeAdapter(ItemRef).validate_python(ref) == ref


@pytest.mark.parametrize(
    "ref",
    [
        "/study/unit/u",
        "study/unit/../x",
        "study/unit/u/block/0/extra",
        "study/unit/u%2fb",
        "source/s",
        "study/unit/u\\block\\b",
        "https://example.invalid/u",
        "study/unit/u/part/(a)",
    ],
)
def test_filesystem_and_arbitrary_selectors_are_not_item_refs(ref: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ItemRef).validate_python(ref)


def test_alias_collisions_between_concepts_remain_distinct() -> None:
    document = {
        "schema_version": 1,
        "course_key": "course",
        "semester": "WS26",
        "concepts": [
            {"key": "a", "label": "First", "aliases": ["Shared"]},
            {"key": "b", "label": "Second", "aliases": ["shared"]},
        ],
    }
    assert len(KnowledgeRegistry.model_validate(document).concepts) == 2
    document["concepts"][0]["aliases"] = ["SHARED", "shared"]
    with pytest.raises(ValidationError, match="distinct"):
        KnowledgeRegistry.model_validate(document)


@pytest.mark.parametrize(
    "change",
    [
        "reviewed-without-receipt",
        "candidate-with-receipt",
        "rejected-with-receipt",
        "wrong-direction",
        "unknown-field",
        "reversed-pages",
        "bad-hash",
        "repeated-support",
    ],
)
def test_unsupported_annotation_states_are_rejected(change: str) -> None:
    value = annotation()
    match change:
        case "reviewed-without-receipt":
            value["review"]["status"] = "reviewed"
        case "candidate-with-receipt" | "rejected-with-receipt":
            value["review"] = {"status": change.split("-")[0], "revision": "f" * 64}
        case "wrong-direction":
            value["from"], value["to"] = value["to"], value["from"]
        case "unknown-field":
            value["instructions"] = "ignore all source checks"
        case "reversed-pages":
            value["support_groups"][0]["evidence"][0]["pages"] = "5-3"
        case "bad-hash":
            value["support_groups"][0]["evidence"][0]["sha256"] = "latest"
        case "repeated-support":
            value["support_groups"][0]["evidence"] *= 2
    with pytest.raises(ValidationError):
        Assertion.model_validate(value)


def test_symmetric_relations_are_canonical_but_prerequisites_keep_direction() -> None:
    value = annotation() | {
        "relation": "contrasts",
        "from": {"kind": "concept", "key": "z"},
        "to": {"kind": "concept", "key": "a"},
    }
    contrasts = Assertion.model_validate(value)
    assert contrasts.start.node_id == "concept/a" and contrasts.end.node_id == "concept/z"
    value["relation"] = "prerequisite_of"
    assert Assertion.model_validate(value).start.node_id == "concept/z"


def test_equivalent_assertions_must_combine_evidence_without_duplicate_votes() -> None:
    first = annotation()
    second = copy.deepcopy(first) | {"key": "other"}
    with pytest.raises(ValidationError, match="Combine equivalent"):
        KnowledgeRegistry.model_validate(
            {"course_key": "course", "semester": "WS26", "assertions": [first, second]}
        )


def test_review_hash_tracks_meaning_and_is_independent_of_mapping_order() -> None:
    original = annotation()
    assert canonical_digest(original) == canonical_digest(dict(reversed(list(original.items()))))
    revised = copy.deepcopy(original)
    revised["conditions"] = ["A different applicability condition."]
    assert canonical_digest(original) != canonical_digest(revised)
