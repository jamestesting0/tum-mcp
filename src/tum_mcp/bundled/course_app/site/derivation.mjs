import { node, studyText, append, plainText } from './dom.mjs';
import { fitMath, formulaParts, splitRelation, texElement } from './mathml.mjs';
import { withMeanings } from './symbols.mjs';
import { iconButton } from './navigation.mjs';

const fitted = cell => { fitMath(cell, 0.8); return cell; };

// Reasons go beside the working when the list is at least 30em wide and every line, hidden
// walkthrough steps included, fits beside them at full size; then the lines align on their
// relation. Otherwise each line and its reason are centred rows. Decided per width, so the
// working never runs past its section.
function place(list, force) {
  const width = list.clientWidth;
  if (!width || (!force && list.dataset.width === String(width))) return;
  list.dataset.width = String(width);
  const hidden = [...list.children].filter(item => item.hidden);
  hidden.forEach(item => { item.hidden = false; });
  list.querySelectorAll('.derivation-left, .derivation-right').forEach(cell => { cell.style.fontSize = ''; });
  list.classList.add('beside');
  const fits = width >= 30 * parseFloat(getComputedStyle(list).fontSize) && list.scrollWidth <= width + 1;
  list.classList.toggle('beside', fits);
  hidden.forEach(item => { item.hidden = true; });
}
const placer = new ResizeObserver(entries => {
  for (const { target } of entries) { place(target); document.fonts?.ready.then(() => place(target, true)); }
});

function line(entry, symbols, seen) {
  const item = node('li', 'derivation-line'), expression = node('div', 'derivation-math');
  // A line listing several statements ("N=4,\quad M=1,\quad ...") is no single equation to
  // align: it runs flush left across the math columns and wraps between its statements.
  const listed = formulaParts(entry.latex).length > 1, [left, relation, right] = splitRelation(entry.latex);
  const typeset = !listed && globalThis.katex && [left, relation, right].map(part => part.trim() ? texElement(part, { display: true, symbols: symbols?.map(item => item.symbol), seen }) : null);
  if (typeset && typeset.every((part, index) => part || ![left, relation, right][index].trim())) {
    const [l, r, rest] = typeset;
    expression.append(append(node('span', 'derivation-left'), ...(l ? [l] : [])),
      append(node('span', 'derivation-relation'), ...(r ? [r] : [])),
      // A long right side breaks only between its parts, then shrinks a little, then scrolls.
      fitted(append(node('span', 'derivation-right'), ...(rest ? [rest] : []))));
  } else {
    // A listed line, or any line without KaTeX (the build's MathML), shows whole and unaligned.
    const whole = texElement(entry.latex, { display: true, mathml: entry.mathml, symbols: symbols?.map(item => item.symbol), seen });
    expression.append(fitted(append(node('span', 'derivation-right derivation-whole'), whole || node('span', '', entry.latex))));
  }
  item.append(expression);
  if (entry.reason) item.append(studyText('p', 'derivation-reason', entry.reason));
  return symbols?.length ? withMeanings(item, symbols, entry.latex) : item;
}

// Working shown one transformation per line, each with the reason it follows. As a
// walkthrough, lines appear one at a time with earlier ones kept for comparison, and the
// state each line reaches is drawn beside it; "Show all steps" reads the whole working.
export function renderDerivation(block, renderVisual) {
  const box = node('div', `derivation${block.walkthrough ? ' walkthrough' : ''}`);
  const items = [], seen = new Set();
  for (const group of block.groups) {
    const list = node('ol', 'derivation-lines');
    for (const entry of group.lines) { const item = line(entry, block.symbols, seen); items.push([item, entry]); list.append(item); }
    box.append(...(group.label ? [studyText('p', 'derivation-label', group.label)] : []), list);
    placer.observe(list);
  }
  if (!block.walkthrough) return box;
  const stage = node('div', 'derivation-visual'), status = node('p', 'visually-hidden');
  status.setAttribute('aria-live', 'polite');
  let index = 0, all = false;
  const prev = iconButton('Previous step', 'left', () => { index--; update(); });
  const next = iconButton('Next step', 'right', () => { index++; update(); });
  const counter = node('span', 'small');
  const whole = node('button', 'quiet derivation-all', 'All steps');
  whole.type = 'button'; whole.setAttribute('aria-pressed', 'false');
  whole.addEventListener('click', () => { all = !all; update(); });
  const controls = append(node('div', 'diagram-controls derivation-controls'), prev, counter, next, whole);
  let shown = null;
  function update() {
    items.forEach(([item], position) => {
      item.hidden = !all && position > index;
      item.classList.toggle('current', !all && position === index);
    });
    // The picture of the latest line that has one, so the drawing follows the algebra.
    const visual = [...items.slice(0, all ? items.length : index + 1)].reverse().find(([, entry]) => entry.visual)?.[1].visual;
    if (visual !== shown) { stage.replaceChildren(...(visual ? [renderVisual(visual)] : [])); shown = visual; }
    stage.hidden = !visual;
    counter.textContent = all ? `${items.length} steps` : `Step ${index + 1} of ${items.length}`;
    prev.disabled = all || index === 0; next.disabled = all || index === items.length - 1;
    whole.textContent = all ? 'Step through' : 'All steps';
    whole.setAttribute('aria-pressed', String(all));
    const [, entry] = items[index];
    status.textContent = all ? '' : `Step ${index + 1} of ${items.length}. ${plainText(entry.reason || '')}`;
  }
  box.append(stage, controls, status);
  update();
  return box;
}
