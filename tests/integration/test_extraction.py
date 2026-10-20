import io

from PIL import Image, ImageDraw, ImageFont

from tum_moodle.extract_worker import run_extraction


def test_worker_extracts_text_with_process_limits() -> None:
    result = run_extraction(b"Known course material.", "text/plain")
    assert result.pages[0].text == "Known course material."


def test_local_ocr_reads_a_scanned_page() -> None:
    image = Image.new("RGB", (1400, 400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    draw.text((50, 100), "REAL TIME SYSTEMS", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PDF")
    result = run_extraction(buffer.getvalue(), "application/pdf")
    assert "REAL TIME SYSTEMS" in result.pages[0].text
    assert "OCR" in result.warnings[0]
