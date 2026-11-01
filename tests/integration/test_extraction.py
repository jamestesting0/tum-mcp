import io
import subprocess
import sys

import psutil
import pytest
from material_fixture import pdf_bytes
from PIL import Image, ImageDraw, ImageFont
from pypdf import apply_configuration

from tum_mcp.moodle import extract_worker
from tum_mcp.moodle.errors import MoodleError
from tum_mcp.moodle.extract_worker import read_pdf_text, run_extraction
from tum_mcp.moodle.extraction import PdfText


def test_worker_extracts_text_with_process_limits() -> None:
    result = run_extraction(b"Known course material.", "text/plain")
    assert result.pages[0].text == "Known course material."


def test_memory_bound_measures_the_worker_where_a_sandbox_hides_other_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a sandbox that denies listing every process, as macOS seatbelt does.
    def denied(self: psutil.Process, recursive: bool = False) -> list[psutil.Process]:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(psutil.Process, "children", denied)
    # Then the bound measures the worker itself instead of failing the extraction.
    assert extract_worker._tree_memory(psutil.Process()) > 0


def test_memory_bound_survives_a_child_that_exits_while_it_is_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a child that exits while Windows lists the worker's process tree.
    def vanished(self: psutil.Process, recursive: bool = False) -> list[psutil.Process]:
        raise psutil.NoSuchProcess(4040)

    monkeypatch.setattr(psutil.Process, "children", vanished)
    # Then this poll measures the worker itself; the next poll lists the tree again.
    assert extract_worker._tree_memory(psutil.Process()) > 0


def test_a_page_beyond_pypdf_parsing_limits_is_read_with_pdfium() -> None:
    # Given slides that pypdf reads normally.
    body = pdf_bytes(["A* uses f(n) = g(n) + h(n)", "Monte Carlo localization"])
    normal = PdfText(body)
    assert [normal.text(index).strip() for index in range(normal.count)] == [
        "A* uses f(n) = g(n) + h(n)",
        "Monte Carlo localization",
    ]
    assert normal.fallback == []
    # When each page's content stream exceeds pypdf's token budget, as one Lecture 14 slide did.
    with apply_configuration(stream_parsing_work_maximum_count=3):
        limited = PdfText(body)
        texts = [limited.text(index).strip() for index in range(limited.count)]
    # Then PDFium reads those pages instead of the whole document failing.
    assert texts == ["A* uses f(n) = g(n) + h(n)", "Monte Carlo localization"]
    assert limited.fallback == [1, 2]


def test_a_pdf_pypdf_cannot_open_is_still_read_and_indexed() -> None:
    # Given a PDF whose cross-reference table is damaged; pypdf refuses it, PDFium repairs it.
    pages = ["Alpha page of slides", "Beta page of slides"]
    good = pdf_bytes(pages)
    body = good[: good.rindex(b"startxref")] + b"startxref\n9\n%%EOF\n"
    # When the study text worker and the Moodle extractor read it.
    text = read_pdf_text(body)
    extracted = run_extraction(body, "application/pdf")
    # Then both return every page, and the Moodle result says a second reader was used.
    assert [page["text"].strip() for page in text["pages"]] == pages
    assert [page.text.strip() for page in extracted.pages] == pages
    assert len(extracted.warnings) == 1 and "second PDF reader" in extracted.warnings[0]


def test_local_ocr_reads_a_scanned_page() -> None:
    image = Image.new("RGB", (1400, 400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=60)
    draw.text((50, 100), "REAL TIME SYSTEMS", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PDF")
    result = run_extraction(buffer.getvalue(), "application/pdf")
    assert "REAL TIME SYSTEMS" in result.pages[0].text
    assert "OCR" in result.warnings[0]


def test_timeout_terminates_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    original_popen = subprocess.Popen
    workers: list[subprocess.Popen[bytes]] = []
    children: list[psutil.Process] = []

    def sleeping_worker(*args, **kwargs) -> subprocess.Popen[bytes]:
        process = original_popen(
            [
                sys.executable,
                "-c",
                "import subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                "print(child.pid, flush=True); child.wait()",
            ],
            **kwargs,
        )
        assert process.stdout is not None
        children.append(psutil.Process(int(process.stdout.readline())))
        workers.append(process)
        return process

    monkeypatch.setattr(extract_worker.subprocess, "Popen", sleeping_worker)
    monkeypatch.setattr(extract_worker, "EXTRACTION_SECONDS", 0)

    with pytest.raises(MoodleError, match="extraction time or memory limits"):
        run_extraction(b"ignored", "text/plain")

    assert len(workers) == 1
    assert workers[0].returncode is not None
    _, alive = psutil.wait_procs(children, timeout=5)
    assert not alive
