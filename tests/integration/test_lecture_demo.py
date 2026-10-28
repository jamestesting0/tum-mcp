import json
from pathlib import Path

from typer.testing import CliRunner

from tum_mcp.cli import app


def test_base_demo_omits_lecture_until_explicit_option(tmp_path: Path) -> None:
    root = tmp_path / "base"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    assert not (root / "app/lectures.json").exists()
    result = CliRunner().invoke(app, ["study", "demo", str(root), "--lectures"])
    assert result.exit_code != 0 and not (root / "app/lectures.json").exists()


def test_optional_demo_and_edited_asset_preservation(
    lecture_extension: Path, tmp_path: Path
) -> None:
    root = tmp_path / "notes"
    args = ["study", "demo", str(root), "--lectures"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    notes = (root / "app/lectures.json").read_bytes()
    payload = json.loads(
        (root / "app/data.mjs").read_text().removeprefix("export default ").removesuffix(";\n")
    )
    assert payload["workspaces"] == ["study", "exercises", "lectures", "exam"]
    assert len(payload["lectures"]["lectures"]) == 1
    figure = next((root / ".tum-mcp/lecture-assets").iterdir())
    figure.write_bytes(b"Personal altered image")
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0 and "preserved" in str(result.exception)
    assert figure.read_bytes() == b"Personal altered image"
    assert (root / "app/lectures.json").read_bytes() == notes
