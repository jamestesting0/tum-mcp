import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pypdfium2
from defusedxml import ElementTree
from pypdf import PdfReader

from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.models import Extracted, TextPage
from tum_mcp.moodle.parsing import main_text


def image_text(path: Path) -> str:
    executable = shutil.which("tesseract") or next(
        (
            str(path)
            for path in (Path("/opt/homebrew/bin/tesseract"), Path("/usr/local/bin/tesseract"))
            if path.is_file()
        ),
        None,
    )
    if executable is None:
        raise MoodleError(ErrorCode.NEEDS_OCR, "Install Tesseract to read scanned documents.")
    result = subprocess.run(
        [executable, str(path), "stdout", "-l", "eng"],
        check=True,
        capture_output=True,
        timeout=45,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


def extract_pdf(body: bytes) -> Extracted:
    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted:
        raise MoodleError(
            ErrorCode.RESOURCE_UNSUPPORTED, "Password-protected PDFs are unsupported."
        )
    if len(reader.pages) > 1500:
        raise MoodleError(ErrorCode.TOO_LARGE, "PDF exceeds the 1,500-page limit.")
    pages: list[TextPage] = []
    warnings: list[str] = []
    total = 0
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if len(text.strip()) < 10:
            with pypdfium2.PdfDocument(body) as document:
                bitmap = document[number - 1].render(scale=2)
                try:
                    with tempfile.TemporaryDirectory(prefix="tum-moodle-ocr-") as directory:
                        path = Path(directory) / "page.png"
                        bitmap.to_pil().save(path)
                        text = image_text(path)
                finally:
                    bitmap.close()
            warnings.append(
                f"Page {number} uses OCR; verify equations and diagrams in the original."
            )
        pages.append(TextPage(number=number, text=text[:200_000]))
        total += len(text)
        if total > 2_000_000:
            warnings.append("Text limit reached; only the first part of this document is indexed.")
            break
    return Extracted(pages=pages, warnings=warnings)


def extract_office(body: bytes) -> Extracted:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        entries = archive.infolist()
        if len(entries) > 3000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
            raise MoodleError(ErrorCode.TOO_LARGE, "Office archive exceeds extraction limits.")
        documents = [entry.filename for entry in entries if entry.filename == "word/document.xml"]
        slides = sorted(
            (
                entry.filename
                for entry in entries
                if entry.filename.startswith("ppt/slides/slide") and entry.filename.endswith(".xml")
            ),
            key=lambda name: int(Path(name).stem.removeprefix("slide")),
        )
        names = documents or slides
        if not names:
            raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "This Office format is unsupported.")
        pages: list[TextPage] = []
        for number, name in enumerate(names, 1):
            xml = archive.read(name)
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "XML entities are unsupported.")
            root = ElementTree.fromstring(xml)
            text = " ".join(
                node.text for node in root.iter() if node.tag.endswith("}t") and node.text
            )
            pages.append(
                TextPage(number=number, text=text[:200_000], unit="slide" if slides else "section")
            )
        return Extracted(pages=pages)


def extract(body: bytes, content_type: str) -> Extracted:
    if body.startswith(b"%PDF-"):
        return extract_pdf(body)
    if body.startswith(b"PK\x03\x04"):
        return extract_office(body)
    if content_type.startswith("image/"):
        with tempfile.TemporaryDirectory(prefix="tum-moodle-image-") as directory:
            path = Path(directory) / "image"
            path.write_bytes(body)
            return Extracted(
                pages=[TextPage(number=1, text=image_text(path))],
                warnings=["OCR text may contain recognition errors."],
            )
    if "html" in content_type:
        return Extracted(
            pages=[
                TextPage(number=1, text=main_text(body.decode("utf-8", "replace")), unit="section")
            ]
        )
    if content_type.startswith("text/"):
        return Extracted(
            pages=[TextPage(number=1, text=body.decode("utf-8", "replace"), unit="section")]
        )
    raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "No text extractor supports this resource.")
