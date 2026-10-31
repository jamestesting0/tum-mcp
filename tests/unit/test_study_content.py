import json
from collections import deque
from importlib.resources import files
from pathlib import Path

import httpx2
import pytest
from pydantic import ValidationError

from tum_mcp.artemis import Artemis
from tum_mcp.credentials import Credential
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Account, Provider
from tum_mcp.study_content import FormulaBlock, Objective, StudyContent
from tum_mcp.study_models import Resource
from tum_mcp.transport import API


def test_explore_preserves_legacy_core_progress_but_changes_teaching_review() -> None:
    from tum_mcp.study_build import unit_revision
    from tum_mcp.study_review import revision

    payload = json.loads(
        (Path(__file__).parents[1] / "fixtures/course_app/content.json").read_bytes()
    )
    before = StudyContent.model_validate(payload).units[1]
    assert before.key == "bfs"
    assert (
        unit_revision(before) == "3c3f0059e28219e78082801a80a63cc0e63d05e9372bbdd27a17f703df1d42b5"
    )
    assert revision(before) == "f15badad09e4ed7e"
    material = {
        "key": "origin",
        "title": "Where the idea came from",
        "sources": payload["units"][1]["sources"],
        "blocks": [
            {
                "key": "history",
                "kind": "text",
                "sources": [before.sources[0].key],
                "title": "Historical context",
                "paragraphs": ["A synthetic supporting passage."],
            }
        ],
    }
    payload["units"][1]["explore"] = [material]
    after = StudyContent.model_validate(payload).units[1]
    assert unit_revision(after) == unit_revision(before)
    assert revision(after) != revision(before)
    payload["units"][1]["explore"] = []
    empty = StudyContent.model_validate(payload).units[1]
    assert empty.model_dump_json() == before.model_dump_json()
    assert revision(empty) == revision(before)
    payload["units"][1]["blocks"][0]["title"] = "Changed core explanation"
    assert unit_revision(StudyContent.model_validate(payload).units[1]) != unit_revision(before)


@pytest.mark.parametrize("invalid", ["empty", "missing_key", "duplicate_key", "undeclared_source"])
def test_explore_blocks_have_scoped_keys_and_sources(invalid: str) -> None:
    payload = json.loads(
        (Path(__file__).parents[1] / "fixtures/course_app/content.json").read_bytes()
    )
    unit = payload["units"][0]
    block = {
        "kind": "text",
        "key": "background",
        "sources": [unit["sources"][0]["key"]],
        "paragraphs": ["A synthetic optional explanation."],
    }
    material = {"key": "origin", "title": "Origins", "sources": unit["sources"], "blocks": [block]}
    match invalid:
        case "empty":
            material["blocks"] = []
        case "missing_key":
            block.pop("key")
        case "duplicate_key":
            material["blocks"].append(block.copy())
        case "undeclared_source":
            block["sources"] = ["not-declared"]
    unit["explore"] = [material]
    with pytest.raises(ValidationError):
        StudyContent.model_validate(payload)


@pytest.mark.parametrize("text", [r"Use \(x", r"Use x\)", r"Use \(\href{https://x}{x}\)"])
def test_invalid_inline_math_is_rejected_without_treating_prose_as_html(text: str) -> None:
    with pytest.raises(ValidationError):
        Objective(key="notation", text=text)
    assert Objective(key="cost", text="Cost $5 < $10.").text == "Cost $5 < $10."


def test_mathml_refuses_script_links_foreign_xml_and_entity_expansion() -> None:
    base = {
        "kind": "formula",
        "title": "Safe math",
        "sources": ["s"],
        "plain": "x",
        "symbols": [{"symbol": "x", "meaning": "A variable."}],
        "conditions": "None.",
    }
    for markup in (
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><script>bad()</script></math>',
        '<math xmlns="http://www.w3.org/1998/Math/MathML" href="https://external.invalid"/>',
        "<math><mi>x</mi></math>",
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi xmlns="">x</mi></math>',
        '<!DOCTYPE math [<!ENTITY a "expanded">]><math xmlns="http://www.w3.org/1998/Math/MathML">&a;</math>',
    ):
        with pytest.raises(ValidationError):
            FormulaBlock.model_validate(base | {"mathml": markup})


