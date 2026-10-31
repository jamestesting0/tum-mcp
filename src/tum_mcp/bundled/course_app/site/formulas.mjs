import { node, studyText, plainText } from './dom.mjs';
import { parseMath, texElement } from './mathml.mjs';

const namespace = 'http://www.w3.org/1998/Math/MathML';
const relations = new Set(['=', '≈', '≠', '≤', '≥', '<', '>', '⇒', '⇔', '←']);

function chunks(math) {
  const sequence = math.children.length === 1 && math.firstElementChild.localName === 'mrow'
    ? math.firstElementChild : math;
  const result = []; let current = [], depth = 0;
  for (const token of sequence.children) {
    const text = token.textContent;
    const relation = token.localName === 'mo' && relations.has(text);
    const gap = token.localName === 'mspace' && parseFloat(token.getAttribute('width')) >= 1;
    if (!depth && (relation || gap) && current.length) { result.push(current); current = []; }
    if (!current.length && gap) continue;
    current.push(token);
    const fences = token.localName === 'mo' ? [token] : token.querySelectorAll('mo');
    for (const fence of fences) {
      if (['(', '[', '{'].includes(fence.textContent)) depth++;
      if ([')', ']', '}'].includes(fence.textContent)) depth = Math.max(0, depth - 1);
    }
  }
  if (current.length) result.push(current);
  return result;
}

function line(source, tokens, size) {
  const row = node('div', 'equation-line');
  const math = source.cloneNode(false), group = document.createElementNS(namespace, 'mrow');
  for (const token of tokens) group.append(token.cloneNode(true));
  math.append(group); math.style.fontSize = `${size}px`; row.append(math);
  return row;
}

class StudyEquation extends HTMLElement {
  #source;
  #width = 0;
  #frame = 0;
  #nearby = false;
  #visibility = new IntersectionObserver(entries => {
    this.#nearby = entries[0].isIntersecting;
    if (this.#nearby) this.#schedule();
  }, { rootMargin: '128px' });
  #observer = new ResizeObserver(entries => {
    const width = entries[0].contentRect.width;
    if (Math.abs(width - this.#width) < .5) return;
    this.#width = width; this.#schedule();
  });
  #fonts = () => this.#schedule();

  connectedCallback() {
    this.#source ??= this.querySelector('math')?.cloneNode(true);
    if (!this.#source) return;
    this.#width = 0; this.#observer.observe(this);
    this.#visibility.observe(this);
    document.fonts.addEventListener('loadingdone', this.#fonts);
    this.#schedule();
  }
  disconnectedCallback() {
    this.#observer.disconnect(); this.#visibility.disconnect(); cancelAnimationFrame(this.#frame);
    document.fonts.removeEventListener('loadingdone', this.#fonts);
  }
  #schedule() {
    cancelAnimationFrame(this.#frame);
    if (!this.#nearby) return;
    this.#frame = requestAnimationFrame(() => { if (this.isConnected) this.#fit(); });
  }
  #fit() {
    const style = getComputedStyle(this);
    const width = this.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    if (width <= 0) return;
    const minimum = parseFloat(style.getPropertyValue('--math-min'));
    const maximum = parseFloat(style.getPropertyValue('--math-max'));
    const source = this.#source;
    const original = source.cloneNode(true); original.style.fontSize = `${maximum}px`;
    const whole = node('div', 'equation-line'); whole.append(original); this.replaceChildren(whole);
    if (original.getBoundingClientRect().width <= width + 1) return;
    const parts = chunks(source), rows = []; let current = [];
    for (const part of parts) {
      const candidate = [...current, ...part], measure = line(source, candidate, minimum);
      this.replaceChildren(measure);
      if (current.length && measure.firstElementChild.getBoundingClientRect().width > width + 1) {
        rows.push(current); current = part;
      } else current = candidate;
    }
    if (current.length) rows.push(current);
    this.replaceChildren(...rows.map(tokens => line(source, tokens, maximum)));
    for (const row of this.children) {
      const math = row.firstElementChild, natural = math.getBoundingClientRect().width;
      math.style.fontSize = `${Math.max(minimum, Math.min(maximum, maximum * (width - 1) / natural))}px`;
    }
    // Auto margins become zero for an oversized line, keeping its beginning reachable.
    this.scrollLeft = 0;
  }
}
customElements.define('study-equation', StudyEquation);

export function renderFormula(block) {
  const box = node('div', 'surface');
  // KaTeX typesets authored LaTeX and wraps a long formula after its relations on a phone;
  // legacy MathML-only formulas keep the fitted native equation.
  const typeset = block.latex && globalThis.katex && texElement(block.latex, { display: true });
  const expression = typeset ? node('div', 'equation tex-equation') : node('study-equation', 'equation');
  expression.tabIndex = 0; expression.setAttribute('role', 'region');
  expression.setAttribute('aria-label', `Equation: ${plainText(block.plain)}`);
  const math = typeset || parseMath(block.mathml);
  if (math) expression.append(math);
  else expression.append(node('p', '', block.plain));
  box.append(expression, studyText('p', '', block.plain));
  const glossary = node('dl', 'symbols');
  for (const symbol of block.symbols) glossary.append(studyText('dt', '', symbol.symbol), studyText('dd', '', symbol.meaning));
  box.append(glossary, studyText('p', 'small', block.conditions));
  return box;
}
