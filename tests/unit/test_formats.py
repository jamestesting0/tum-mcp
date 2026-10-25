import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from tum_mcp.moodle import extraction
from tum_mcp.moodle.extraction import extract_office


def test_word_document_text_is_extracted() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="urn:word"><w:p><w:r><w:t>Deadline</w:t></w:r></w:p></w:document>',
        )
    result = extract_office(buffer.getvalue())
    assert result.pages[0].text == "Deadline"
    assert result.pages[0].unit == "section"


def test_powerpoint_slides_keep_numeric_order() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for number in (10, 2, 1):
            archive.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<a:sld xmlns:a="urn:slide"><a:t>Slide {number}</a:t></a:sld>',
            )
    assert [page.text for page in extract_office(buffer.getvalue()).pages] == [
        "Slide 1",
        "Slide 2",
        "Slide 10",
    ]


def test_ocr_finds_intel_homebrew_without_shell_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extraction.shutil, "which", lambda _: None)
    executable = Path("/usr/local/bin/tesseract")
    scan = (tmp_path / "scan space.png").resolve()
    monkeypatch.setattr(Path, "is_file", lambda path: path == executable)

    def run(
        command: list[str], *, check: bool, capture_output: bool, timeout: int
    ) -> subprocess.CompletedProcess[bytes]:
        assert command == [str(executable), str(scan), "stdout", "-l", "eng"]
        assert check and capture_output and timeout == 45
        return subprocess.CompletedProcess(command, 0, stdout=b"Scanned lecture text\n")

    monkeypatch.setattr(extraction.subprocess, "run", run)
    assert extraction.image_text(scan) == "Scanned lecture text"