def test_sample_frontier_and_answer_match_an_independent_bfs() -> None:
    path = Path(__file__).parents[1] / "fixtures/course_app/content.json"
    content = StudyContent.model_validate_json(path.read_bytes())
    unit = next(unit for unit in content.units if unit.key == "bfs")
    diagram = next(block for block in unit.blocks if block.kind == "diagram")
    adjacency = {node.key: [] for node in diagram.nodes}
    for edge in diagram.edges:
        adjacency[edge.start].append(edge.end)
        adjacency[edge.end].append(edge.start)
    queue, seen = deque(["a"]), {"a"}
    expected = [tuple(queue)]
    while queue:
        vertex = queue.popleft()
        for neighbor in sorted(adjacency[vertex]):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
        expected.append(tuple(queue))
    assert tuple(frame.frontier for frame in diagram.frames[:-1]) == tuple(expected)
    question = next(q for q in unit.questions if q.key == "frontier")
    answer = next(option for option in question.options if option.key == question.correct)
    assert answer.text == ", ".join(key.upper() for key in expected[2])


def test_question_schema_rejects_an_answer_key_missing_from_its_options() -> None:
    path = files("tum_mcp") / "bundled/course_app/example/content.json"
    content = json.loads(path.read_bytes())
    content["units"][0]["questions"][0]["correct"] = "missing"
    with pytest.raises(ValidationError):
        StudyContent.model_validate(content)


def test_source_links_cannot_embed_credentials() -> None:
    with pytest.raises(ValidationError):
        Resource(
            key="s",
            binding="moodle",
            kind="content",
            title="Source",
            url="https://student:password@example.invalid/source",
        )


@pytest.mark.parametrize("kind", ["programming", "text", "modeling", "file-upload"])
def test_released_non_quiz_statement_types_are_read_without_creating_participation(
    kind: str,
) -> None:
    account = Account(
        provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7", courses=(9,)
    )
    exercise = {
        "id": 4,
        "type": kind,
        "title": "Statement",
        "course": {"id": 9},
        "releaseDate": "2020-01-01T00:00:00Z",
        "problemStatement": "Read the model.",
    }
    visited = []

    def request(req: httpx2.Request) -> httpx2.Response:
        visited.append((req.method, req.url.path))
        routes = {
            "/api/core/public/account": {"id": 7, "login": "synthetic"},
            "/api/course/courses/9/exercises-for-overview": {"exercises": [exercise]},
            "/api/exercise/exercises/4/details": {"exercise": exercise},
        }
        return httpx2.Response(200, json=routes[req.url.path])

    provider = Artemis(
        API(account, Credential(account_id=account.id), httpx2.MockTransport(request))
    )
    result = provider.exercise(9, 4)
    assert result.exercise.type == kind
    assert all(method == "GET" for method, _ in visited)


def test_even_internal_start_is_denied_before_loading_credentials_or_sending_http() -> None:
    account = Account(provider=Provider.ARTEMIS, origin="https://artemis.tum.de", principal="7")
    api = API(account)
    with pytest.raises(CampusError) as error:
        api._start_once(4, practice=False)
    assert error.value.code == Code.CAPABILITY_UNSUPPORTED
    with pytest.raises(CampusError) as error:
        api._request("POST", "/api/core/public/account", None)
    assert error.value.code == Code.SCOPE_DENIED


def _headed(levels: list[int | None]) -> dict:
    content = json.loads(
        (Path(__file__).parents[1] / "fixtures/course_app/content.json").read_bytes()
    )
    unit = content["units"][0]
    template = next(block for block in unit["blocks"] if block["kind"] == "text")
    blocks = []
    for index, level in enumerate(levels):
        block = {
            key: value for key, value in template.items() if key not in {"title", "level", "key"}
        }
        if level is not None:
            block.update(title=f"Heading {index}", level=level)
        blocks.append(block)
    unit["blocks"] = blocks
    return content


def test_titled_blocks_form_an_outline_and_untitled_blocks_continue_a_section() -> None:
    # Sections, subsections and untitled continuations descend one level at a time.
    StudyContent.model_validate(_headed([1, None, 2, 3, None, 2, 1]))
    # A lesson may open with an untitled passage before its first heading.
    StudyContent.model_validate(_headed([None, 1, 2]))


@pytest.mark.parametrize("levels", [[2], [1, 3], [1, None, 3]])
def test_a_skipped_heading_level_is_rejected(levels: list[int | None]) -> None:
    with pytest.raises(ValidationError, match="one level deeper at a time"):
        StudyContent.model_validate(_headed(levels))
