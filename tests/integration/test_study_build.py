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
