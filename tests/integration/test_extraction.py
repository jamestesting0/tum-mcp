import io
import subprocess
import sys

import psutil
import pytest
from PIL import Image, ImageDraw, ImageFont

from tum_moodle import extract_worker
from tum_moodle.errors import MoodleError
from tum_moodle.extract_worker import run_extraction


def test_worker_extracts_text_with_process_limits() -> None:
    result = run_extraction(b"Known course material.", "text/plain")
    assert result.pages[0].text == "Known course material."


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
