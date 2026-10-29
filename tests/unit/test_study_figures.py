import re
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.study_figures import figure_bytes, figure_images, safe_svg

ARM = (
    '<svg viewBox="0 0 480 300"><defs><marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" '
    'markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" '
    'class="fill-ink"/></marker></defs><line x1="60" y1="240" x2="200" y2="120" '
    'class="thick"/><circle cx="200" cy="120" r="8" class="fill-surface"/>'
    '<path d="M100 240 A40 40 0 0 0 90 215" class="accent" marker-end="url(#tip)"/>'
    '<text x="110" y="230" class="accent">θ1</text></svg>'
)


def test_drawings_use_theme_classes_and_nothing_that_runs_or_loads() -> None:
    assert safe_svg(ARM) == ARM
    for unsafe in (
        '<svg viewBox="0 0 1 1"><script>alert(1)</script></svg>',
        '<svg viewBox="0 0 1 1" onload="alert(1)"/>',
        '<svg viewBox="0 0 1 1"><a href="https://example.com"><text>x</text></a></svg>',
        '<svg viewBox="0 0 1 1"><rect style="fill:red" width="1" height="1"/></svg>',
        '<svg viewBox="0 0 1 1"><rect fill="#ff0000" width="1" height="1"/></svg>',
        '<svg viewBox="0 0 1 1"><path d="M0 0" marker-end="url(https://x/y.svg#m)"/></svg>',
        '<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg viewBox="0 0 1 1"><text>&a;</text></svg>',
        '<svg viewBox="0 0 1 1"><foreignObject><div>x</div></foreignObject></svg>',
        '<svg viewBox="0 0 1 1"><rect class="red" width="1" height="1"/></svg>',
        "<svg><rect width='1' height='1'/></svg>",
        '<svg viewBox="0 0 1200 300"><rect width="1" height="1"/></svg>',
        '<svg viewBox="0 0 400 300"><text font-size="9">tiny</text></svg>',
    ):
        with pytest.raises(ValueError):
            safe_svg(unsafe)


def test_images_are_confined_typed_and_found_wherever_a_figure_sits(tmp_path: Path) -> None:
    png = tmp_path / "arm.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    assert figure_bytes(png).startswith(b"\x89PNG")
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"<svg/>")
    with pytest.raises(CampusError):
        figure_bytes(fake)
    with pytest.raises(CampusError):
        figure_bytes(tmp_path / "missing.png")
    payload = {
        "units": [{"blocks": [{"kind": "figure", "image": "figures/arm.png"}]}],
        "exercises": [{"statement": [{"kind": "figure", "svg": ARM}]}],
    }
    assert list(figure_images(payload)) == ["figures/arm.png"]


WEDGE = (
    '<svg viewBox="0 0 440 240"><line x1="130" y1="146" x2="290" y2="94" class="dashed"/>'
    '<line x1="130" y1="148" x2="295" y2="110"/>'
    '<text x="170" y="112" class="small">intended path</text></svg>'
)
ON_ARC = (
    '<svg viewBox="0 0 440 300"><path d="M30 250 A120 120 0 0 1 270 250"/>'
    '<text x="160" y="126">(0, 2)</text></svg>'
)


@pytest.mark.parametrize(
    ("markup", "message"),
    [
        (WEDGE, 'Label "intended path" touches a <line>'),
        (ON_ARC, 'Label "(0, 2)" touches a <path>'),
        ('<svg viewBox="0 0 300 100"><text x="250" y="50">far too long</text></svg>', "outside"),
        (
            '<svg viewBox="0 0 300 100"><text x="20" y="50">one</text>'
            '<text x="30" y="52">two</text></svg>',
            "overlap",
        ),
    ],
)
def test_labels_must_stay_clear_of_strokes_labels_and_edges(markup: str, message: str) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        safe_svg(markup)


def test_clear_labels_beside_lines_arcs_and_inside_boxes_pass() -> None:
    safe_svg(
        '<svg viewBox="0 0 440 300"><path d="M30 250 A120 120 0 0 1 270 250"/>'
        '<text x="160" y="110">(0, 2)</text><rect x="300" y="160" width="120" height="60"/>'
        '<text x="360" y="196" text-anchor="middle">room</text></svg>'
    )
    safe_svg(
        '<svg viewBox="0 0 440 240"><line x1="80" y1="167" x2="259" y2="75" class="dashed"/>'
        '<line x1="81" y1="170" x2="276" y2="150"/><text x="290" y="76">intended path</text>'
        '<text x="290" y="156">actual path</text></svg>'
    )
