import base64
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Final

import psutil

from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.extraction import extract
from tum_mcp.moodle.models import Extracted

EXTRACTION_SECONDS: Final = 60
PAGE_IMAGE_EDGE: Final = 1600


class ExtractionLimit(MoodleError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.EXTRACTION_FAILED, "Document exceeded extraction time or memory limits."
        )


def kill_worker(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        return
    with suppress(psutil.NoSuchProcess):
        for child in psutil.Process(process.pid).children(recursive=True):
            with suppress(psutil.NoSuchProcess):
                child.kill()
    process.kill()


def run_extraction(body: bytes, content_type: str) -> Extracted:
    return Extracted.model_validate_json(_run_worker(body, content_type))


def validate_pdf(body: bytes) -> int:
    """Check every PDF page in the bounded worker without OCR or rewriting bytes."""
    if len(body) > 50 * 1024 * 1024 or not body.startswith(b"%PDF-"):
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "A PDF under 50 MiB is required.")
    try:
        result = json.loads(_run_worker(body, "application/x-tum-pdf-validation"))
        pages = result["pages"]
        if not isinstance(pages, int) or isinstance(pages, bool) or not 1 <= pages <= 1500:
            raise ValueError
        return pages
    except (ValueError, KeyError, TypeError):
        raise MoodleError(ErrorCode.EXTRACTION_FAILED, "PDF validation failed.") from None


def render_pdf_pages(body: bytes, numbers: Sequence[int]) -> list[bytes]:
    """Render up to 12 PDF pages to PNG, long edge 1600 px, in the bounded worker."""
    if not 1 <= len(numbers) <= 12 or len(body) > 50 * 1024 * 1024 or not body.startswith(b"%PDF-"):
        raise MoodleError(
            ErrorCode.RESOURCE_UNSUPPORTED, "Render 1 to 12 pages of a PDF under 50 MiB."
        )
    try:
        pages = ",".join(str(number) for number in numbers)
        result = json.loads(_run_worker(body, f"application/x-tum-pdf-render:{pages}"))
        return [base64.b64decode(image, validate=True) for image in result["images"]]
    except (ValueError, KeyError, TypeError):
        raise MoodleError(ErrorCode.EXTRACTION_FAILED, "PDF pages could not be rendered.") from None


def read_pdf_text(body: bytes) -> dict:
    """Read every page's text layer in one bounded worker pass, without OCR."""
    if len(body) > 50 * 1024 * 1024 or not body.startswith(b"%PDF-"):
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "A PDF under 50 MiB is required.")
    try:
        result = json.loads(_run_worker(body, "application/x-tum-pdf-text"))
        if not isinstance(result, dict) or not isinstance(result.get("pages"), list):
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise MoodleError(ErrorCode.EXTRACTION_FAILED, "PDF text could not be read.") from None


def _run_worker(body: bytes, content_type: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="tum-moodle-extract-") as directory:
        path = Path(directory) / "document"
        path.write_bytes(body)
        with subprocess.Popen(
            [sys.executable, "-m", "tum_mcp.moodle.extract_worker", str(path), content_type],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name == "posix",
        ) as process:
            deadline = time.monotonic() + EXTRACTION_SECONDS
            observed = psutil.Process(process.pid)
            while True:
                try:
                    output, _ = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    memory = _tree_memory(observed)
                    if memory > 512 * 1024**2 or time.monotonic() > deadline:
                        kill_worker(process)
                        process.communicate()
                        raise ExtractionLimit() from None
            if process.returncode != 0:
                raise MoodleError(ErrorCode.EXTRACTION_FAILED, "Document could not be extracted.")
            return output


def _tree_memory(worker: psutil.Process) -> int:
    """Resident memory of the worker and its children. Sandboxes such as macOS seatbelt deny
    listing every process, so the worker's own memory is the bound there."""
    try:
        children = worker.children(recursive=True)
    except (psutil.AccessDenied, PermissionError):
        children = []
    try:
        return sum(process.memory_info().rss for process in [worker, *children])
    except psutil.NoSuchProcess:
        return 0


if __name__ == "__main__":
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    body = Path(sys.argv[1]).read_bytes()
    if sys.argv[2].startswith("application/x-tum-pdf-render:"):
        import pypdfium2

        numbers = [int(value) for value in sys.argv[2].split(":", 1)[1].split(",")]
        document = pypdfium2.PdfDocument(body)
        if not 1 <= len(numbers) <= 12 or not all(1 <= n <= len(document) for n in numbers):
            raise ValueError("Invalid page range")
        images = []
        for number in numbers:
            page = document[number - 1]
            bitmap = page.render(scale=PAGE_IMAGE_EDGE / max(page.get_size()))
            try:
                output = io.BytesIO()
                bitmap.to_pil().save(output, format="PNG")
            finally:
                bitmap.close()
                page.close()
            images.append(base64.b64encode(output.getvalue()).decode("ascii"))
        document.close()
        sys.stdout.write(json.dumps({"images": images}))
    elif sys.argv[2].startswith("application/x-tum-pdf-"):
        from tum_mcp.moodle.extraction import PdfText

        pdf = PdfText(body, strict=True)
        if pdf.encrypted or not 1 <= pdf.count <= 1500:
            raise ValueError("Unsupported PDF")
        if sys.argv[2] == "application/x-tum-pdf-validation":
            if pdf.reader is None:
                for index in range(pdf.count):
                    pdf.pdfium[index].close()
            else:
                for page in pdf.reader.pages:
                    _ = page.mediabox
                    _ = page.get_contents()
            sys.stdout.write(json.dumps({"pages": pdf.count}))
        elif sys.argv[2] == "application/x-tum-pdf-text":
            pages, total, truncated = [], 0, False
            for index in range(pdf.count):
                extracted = pdf.text(index)[:200_000] if not truncated else ""
                total += len(extracted)
                if total > 2_000_000:
                    extracted, truncated = "", True
                pages.append(
                    {
                        "number": index + 1,
                        "text": extracted,
                        "text_available": bool(extracted.strip()),
                    }
                )
            sys.stdout.write(
                json.dumps({"pages": pages, "total_pages": len(pages), "truncated": truncated})
            )
        else:
            raise ValueError("Unknown PDF request")
    else:
        result = extract(body, sys.argv[2])
        sys.stdout.write(result.model_dump_json())
