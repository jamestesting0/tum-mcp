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

// Variable meanings. A formula marks a listed variable wherever it is spelled as listed; the
// build checks the same rules (study_math.symbol_marks) and tests/fixtures/symbol_marks.json
// pins both. Text arguments, environment names and delimiters after \left are never marked; a
// subscripted match keeps a following superscript (and the reverse), so K_j^\dagger stacks.
const TEXTUAL = new Set(['text', 'textrm', 'textbf', 'textit', 'textsf', 'texttt', 'mathrm', 'operatorname', 'mbox', 'begin', 'end']);
const DELIMITER_PREFIX = /\\(?:left|right|middle|[bB]igg?[lrm]?)$/;
const space = char => /\s/.test(char || '');
// A variable as written in a meaning list, \(\rho\) or \rho, as plain LaTeX.
export function symbolLatex(symbol) {
  const text = symbol.trim(), inner = /^\\\(([\s\S]*)\\\)$/.exec(text);
  return (inner ? inner[1] : text).trim();
}
// A decoration makes a different variable: K_j^\dagger is not K_j, \bar a is not a. Such a
// form is never marked with the plain variable's meaning (study_math mirrors this).
const DECORATIONS = new Set(['\\dagger', '*', '\\ast', 'T', '\\top', '\\intercal', '\\prime', '\\star']);
const ACCENTS = 'bar|hat|tilde|vec|dot|ddot|check|breve|acute|grave|mathring|overline|widehat|widetilde';
const ACCENT = new RegExp(`^\\\\(?:${ACCENTS})(?![A-Za-z])\\s*`);
export function normalizeSymbol(symbol) {
  return symbolLatex(symbol).replace(new RegExp(`(\\\\(?:${ACCENTS}))\\s*\\{([A-Za-z0-9])\\}`, 'g'), '$1 $2')
    .replace(/(\\[A-Za-z]+)\s+(?=[A-Za-z])/g, '$1\u0000').replace(/\s+/g, '')
    .replace(/\u0000/g, ' ').replace(/([_^])\{([A-Za-z0-9]|\\[A-Za-z]+)\}/g, '$1$2');
}
function groupEnd(latex, opening) {
  let depth = 0, index = opening;
  while (index < latex.length) {
    const char = latex[index];
    if (char === '\\') { index += 2; continue; }
    depth += (char === '{') - (char === '}'); index++;
    if (depth === 0) return index;
  }
  return latex.length;
}
const skipSpace = (latex, position) => { while (space(latex[position])) position++; return position; };
function matchAt(latex, start, symbol) {
  let position = start, k = 0;
  while (k < symbol.length) {
    const want = symbol[k];
    if (want === ' ') {
      // \bar a also matches \bar{a}.
      if (latex[position] === '{' && latex[position + 2] === '}') {
        if (latex[position + 1] !== symbol[k + 1]) return -1;
        position += 3; k += 2; continue;
      }
      if (!space(latex[position])) return -1;
      position = skipSpace(latex, position); k++; continue;
    }
    if (position > start) position = skipSpace(latex, position);
    if ((want === '_' || want === '^') && latex[position] === want) {
      position = skipSpace(latex, position + 1); k++;
      if (latex[position] === '{') {
        // A braced script matches the listed one written without braces.
        const end = groupEnd(latex, position), inner = latex.slice(position + 1, end - 1).trim();
        if (inner && symbol.startsWith(inner, k) && symbol[k] !== '{') { position = end; k += inner.length; }
      }
      continue;
    }
    if (latex[position] !== want) return -1;
    position++; k++;
  }
  if (/\\[A-Za-z]+$/.test(symbol) && /[A-Za-z]/.test(latex[position] || '')) return -1;
  return position;
}
function scriptEnd(latex, at) {
  const position = skipSpace(latex, at + 1);
  if (latex[position] === '{') return groupEnd(latex, position);
  const command = /^\\[A-Za-z]+|^\\./.exec(latex.slice(position));
  return position + (command ? command[0].length : 1);
}
// The end of a dagger, star, transpose or prime decorating the variable before `at`.
function decorationEnd(latex, at) {
  if (latex[at] === "'") { let end = at; while (latex[end] === "'") end++; return end; }
  if (latex[at] !== '^') return -1;
  const end = scriptEnd(latex, at);
  let script = latex.slice(at + 1, end).trim();
  if (script.startsWith('{') && script.endsWith('}')) script = script.slice(1, -1).trim();
  return DECORATIONS.has(script) || /^'+$/.test(script) ? end : -1;
}
export function symbolMarks(latex, symbols) {
  const order = symbols.map((text, index) => [index, normalizeSymbol(text)]).sort((a, b) => b[1].length - a[1].length);
  const marks = []; let position = 0, previous = '';
  while (position < latex.length) {
    const textual = /^\\([A-Za-z]+)\s*\{/.exec(latex.slice(position));
    if (textual && TEXTUAL.has(textual[1])) {
      const end = groupEnd(latex, position + textual[0].length - 1);
      previous = latex.slice(position, end); position = end; continue;
    }
    let hit = null;
    if (!space(latex[position]) && !DELIMITER_PREFIX.test(previous)) {
      for (const [index, symbol] of order) {
        const end = symbol ? matchAt(latex, position, symbol) : -1;
        if (end >= 0) { hit = [index, symbol, end]; break; }
      }
    }
    if (hit) {
      let [index, symbol, end] = hit;
      const after = skipSpace(latex, end), decorated = decorationEnd(latex, after);
      if (decorated >= 0) { previous = latex.slice(position, decorated); position = decorated; continue; }
      const tail = /([_^])[^_^]*$/.exec(symbol);
      if (tail && (latex[after] === '_' || latex[after] === '^') && latex[after] !== tail[1]) end = scriptEnd(latex, after);
      marks.push([position, end, index]);
      previous = latex.slice(position, end); position = end; continue;
    }
    const accent = ACCENT.exec(latex.slice(position));
    if (accent) {
      const start = position + accent[0].length;
      let end = latex[start] === '{' ? groupEnd(latex, start) : start;
      if (end === start) end = start + ((/^\\[A-Za-z]+|^\\./.exec(latex.slice(start)) || [latex[start] || ''])[0].length);
      previous = latex.slice(position, end); position = end; continue;
    }
    const step = (/^\\[A-Za-z]+|^\\./s.exec(latex.slice(position)) || [latex[position]])[0];
    if (!space(step)) previous = step;
    position += step.length;
  }
  return marks;
}
// The formula with each mark wrapped for KaTeX's \htmlData, which only the app writes.
// A variable is marked once per block, where it first appears; `seen` carries the block's marks.
function markLatex(latex, symbols, seen) {
  let out = '', at = 0;
  for (const [start, end, index] of symbolMarks(latex, symbols)) {
    if (seen.has(index)) continue;
    seen.add(index);
    out += `${latex.slice(at, start)}{\\htmlData{v=${index}}{${latex.slice(start, end)}}}`; at = end;
  }
  return out + latex.slice(at);
}

// One reading of a formula's top level for everything that cuts it: line breaks and the
// relation a derivation line aligns on (study_math.top_tokens mirrors it). Depth counts
// braces, brackets, \left...\right pairs, environments, kets |a, b\rangle, bras \langle a, b|
// and inner products \langle u, v\rangle. Each token comes with the depth it sits at.
const OPENS = new Set(['{', 'lbrace', 'lfloor', 'lceil', 'left', 'begin']);
const CLOSES = new Set(['}', 'rbrace', 'rfloor', 'rceil', 'right', 'end']);
const DELIMITED = /^\\(?:left|right|middle|[bB]igg?[lrm]?)$/;
export function* topTokens(latex) {
  const stack = []; let previous = '';
  // Whether a \rangle closes what opens at index before any bar does.
  const ket = index => { const rest = latex.slice(index + 1), close = rest.indexOf('\\rangle'), bar = rest.search(/\||\\vert|\\mid/); return close >= 0 && (bar < 0 || close < bar); };
  for (const { 0: token, index } of latex.matchAll(/\\(?:[A-Za-z]+|.)|./gs)) {
    yield { index, token, depth: stack.length };
    if (/^\s$/.test(token)) continue;
    const delimiter = DELIMITED.test(previous); previous = token;
    if (delimiter) continue; // the delimiter after \left or \right belongs to that pair
    const name = token.length > 1 ? token.slice(1) : null;
    if (name !== null) {
      if (OPENS.has(name)) stack.push('group');
      else if (CLOSES.has(name)) stack.pop();
      else if (name === 'langle') stack.push(ket(index) ? 'angle' : 'bra');
      else if (name === 'rangle' && ['angle', 'ket'].includes(stack.at(-1))) stack.pop();
    } else if (token === '|') {
      if (stack.at(-1) === 'bra') stack.pop();
      if (ket(index)) stack.push('ket');
    } else if ('{(['.includes(token)) stack.push('group');
    else if ('})]'.includes(token)) stack.pop();
  }
}

// A formula breaks only between its parts: at a comma, \quad or \qquad on the top level, or
// before a connective such as \iff that joins two whole statements. Each part keeps the space
// that followed it.
const CONNECTIVES = new Set(['\\iff', '\\implies', '\\impliedby', '\\Rightarrow', '\\Leftrightarrow', '\\Longrightarrow', '\\Longleftrightarrow']);
const SPACING = /^(?:\s|~|\\[,:;! ]|\\q?quad(?![A-Za-z]))+/;
export function formulaParts(latex) {
  const parts = []; let start = 0;
  const cut = (end, quad) => {
    const space = latex.slice(end).match(SPACING)?.[0] || '', text = latex.slice(start, end).trim();
    if (text) parts.push({ latex: text, gap: /qquad/.test(space) ? 'qquad' : /quad/.test(space) || quad ? 'quad' : 'space' });
    start = end + space.length;
  };
  for (const { index, token, depth } of topTokens(latex)) {
    if (depth || index < start) continue;
    if (/^\\q?quad$/.test(token)) cut(index, true);
    else if (token === ',') cut(index + 1, false);
    else if (index > start && CONNECTIVES.has(token)) cut(index, false);
  }
  const last = latex.slice(start).trim();
  if (last) parts.push({ latex: last, gap: null });
  else if (parts.length) parts.at(-1).gap = null;
  return parts;
}

// Relations a derivation line aligns on.
const RELATIONS = new Set(['\\Longleftrightarrow', '\\Longrightarrow', '\\longrightarrow', '\\longmapsto', '\\Leftrightarrow', '\\Rightarrow', '\\rightarrow', '\\mapsto', '\\implies', '\\coloneqq', '\\cong', '\\simeq', '\\approx', '\\propto', '\\equiv', '\\leq', '\\geq', '\\neq', '\\iff', '\\sim', '\\subseteq', '\\supseteq', '\\subset', '\\supset', '\\leftarrow', '\\Leftarrow', '\\gets', '\\models', '\\vdash', '\\vDash', '\\ne', '\\le', '\\ge', '\\to', '=', '<', '>']);
// A line's LaTeX split at its first top-level relation, so every line of a derivation aligns
// on it; a line that opens with a relation continues the line above.
export function splitRelation(latex) {
  for (const { index, token, depth } of topTokens(latex)) {
    if (!depth && RELATIONS.has(token)) return [latex.slice(0, index), token, latex.slice(index + token.length)];
  }
  return ['', '', latex];
}

function typeset(katex, latex, display, symbols, seen) {
  const span = document.createElement('span');
  span.className = 'tex-part';
  const options = { displayMode: false, output: 'htmlAndMathml', throwOnError: true, strict: 'ignore', maxExpand: 1000 };
  const render = (source, trust) => katex.render(display ? `\\displaystyle ${source}` : source, span, { ...options, trust });
  // Marked variables need KaTeX's \htmlData, and only that command is trusted; a formula
  // KaTeX rejects once marked is shown unmarked.
  const marked = symbols?.length ? markLatex(latex, symbols, seen) : latex;
  if (marked === latex) render(latex, false);
  else try { render(marked, ({ command }) => command === '\\htmlData'); } catch { render(latex, false); }
  for (const annotation of span.querySelectorAll('annotation')) annotation.remove();
  return span;
}

function fit(elements) {
  const rows = elements.filter(element => element.isConnected).map(element => {
    const inline = element.localName === 'study-inline-math';
    const expression = inline ? element.firstElementChild : element;
    expression.style.fontSize = '';
    return { element, expression, inline };
  });
  const sizes = rows.map(({ element, expression, inline }) => {
    const style = getComputedStyle(element), size = parseFloat(getComputedStyle(expression).fontSize);
    const width = element.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const parts = expression.querySelectorAll(inline ? '.katex-html > .base' : '.tex-part');
    const widest = parts.length
      ? Math.max(...[...parts].map(part => part.getBoundingClientRect().width))
      : (inline ? expression : expression.querySelector('math'))?.getBoundingClientRect().width;
    return width > 0 && widest > width ? `${size * Math.max(0.5, width - 0.5) / widest}px` : '';
  });
  rows.forEach(({ expression }, index) => { expression.style.fontSize = sizes[index]; });
}
const fitter = new ResizeObserver(entries => fit(entries.map(entry => entry.target)));
export function fitMath(element) {
  fitter.observe(element);
  document.fonts?.ready.then(() => fit([element]));
}
customElements.define('study-inline-math', class extends HTMLElement {
  connectedCallback() { fitMath(this); }
  disconnectedCallback() { fitter.unobserve(this); }
});

export function inlineExpression(latex, mathml = null) {
  const math = texElement(latex, { mathml });
  if (!math) return null;
  const span = document.createElement('study-inline-math');
  span.className = 'inline-math';
  span.append(math);
  return span;
}

// Mathematics is typeset by KaTeX (vendored, MIT), as in Notion: TeX fonts, spacing, radicals
// and text-size inline matrices. Only LaTeX the build already validated reaches it, with
// trust off. `display` sets display style in KaTeX's inline layout. Display equations break
// between the parts from formulaParts. KaTeX keeps a MathML copy for screen readers; its LaTeX annotation is
// dropped so the page text stays the mathematics. When KaTeX is missing or rejects the
// input, the build's MathML is shown.
export function texElement(latex, { display = false, mathml = null, symbols = null, seen = new Set() } = {}) {
  const katex = globalThis.katex;
  if (katex && latex) {
    const span = document.createElement('span');
    span.className = display ? 'tex tex-display' : 'tex';
    try {
      // Display math breaks between its parts; an inline formula is one piece and never breaks.
      const parts = display ? formulaParts(latex) : [{ latex, gap: null }];
      for (const part of parts) {
        span.append(typeset(katex, part.latex, display, symbols, seen));
        // A real space is the break opportunity; it vanishes at a line end, so a wrapped part
        // starts flush. Its width keeps the authored \quad or \qquad.
        if (part.gap) { const gap = document.createElement('span'); gap.className = `tex-gap ${part.gap}`; gap.textContent = ' '; span.append(gap); }
      }
      return span;
    } catch {
      try { const span = document.createElement('span'); span.className = display ? 'tex tex-display' : 'tex'; span.append(typeset(katex, latex, display)); return span; }
      catch { /* fall back to the build's MathML below */ }
    }
  }
  const math = mathml && parseMath(mathml);
  if (math) math.setAttribute('display', display ? 'block' : 'inline');
  return math;
}

// An SVG label written wholly as inline LaTeX, \(x_3\), is typeset by KaTeX where the text
// stood, at its size, anchor and colour, so a drawing's mathematics reads like the text around
// it. It needs the drawing on screen to measure.
const MATH_LABEL = /^\s*\\\(([\s\S]+)\\\)\s*$/;
export function typesetLabels(svg) {
  const scale = svg.getScreenCTM()?.a || 1;
  for (const text of svg.querySelectorAll('text')) {
    const latex = MATH_LABEL.exec(text.textContent)?.[1], math = latex && texElement(latex);
    if (!math) continue;
    const at = text.hasAttribute('x') ? text : text.querySelector('tspan') || text;
    const style = getComputedStyle(at), size = parseFloat(style.fontSize) || 16;
    const x = Number(at.getAttribute('x')) || 0, y = Number(at.getAttribute('y')) || 0;
    const box = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
    const holder = document.createElement('span'), baseline = document.createElement('span');
    holder.className = 'figure-math'; baseline.className = 'figure-baseline';
    holder.style.fontSize = `${size}px`; holder.style.color = getComputedStyle(text).fill;
    holder.append(math, baseline); box.append(holder);
    box.setAttribute('width', String(size * 40)); box.setAttribute('height', String(size * 4));
    text.replaceWith(box);
    const outer = holder.getBoundingClientRect(), width = outer.width / scale, height = outer.height / scale;
    const base = (baseline.getBoundingClientRect().top - outer.top) / scale;
    const anchor = getComputedStyle(text).textAnchor || style.textAnchor;
    const middle = ['middle', 'central'].includes(style.dominantBaseline);
    box.setAttribute('x', String(anchor === 'middle' ? x - width / 2 : anchor === 'end' ? x - width : x));
    box.setAttribute('y', String(middle ? y - height / 2 : y - base));
    box.setAttribute('width', String(width + 1)); box.setAttribute('height', String(height));
  }
}
