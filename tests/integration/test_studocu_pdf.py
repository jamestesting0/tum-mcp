import io

import pytest
from pypdf import PdfWriter
from pypdf.constants import PageLabelStyle
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tum_mcp.moodle.errors import MoodleError
from tum_mcp.moodle.extract_worker import read_pdf_pages, validate_pdf


def test_validation_keeps_original_and_does_not_need_ocr() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    original = buffer.getvalue()
    assert validate_pdf(original) == 2
    assert buffer.getvalue() == original


@pytest.mark.parametrize("body", [b"not a pdf", b"%PDF-1.7\ncorrupt"])
def test_invalid_pdf_is_rejected(body: bytes) -> None:
    with pytest.raises(MoodleError):
        validate_pdf(body)


def test_encrypted_pdf_is_rejected() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("synthetic-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(MoodleError):
        validate_pdf(buffer.getvalue())


def test_page_text_limit_is_explicit() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 0 10 Td (" + b"a" * 51000 + b") Tj ET")
    page.replace_contents(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    page_view = read_pdf_pages(buffer.getvalue(), 1, 1)["pages"][0]
    assert len(page_view["text"]) == 50000
    assert page_view["text_truncated"] is True
    assert page_view["text_available"] is True


def test_explicit_pdf_page_label_is_distinct_from_physical_page() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.set_page_label(0, 0, style=PageLabelStyle.DECIMAL, prefix="Exam-", start=1)
    buffer = io.BytesIO()
    writer.write(buffer)
    page = read_pdf_pages(buffer.getvalue(), 1, 1)["pages"][0]
    assert page["number"] == 1 and page["pdf_page_label"] == "Exam-1"
    assert page["text_available"] is False and page["text_truncated"] is False
