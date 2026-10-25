import json
from pathlib import Path

from tum_mcp.study_build import build


def test_reorganizing_folders_keeps_unit_progress_revisions(project: Path) -> None:
    def app_data() -> dict:
        text = (project / "study/data.mjs").read_text()
        return json.loads(text.removeprefix("export default ").removesuffix(";\n"))

    before = app_data()
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    content["units"][0]["path"] = ["Week 1", "Foundations"]
    path.write_text(json.dumps(content))
    build(project)
    after = app_data()
    assert after["units"][0]["path"] == ["Week 1", "Foundations"]
    assert [u["revision"] for u in after["units"]] == [u["revision"] for u in before["units"]]


def test_latex_is_compiled_into_generated_data_without_rewriting_author_input(
    project: Path,
) -> None:
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    formula = next(b for b in content["units"][0]["blocks"] if b["kind"] == "formula")
    formula.pop("mathml", None)
    formula["latex"] = r"\sum_{v\in V}\deg(v)=2|E|"
    desired = json.dumps(content)
    path.write_text(desired)
    build(project)
    assert path.read_text() == desired
    output = (project / "study/data.mjs").read_text()
    data = json.loads(output.removeprefix("export default ").removesuffix(";\n"))
    rendered = next(b for b in data["units"][0]["blocks"] if b["kind"] == "formula")
    assert rendered["latex"] == formula["latex"]
    assert "<math" in rendered["mathml"] and "<script" not in rendered["mathml"]


def test_inline_notation_is_compiled_once_while_code_and_currency_stay_literal(
    project: Path,
) -> None:
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    unit = content["units"][0]
    unit["summary"] = r"Use \(v_i\) for a vertex. A notebook costs $5."
    unit["flashcards"][0]["back"] = r"The vertex is \(v_i\)."
    code = next(b for u in content["units"] for b in u["blocks"] if b["kind"] == "code")
    code["code"] = r'print("\(literal code\)")'
    original = json.dumps(content)
    path.write_text(original)
    build(project, publish=False)
    data = json.loads(
        (project / "study/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    assert "v_i" in data["inlineMath"]
    assert "<msub>" in data["inlineMath"]["v_i"]
    assert "literal code" not in data["inlineMath"]
    assert data["units"][0]["summary"] == unit["summary"]
    assert path.read_text() == original
