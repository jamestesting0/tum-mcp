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
from tum_mcp.study_math import compile_latex
from tum_mcp.study_models import Resource
from tum_mcp.transport import API


@pytest.mark.parametrize(
    "expression",
    [r"\binom{n}{k}p^k(1-p)^{n-k}", r"\begin{bmatrix}1&0\\0&1\end{bmatrix}", r"\frac{a}{b}"],
)
def test_common_formula_forms_compile_to_safe_native_math(expression: str) -> None:
    # Given editable mathematical notation used in the component examples.
    # When the local compiler validates it for the renderer.
    result = compile_latex(expression)
    # Then binomial fences, matrices and fractions are renderable MathML.
    assert result.startswith('<math xmlns="http://www.w3.org/1998/Math/MathML"')
    assert "<mfrac" in result or "<mtable" in result


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
