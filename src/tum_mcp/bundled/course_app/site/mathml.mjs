// Only the local compiler's inert MathML is accepted; prose never becomes HTML.
const namespace = 'http://www.w3.org/1998/Math/MathML';
const allowed = new Set('math mrow mi mn mo mtext mfrac msqrt mroot msub msup msubsup mtable mtr mtd munder mover munderover mmultiscripts mprescripts none mspace mstyle menclose'.split(' '));
const attributes = new Set('display form mathvariant displaystyle stretchy linethickness fence separator accent accentunder notation columnalign rowalign columnspacing rowspacing columnlines rowlines scriptlevel width height depth lspace rspace minsize maxsize'.split(' '));
export function parseMath(value) {
  const parsed = new DOMParser().parseFromString(value, 'application/xml');
  if (parsed.documentElement.localName !== 'math' || parsed.querySelector('parsererror') || ![...parsed.querySelectorAll('*')].every(element =>
    element.namespaceURI === namespace && allowed.has(element.localName) &&
    [...element.attributes].every(attribute => attributes.has(attribute.name) || attribute.name === 'xmlns'))) return null;
  return document.importNode(parsed.documentElement, true);
}

// Mathematics is typeset by KaTeX (vendored, MIT), as in Notion: TeX fonts, spacing, radicals
// and text-size inline matrices. Only LaTeX the build already validated reaches it, with
// trust off. `display` sets display style but keeps KaTeX's inline layout, which breaks long
// expressions after their relations and operators on narrow screens. KaTeX keeps a MathML
// copy for screen readers; its LaTeX annotation is dropped so the page text stays the
// mathematics. When KaTeX is missing or rejects the input, the build's MathML is shown.
export function texElement(latex, { display = false, mathml = null } = {}) {
  const katex = globalThis.katex;
  if (katex && latex) {
    const span = document.createElement('span');
    span.className = display ? 'tex tex-display' : 'tex';
    try {
      katex.render(display ? `\\displaystyle ${latex}` : latex, span, {
        displayMode: false, output: 'htmlAndMathml', throwOnError: true, trust: false, strict: 'ignore', maxExpand: 1000,
      });
      for (const annotation of span.querySelectorAll('annotation')) annotation.remove();
      return span;
    } catch { /* fall back to the build's MathML below */ }
  }
  const math = mathml && parseMath(mathml);
  if (math) math.setAttribute('display', display ? 'block' : 'inline');
  return math;
}
