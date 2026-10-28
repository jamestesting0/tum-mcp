import json
from pathlib import Path

import pytest
from material_fixture import material_project, pdf_bytes
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_text import document_text


def test_pdf_text_is_extracted_once_per_hash_and_marks_pages_without_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = material_project(
        tmp_path,
        {"exam-2024": ("exam", pdf_bytes(["Task 1 Observer pattern", "", "Task 2 Strategy"]))},
    )
    record = document_text(root, "exam-2024")
    assert [page.text.strip() for page in record.pages] == [
        "Task 1 Observer pattern",
        "",
        "Task 2 Strategy",
    ]
    assert record.kind == "pdf" and record.needs_visual == (2,)
    cache = root / f".tum-mcp/cache/text/{record.sha256}.json"
    assert cache.is_file()

    def no_extraction(*_args: object) -> None:
        raise AssertionError("cached text must not be extracted again")

    monkeypatch.setattr("tum_mcp.study_text._extract", no_extraction)
    assert document_text(root, "exam-2024") == record


def test_cli_returns_a_page_range_and_rejects_changed_materials(tmp_path: Path) -> None:
    root = material_project(
        tmp_path,
        {
            "slides": ("content", pdf_bytes(["One", "Two", "Three"])),
            "notes": ("other", b"# Notes\nComposite pattern"),
            "binary": ("other", b"GIF89a\x01\x00\xff\xfe\x00"),
        },
    )
    runner = CliRunner()
    result = runner.invoke(app, ["study", "text", str(root), "--key", "slides", "--pages", "2-3"])
    assert result.exit_code == 0, result.output
    view = json.loads(result.output)
    assert view["total_pages"] == 3 and [page["number"] for page in view["pages"]] == [2, 3]
    notes = json.loads(runner.invoke(app, ["study", "text", str(root), "--key", "notes"]).output)
    assert notes["kind"] == "text" and "Composite pattern" in notes["pages"][0]["text"]
    bad = runner.invoke(app, ["study", "text", str(root), "--key", "slides", "--pages", "3-9"])
    assert bad.exit_code != 0
    (root / "materials/content/material-slides.pdf").write_bytes(pdf_bytes(["Edited"]))
    with pytest.raises(CampusError) as error:
        document_text(root, "slides")
    assert error.value.code == Code.STALE_RESULT
    with pytest.raises(CampusError) as error:
        document_text(root, "binary")
    assert error.value.code == Code.CAPABILITY_UNSUPPORTED
