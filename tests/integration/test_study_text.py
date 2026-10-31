import json
from pathlib import Path

import pytest
from material_fixture import material_project, pdf_bytes
from PIL import Image
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_text import document_text, find_sources, page_images


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


def test_page_images_let_any_host_look_at_a_slide_and_are_rendered_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given slides and a text note, for an agent whose host cannot open PDFs.
    root = material_project(
        tmp_path,
        {"slides": ("content", pdf_bytes(["One", "Two", "Three"])), "notes": ("other", b"# Notes")},
    )
    runner = CliRunner()
    # When it asks for two pages with images.
    command = ["study", "text", str(root), "--key", "slides", "--pages", "2-3", "--images"]
    result = runner.invoke(app, command)
    # Then each page names a sharp PNG inside the project, beside the PDF it came from.
    assert result.exit_code == 0, result.output
    view = json.loads(result.output)
    assert view["path"] == "materials/content/material-slides.pdf"
    for page in view["pages"]:
        with Image.open(root / page["image"]) as picture:
            assert picture.format == "PNG" and abs(max(picture.size) - 1600) <= 1

    def no_render(*_args: object) -> None:
        raise AssertionError("cached page images must not be rendered again")

    monkeypatch.setattr("tum_mcp.moodle.extract_worker.render_pdf_pages", no_render)
    assert page_images(root, "slides", [2, 3]) == {
        page["number"]: page["image"] for page in view["pages"]
    }
    assert runner.invoke(app, ["study", "text", str(root), "--key", "notes", "--images"]).exit_code


def test_find_lists_sources_and_ranks_pages_that_mention_every_word(tmp_path: Path) -> None:
    pages = [
        "Search intro",
        "Greedy search uses a heuristic",
        "",
        "Heuristic search: A* adds the heuristic h to the path cost g",
    ]
    root = material_project(
        tmp_path,
        {
            "search-slides": ("content", pdf_bytes(pages)),
            "notes": ("other", "# Notes\nComposite pattern, the \ufb01rst one".encode()),
        },
    )
    catalogue = find_sources(root, None)["sources"]
    assert [(item["key"], item["kind"], item["status"]) for item in catalogue] == [
        ("notes", "other", "current"),
        ("search-slides", "content", "current"),
    ]
    result = find_sources(root, "HEURISTIC search")
    assert [(hit["key"], hit["page"]) for hit in result["pages"]] == [
        ("search-slides", 4),
        ("search-slides", 2),
    ]
    assert result["pages"][0]["path"] == "materials/content/material-search-slides.pdf"
    assert "A* adds the heuristic" in result["pages"][0]["snippet"]
    assert result["title_matches"] == [] and result["pages_without_text"] == {"search-slides": 1}
    assert [hit["key"] for hit in find_sources(root, "first composite")["pages"]] == ["notes"]
    runner = CliRunner()
    command = ["study", "find", str(root), "heuristic", "--kind", "content", "--limit", "1"]
    output = runner.invoke(app, command)
    assert output.exit_code == 0, output.output
    view = json.loads(output.output)
    assert view["total_pages"] == 2 and [hit["page"] for hit in view["pages"]] == [4]
    assert view["not_searched"] == {}
    (root / "materials/other/material-notes.md").write_bytes(b"# Notes\nEdited locally")
    edited = find_sources(root, "composite")
    assert edited["pages"] == [] and list(edited["not_searched"].values()) == [["notes"]]
