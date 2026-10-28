import pytest
from pydantic import TypeAdapter, ValidationError

from tum_mcp.study_content import Block, has_visual

BLOCK = TypeAdapter(Block)


def class_diagram(**overrides: object) -> dict:
    value = {
        "kind": "uml",
        "title": "Composite",
        "sources": ["slides"],
        "diagram": "class",
        "description": "Leaf and Composite implement Component.",
        "classes": [
            {"key": "component", "name": "Component", "stereotype": "interface"},
            {"key": "leaf", "name": "Leaf", "operations": [{"text": "+ operation(): void"}]},
            {"key": "composite", "name": "Composite"},
        ],
        "relations": [
            {"start": "leaf", "end": "component", "kind": "realization"},
            {
                "start": "composite",
                "end": "component",
                "kind": "composition",
                "end_multiplicity": "0..*",
            },
        ],
    }
    return value | overrides


def sequence_diagram(**overrides: object) -> dict:
    value = {
        "kind": "uml",
        "title": "Notify",
        "sources": ["slides"],
        "diagram": "sequence",
        "description": "The subject notifies each observer.",
        "participants": [{"key": "s", "name": "s: Subject"}, {"key": "o", "name": "o: Observer"}],
        "messages": [
            {"start": "s", "end": "s", "text": "setState()"},
            {"start": "s", "end": "o", "text": "update()"},
            {"start": "o", "end": "s", "text": "done", "kind": "return"},
        ],
        "fragments": [{"kind": "loop", "condition": "each observer", "first": 1, "last": 2}],
    }
    return value | overrides


def test_uml_class_and_sequence_diagrams_validate_and_count_as_visuals() -> None:
    blocks = (BLOCK.validate_python(class_diagram()), BLOCK.validate_python(sequence_diagram()))
    assert [block.diagram for block in blocks] == ["class", "sequence"]
    assert has_visual(blocks[:1]) and has_visual(blocks[1:])


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            class_diagram(relations=[{"start": "leaf", "end": "x", "kind": "inheritance"}]),
            "unknown class",
        ),
        (
            class_diagram(relations=[{"start": "leaf", "end": "leaf", "kind": "inheritance"}]),
            "inherit from itself",
        ),
        (class_diagram(classes=[{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]), "distinct"),
        (
            class_diagram(messages=[{"start": "a", "end": "a", "text": "x"}]),
            "classes and relations only",
        ),
        (
            sequence_diagram(messages=[{"start": "s", "end": "z", "text": "x"}]),
            "unknown participant",
        ),
        (sequence_diagram(fragments=[{"kind": "alt", "first": 2, "last": 5}]), "existing messages"),
        (sequence_diagram(classes=[{"key": "a", "name": "A"}]), "participants and messages only"),
        (
            class_diagram(relations=[{"start": "leaf", "end": "component", "kind": "extends"}]),
            "Input should be",
        ),
    ],
)
def test_uml_diagrams_reject_inconsistent_structure(value: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        BLOCK.validate_python(value)
