import { node, studyText, append, plainText } from './dom.mjs';
import { texElement } from './mathml.mjs';
import { iconButton } from './navigation.mjs';

// Relations a derivation line aligns on, longest first so \leq is not read as \le.
const RELATIONS = ['\\Leftrightarrow', '\\Rightarrow', '\\approx', '\\propto', '\\equiv', '\\leq', '\\geq', '\\neq', '\\iff', '\\sim', '\\le', '\\ge', '\\to', '=', '<', '>'];

// Splits a line's LaTeX at its first relation outside any group or bracket, so every line
// aligns on it, as in an aligned derivation; a line that opens with a relation continues
// the line above.
export function splitRelation(latex) {
  let depth = 0;
  for (let index = 0; index < latex.length; index++) {
    const rest = latex.slice(index), char = latex[index];
    if (char === '\\') {
      const command = /^\\(?:[A-Za-z]+|.)/.exec(rest)[0];
      if (!depth && RELATIONS.includes(command) && !/^[A-Za-z]/.test(latex[index + command.length] || '')) {
        return [latex.slice(0, index), command, latex.slice(index + command.length)];
      }
      if (command === '\\{' || command === '\\langle') depth++;
      if (command === '\\}' || command === '\\rangle') depth = Math.max(0, depth - 1);
      index += command.length - 1;
    } else if ('{(['.includes(char)) depth++;
    else if ('})]'.includes(char)) depth = Math.max(0, depth - 1);
    else if (!depth && '=<>'.includes(char)) return [latex.slice(0, index), char, latex.slice(index + 1)];
  }
  return ['', '', latex];
}

function line(entry) {
  const item = node('li', 'derivation-line'), expression = node('div', 'derivation-math');
  const [left, relation, right] = splitRelation(entry.latex);
  const typeset = globalThis.katex && [left, relation, right].map(part => part.trim() ? texElement(part, { display: true }) : null);
  if (typeset && typeset.every((part, index) => part || ![left, relation, right][index].trim())) {
    const [l, r, rest] = typeset;
    expression.append(append(node('span', 'derivation-left'), ...(l ? [l] : [])),
      append(node('span', 'derivation-relation'), ...(r ? [r] : [])),
      // A long right side wraps after its operators on a phone instead of running off-screen.
      append(node('span', 'derivation-right'), ...(rest ? [rest] : [])));
  } else {
    // Without KaTeX the whole line shows as the build's MathML, unaligned.
    const whole = texElement(entry.latex, { display: true, mathml: entry.mathml });
    expression.append(append(node('span', 'derivation-right derivation-whole'), whole || node('span', '', entry.latex)));
  }
  item.append(expression);
  if (entry.reason) item.append(studyText('p', 'derivation-reason', entry.reason));
  return item;
}

// Working shown one transformation per line, each with the reason it follows. As a
// walkthrough, lines appear one at a time with earlier ones kept for comparison, and the
// state each line reaches is drawn beside it; "Show all steps" reads the whole working.
export function renderDerivation(block, renderVisual) {
  const box = node('div', `derivation${block.walkthrough ? ' walkthrough' : ''}`);
  const items = [];
  for (const group of block.groups) {
    const list = node('ol', 'derivation-lines');
    for (const entry of group.lines) { const item = line(entry); items.push([item, entry]); list.append(item); }
    box.append(...(group.label ? [studyText('p', 'derivation-label', group.label)] : []), list);
  }
  if (!block.walkthrough) return box;
  const stage = node('div', 'derivation-visual'), status = node('p', 'visually-hidden');
  status.setAttribute('aria-live', 'polite');
  let index = 0, all = false;
  const prev = iconButton('Previous step', 'left', () => { index--; update(); });
  const next = iconButton('Next step', 'right', () => { index++; update(); });
  const counter = node('span', 'small');
  const whole = node('button', 'quiet derivation-all', 'Show all steps');
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
    counter.textContent = all ? `${items.length} steps` : `${index + 1} / ${items.length}`;
    prev.disabled = all || index === 0; next.disabled = all || index === items.length - 1;
    whole.textContent = all ? 'Step through' : 'Show all steps';
    whole.setAttribute('aria-pressed', String(all));
    const [, entry] = items[index];
    status.textContent = all ? '' : `Step ${index + 1} of ${items.length}. ${plainText(entry.reason || '')}`;
  }
  box.append(stage, controls, status);
  update();
  return box;
}
