import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Final

import psutil

from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.extraction import extract
from tum_mcp.moodle.models import Extracted

EXTRACTION_SECONDS: Final = 60


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


def read_pdf_pages(body: bytes, start: int, limit: int, *, images: bool = False) -> dict:
    """Read a small range of physical PDF pages in the same bounded worker."""
    if not 1 <= start <= 1500 or not 1 <= limit <= 12 or len(body) > 50 * 1024 * 1024:
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "PDF page range is invalid.")
    try:
        result = json.loads(
            _run_worker(body, f"application/x-tum-pdf-pages:{start}:{limit}:{int(images)}")
        )
        if not isinstance(result, dict) or not isinstance(result.get("pages"), list):
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise MoodleError(ErrorCode.EXTRACTION_FAILED, "PDF pages could not be read.") from None


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
                    try:
                        memory = sum(
                            child.memory_info().rss
                            for child in [observed, *observed.children(recursive=True)]
                        )
                    except psutil.NoSuchProcess:
                        memory = 0
                    if memory > 512 * 1024**2 or time.monotonic() > deadline:
                        kill_worker(process)
                        process.communicate()
                        raise ExtractionLimit() from None
            if process.returncode != 0:
                raise MoodleError(ErrorCode.EXTRACTION_FAILED, "Document could not be extracted.")
            return output


if __name__ == "__main__":
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    body = Path(sys.argv[1]).read_bytes()
    if sys.argv[2].startswith("application/x-tum-pdf-"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 1500:
            raise ValueError("Unsupported PDF")
        if sys.argv[2] == "application/x-tum-pdf-validation":
            for page in reader.pages:
                _ = page.mediabox
                _ = page.get_contents()
            sys.stdout.write(json.dumps({"pages": len(reader.pages)}))
        elif sys.argv[2] == "application/x-tum-pdf-text":
            pages, total, truncated = [], 0, False
            for index, page in enumerate(reader.pages):
                extracted = (page.extract_text() or "")[:200_000] if not truncated else ""
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
            import base64

            _, start, limit, images = sys.argv[2].split(":")
            first, count = int(start), int(limit)
            if not 1 <= first <= len(reader.pages) or not 1 <= count <= 12:
                raise ValueError("Invalid page range")
            selected = []
            labels = reader.page_labels if reader.trailer["/Root"].get("/PageLabels") else None
            pdfium = None
            if int(images):
                import pypdfium2

                pdfium = pypdfium2.PdfDocument(body)
            try:
                for index in range(first - 1, min(len(reader.pages), first - 1 + count)):
                    extracted = reader.pages[index].extract_text() or ""
                    item = {
                        "number": index + 1,
                        "text": extracted[:50000],
                        "text_available": bool(extracted.strip()),
                        "text_truncated": len(extracted) > 50000,
                    }
                    if labels is not None:
                        item["pdf_page_label"] = labels[index]
                    if pdfium is not None:
                        page = pdfium[index]
                        bitmap = page.render(scale=1)
                        try:
                            image = bitmap.to_pil()
                            image.thumbnail((1400, 1400))
                            output = io.BytesIO()
                            image.save(output, format="PNG", optimize=True)
                            item["image_png_base64"] = base64.b64encode(output.getvalue()).decode(
                                "ascii"
                            )
                        finally:
                            bitmap.close()
                            page.close()
                    selected.append(item)
            finally:
                if pdfium is not None:
                    pdfium.close()
            sys.stdout.write(
                json.dumps(
                    {
                        "pages": selected,
                        "total_pages": len(reader.pages),
                        "next_page": first + count if first + count <= len(reader.pages) else None,
                    }
                )
            )
    else:
        result = extract(body, sys.argv[2])
        sys.stdout.write(result.model_dump_json())
