import json
from pathlib import Path

import pytest
from material_fixture import material_project

from tum_mcp.course.checks.report import whole_slide
from tum_mcp.course.sources.page_figures import crop_figure, page_regions
from tum_mcp.errors import CampusError

# A 4:3 slide: a title bar, two boxed boards with a label beside them, and a footer bar.
SLIDE = """0 0 1 rg 0 270 400 30 re f
0 0 0 RG 2 w 60 80 90 90 re S 210 80 90 90 re S
60 125 m 150 125 l S 210 125 m 300 125 l S
BT /F1 10 Tf 305 120 Td (goal) Tj ET
0 0 1 rg 0 0 400 12 re f"""


def slide_pdf() -> bytes:
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        f"<< /Length {len(SLIDE)} >>\nstream\n{SLIDE}\nendstream",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 3 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body, offsets = b"%PDF-1.4\n", []
    for number, value in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{value}\nendobj\n".encode()
    start = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return body


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return material_project(tmp_path, {"slides": ("content", slide_pdf())})


def test_a_page_lists_its_figures_without_the_title_bar_and_footer(project: Path) -> None:
    listed = page_regions(project, "slides", 1)
    boxes = [region["box"] for region in listed["regions"]]
    assert (project / listed["preview"]).is_file()
    assert len(boxes) == 2, "each board on its own, neither slide band"
    for x0, y0, x1, y1 in boxes:
        assert 0.1 < y0 < y1 < 0.75 and x1 - x0 < 0.9
    assert any(x1 > 0.8 for _, _, x1, _ in boxes), "the label touching a board belongs to it"


def test_merged_regions_crop_into_the_app_with_their_page(project: Path) -> None:
    result = crop_figure(project, "slides", 1, "boards", regions=[1, 2])
    image = project / "app" / result["image"]
    width, height = (int.from_bytes(image.read_bytes()[at : at + 4]) for at in (16, 20))
    assert result["pages"] == "1" and result["sources"] == ["slides"]
    assert width > 2 * height, "two boards side by side, trimmed to the drawing"
    record = json.loads((project / ".tum-mcp/figures.json").read_text())["figures/boards.png"]
    assert record["page"] == 1 and record["source"] == "slides"
    assert not whole_slide(project, "figures/boards.png", record)

    crop_figure(project, "slides", 1, "slide", box=[0, 0, 1, 1])
    record = json.loads((project / ".tum-mcp/figures.json").read_text())["figures/slide.png"]
    assert whole_slide(project, "figures/slide.png", record)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"regions": [3]}, "regions 1-2"),
        ({"regions": [1], "box": [0, 0, 1, 1]}, "--region or --box"),
        ({"regions": [1], "name": "Boards!"}, "lowercase"),
    ],
)
def test_a_crop_names_one_listed_region_or_box(project: Path, change: dict, message: str) -> None:
    arguments = {"name": "boards", "regions": None, "box": None} | change
    with pytest.raises(CampusError, match=message):
        crop_figure(project, "slides", 1, **arguments)
