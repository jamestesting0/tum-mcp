"""KaTeX math, derivation walkthroughs and visual backgrounds in the bundled example."""

import json
import os
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Browser, expect
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.course.app.preview import Handler, PreviewServer

pytestmark = pytest.mark.skipif(
    os.environ.get("TUM_MCP_BROWSER_INTEGRATION") != "1", reason="Explicit owned browser QA."
)

# The nearest ancestor that paints a background, which a drawing should blend into.
CARD = """element => {
  const paint = node => getComputedStyle(node).backgroundColor;
  let node = element.parentElement;
  while (node && paint(node) === 'rgba(0, 0, 0, 0)') node = node.parentElement;
  return [paint(element), paint(node || document.body)];
}"""


@pytest.fixture
def example_url(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "example"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    # The real preview server, so its Content-Security-Policy applies to KaTeX.
    with PreviewServer(("127.0.0.1", 0), partial(Handler, directory=str(root / "app"))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join(timeout=3)


@pytest.mark.parametrize("width,theme", [(390, "light"), (1280, "dark")])
def test_math_derivations_and_drawings_render_like_their_page(
    course_browser: Browser, example_url: str, width: int, theme: str
) -> None:
    context = course_browser.new_context(
        viewport={"width": width, "height": 900}, color_scheme=theme
    )
    errors: list[str] = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(message.text) if "Content Security" in message.text else None,
    )
    try:
        page.goto(example_url + "#study/components/content")
        # Inline and block math are typeset by KaTeX under the CSP, not left as source.
        expect(page.locator(".inline-math .katex").first).to_be_visible()
        assert page.locator(".tex-equation .katex").count() >= 1
        assert "\\(" not in page.locator("main").inner_text()
        # A derivation aligns each line on its relation and states its reason.
        derivation = page.locator(".derivation:not(.walkthrough)").first
        assert derivation.locator(".derivation-relation .katex").count() >= 3
        assert derivation.locator(".derivation-reason").count() >= 3
        # A walkthrough reveals one line at a time, keeps earlier ones and can show all.
        walk = page.locator(".derivation.walkthrough")
        lines = walk.locator(".derivation-line")
        expect(lines.nth(1)).to_be_hidden()
        walk.get_by_role("button", name="Next step").click()
        expect(lines.nth(1)).to_be_visible()
        expect(lines.nth(0)).to_be_visible()
        expect(walk.locator("[aria-live]")).to_contain_text("Step 2 of 4")
        walk.get_by_role("button", name="All steps").click()
        expect(lines.nth(3)).to_be_visible()
        # Diagrams and UML sit on the background of the card that holds them.
        for region in page.locator(".graph-region, .uml-region").all():
            own, card = region.evaluate(CARD)
            assert own == card, (own, card)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()


def test_formulas_break_only_between_their_parts(course_browser: Browser, example_url: str) -> None:
    page = course_browser.new_page(viewport={"width": 390, "height": 900})
    page.goto(example_url + "#study/components/content")
    expect(page.locator(".tex-equation .katex").first).to_be_visible()
    cases = json.loads((Path(__file__).parents[1] / "fixtures/latex_scan.json").read_text())
    result = page.evaluate(
        r"""async cases => {
          const { inlineExpression, texElement, formulaParts, splitRelation } =
            await import('./runtime/reading/mathml.mjs');
          const box = document.createElement('div');
          box.style.width = '140px'; box.style.fontSize = '24px';
          const long = String.raw`x_1+x_2+x_3+x_4=1,\qquad y_1+y_2=2`;
          box.append(texElement(long, { display: true }));
          document.querySelector('main').append(box);
          const pieces = [...box.querySelectorAll('.tex-part')];
          const feedback = document.createElement('p');
          feedback.className = 'feedback';
          const matrix = String.raw`\begin{pmatrix}1&1\\0&0\end{pmatrix}`;
          const inline = inlineExpression(`R^2=${matrix}${matrix}=${matrix}=R`);
          feedback.append('Multiplying gives ', inline, '.');
          box.append(feedback);
          await document.fonts.ready;
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return {
            scan: cases.map(c => ({
              parts: formulaParts(c.latex).map(part => part.latex),
              split: splitRelation(c.latex),
            })),
            rects: pieces.map(piece => piece.getClientRects().length),
            stacked: pieces[1].getBoundingClientRect().top
              > pieces[0].getBoundingClientRect().bottom - 1,
            inlineOverflow: feedback.scrollWidth - feedback.clientWidth,
            inlineRects: inline.querySelector('.tex-part').getClientRects().length,
            inlineBoxOverflow: inline.scrollWidth - inline.clientWidth,
            inlineOverflowX: getComputedStyle(inline).overflowX,
            inlineOverflowY: getComputedStyle(inline).overflowY,
          };
        }""",
        cases,
    )
    page.close()
    # The app cuts and aligns formulas where the build's scanner does (test_study_math).
    assert result["scan"] == [{"parts": c["parts"], "split": c["split"]} for c in cases]
    # Each part stays on one line; the line breaks at the gap between them.
    assert result["rects"] == [1, 1]
    assert result["stacked"]
    assert result["inlineOverflow"] <= 1
    assert result["inlineRects"] > 1
    assert result["inlineBoxOverflow"] <= 1
    assert result["inlineOverflowX"] == result["inlineOverflowY"] == "visible"


@pytest.mark.parametrize("width", [390, 1280])
def test_derivations_align_on_one_relation_inside_their_section(
    course_browser: Browser, example_url: str, width: int
) -> None:
    # Bra-kets before the relation, and lines too wide for reasons beside them.
    groups = [
        [
            r"\rho=\tfrac13(|0\rangle\langle0|+|1\rangle\langle1|+|-\rangle\langle-|)",
            r"|0\rangle\langle0|+|1\rangle\langle1|=|+\rangle\langle+|+|-\rangle\langle-|",
            r"=\begin{pmatrix}1/2&-1/6\\-1/6&1/2\end{pmatrix}",
        ],
        [
            r"D=2\begin{pmatrix}\cos^2(\theta/2)&\cos(\theta/2)\sin(\theta/2)\\"
            r"\cos(\theta/2)\sin(\theta/2)&\sin^2(\theta/2)\end{pmatrix}-I",
            r"G\begin{pmatrix}\cos\phi\\\sin\phi\end{pmatrix}="
            r"\begin{pmatrix}\cos(\phi+\theta)\\\sin(\phi+\theta)\end{pmatrix}",
        ],
        [
            r"YZ=iX,\qquad ZY=-iX",
            r"ZX=iY,\qquad XZ=-iY",
        ],
        [r"XY=iZ", r"YZ=iX,\qquad ZY=-iX"],
    ]
    page = course_browser.new_page(viewport={"width": width, "height": 900})
    page.goto(example_url + "#study/components/content")
    expect(page.locator(".tex-equation .katex").first).to_be_visible()
    lists = page.evaluate(
        """async groups => {
          const { renderDerivation } = await import('./runtime/reading/derivation.mjs');
          const reason = 'Because the bases agree.';
          const lines = latex => ({ lines: latex.map(l => ({ latex: l, reason })) });
          const box = renderDerivation({ groups: groups.map(lines) }, () => null);
          document.querySelector('main section, main').append(box);
          await document.fonts.ready;
          await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
          const centred = (math, outer) => {
            const cells = [...math.children].map(cell => cell.getBoundingClientRect())
              .filter(cell => cell.width > 0);
            const left = Math.min(...cells.map(cell => cell.left)) - outer.left;
            return Math.abs(left - (outer.right - Math.max(...cells.map(cell => cell.right))));
          };
          return [...box.querySelectorAll('.derivation-lines')].map(list => ({
            beside: list.classList.contains('beside'),
            offcentre: [...list.querySelectorAll('.derivation-math')]
              .map(math => centred(math, list.getBoundingClientRect())),
            overflow: list.scrollWidth - list.clientWidth,
            wholeOverflow: [...list.querySelectorAll('.derivation-whole')]
              .map(cell => cell.scrollWidth - cell.clientWidth),
            relations: [...list.querySelectorAll('.derivation-relation')]
              .map(cell => cell.textContent.trim() !== ''),
            lefts: [...new Set([...list.querySelectorAll('.derivation-relation')]
              .map(cell => Math.round(cell.getBoundingClientRect().left)))],
          }));
        }""",
        groups,
    )
    page.close()
    for found in lists:
        assert found["overflow"] <= 1
        assert all(overflow <= 1 for overflow in found["wholeOverflow"])
        assert all(found["relations"])
        # Beside a reason column the lines align on their relation; under their reasons each
        # line is a centred row.
        if found["beside"]:
            assert len(found["lefts"]) == (1 if found["relations"] else 0)
        else:
            assert max(found["offcentre"]) <= 2


def test_variables_open_their_meaning_by_click_and_keyboard(
    course_browser: Browser, example_url: str
) -> None:
    cases = json.loads((Path(__file__).parents[1] / "fixtures/symbol_marks.json").read_text())
    page = course_browser.new_page(viewport={"width": 390, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(example_url + "#study/components/content")
    expect(page.locator(".tex-equation .katex").first).to_be_visible()
    # The app marks exactly what the build's matcher marks (test_variable_meanings).
    marks = page.evaluate(
        """async cases => {
          const { symbolMarks } = await import('./runtime/reading/mathml.mjs');
          return cases.map(c => symbolMarks(c.latex, c.symbols)
            .map(([s, e, i]) => [c.latex.slice(s, e), i]));
        }""",
        cases,
    )
    assert marks == [case["marks"] for case in cases]
    # A block marks each variable where it first appears; a line still lists what it contains,
    # and K_j^\dagger never borrows the meaning of K_j.
    block = page.evaluate(
        r"""async () => {
          const { renderDerivation } = await import('./runtime/reading/derivation.mjs');
          const symbols = [{ symbol: '\\(K_j\\)', meaning: 'Kraus operator' },
            { symbol: '\\(\\rho\\)', meaning: 'Input state' }];
          const box = renderDerivation({ symbols, groups: [{ lines: [
            { latex: String.raw`\mathcal E(\rho)=\sum_j K_j\rho K_j^\dagger` },
            { latex: String.raw`\sum_j K_j^\dagger K_j=I` }] }] }, () => null);
          document.querySelector('main').append(box);
          const lines = [...box.querySelectorAll('.derivation-line')];
          return {
            marks: [...box.querySelectorAll('[data-v]')].map(mark => mark.dataset.v),
            listed: lines.map(line => line.querySelector('.visually-hidden')?.textContent || ''),
          };
        }"""
    )
    assert sorted(block["marks"]) == ["0", "1"]
    assert "Kraus operator" in block["listed"][1]
    # The preview's policy lets KaTeX size the arrow it draws for a vector.
    arrow = page.evaluate(
        """async () => {
          const { texElement } = await import('./runtime/reading/mathml.mjs');
          const math = texElement('\\\\vec r', { display: true });
          document.querySelector('main').append(math);
          return math.querySelector('svg').getBoundingClientRect().width;
        }"""
    )
    assert arrow > 0
    line = page.locator(".derivation-line.has-meanings").first
    line.scroll_into_view_if_needed()
    expect(page.locator("#" + line.get_attribute("aria-describedby"))).to_contain_text("Hadamard")
    line.locator("[data-v]").first.click()
    expect(page.locator(".symbol-bubble")).to_contain_text("the Hadamard gate")
    page.keyboard.press("Escape")
    line.focus()
    page.keyboard.press("Escape")
    expect(page.locator(".symbol-bubble")).to_have_count(0)
    page.keyboard.press("Enter")
    expect(page.locator(".symbol-bubble")).to_contain_text("the Hadamard gate")
    page.close()
    assert errors == []
