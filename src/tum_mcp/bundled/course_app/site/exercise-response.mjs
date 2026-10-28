import { node, studyText, button, append } from './dom.mjs';
import { graphResponse, plotResponse } from './graph-response.mjs';

const number = value => /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim()) && Number.isFinite(Number(value));
const normalize = value => value.trim().replace(/\s+/g, ' ').toLowerCase();
function structured(text, array = false) {
  try { const value = JSON.parse(text); return value && typeof value === 'object' && Array.isArray(value) === array ? value : array ? [] : {}; }
  catch { return array ? [] : {}; }
}
function field(label, multiline, value, edit) {
  const wrapper = node('label', 'stack', label), input = node(multiline ? 'textarea' : 'input');
  if (!multiline) { input.type = 'text'; input.autocomplete = 'off'; }
  input.value = value; input.maxLength = 20000;
  input.addEventListener('input', () => edit(input.value)); wrapper.append(input);
  return { wrapper, input };
}

function seeded(identity) {
  let state = [...identity].reduce((hash, character) => Math.imul(hash ^ character.charCodeAt(0), 16777619), 2166136261) >>> 0;
  return () => { state = Math.imul(state ^ (state >>> 15), 2246822507) >>> 0; return state / 4294967296; };
}
function orderResponse(check, draft, edit, identity) {
  const root = node('div', 'exercise-response order-response'), keys = check.items.map(item => item.key);
  const target = check.answers[0], distractors = keys.length > target.length;
  const saved = structured(draft);
  let order = Array.isArray(saved.order) && saved.order.length === keys.length && keys.every(key => saved.order.includes(key)) ? saved.order : null;
  if (!order) {
    // A stable shuffle per exercise step; the authored order is often the solution.
    const random = seeded(identity); order = [...keys];
    for (let attempt = 0; attempt < 5 && check.answers.some(answer => answer.join() === order.filter(key => answer.includes(key)).join()); attempt++)
      for (let index = order.length - 1; index > 0; index--) { const swap = Math.floor(random() * (index + 1)); [order[index], order[swap]] = [order[swap], order[index]]; }
  }
  const left = new Set(Array.isArray(saved.left_out) ? saved.left_out.filter(key => keys.includes(key)) : []);
  const save = () => edit(JSON.stringify({ order, left_out: [...left] }));
  const list = node('ol', 'order-list');
  root.append(node('p', 'small', distractors ? 'Arrange the lines in order and leave out the ones that do not belong.' : 'Arrange the items in order.'), list);
  const content = item => item.code ? append(node('pre', 'order-code'), node('code', '', item.code)) : studyText('span', '', item.text);
  function render(focus) {
    list.replaceChildren();
    order.forEach((key, index) => {
      const item = check.items.find(entry => entry.key === key), row = node('li', `order-item${left.has(key) ? ' left-out' : ''}`);
      const label = (item.code || studyText('span', '', item.text).textContent).trim();
      const move = (offset, name) => {
        const control = button(name === 'up' ? '↑' : '↓', () => {
          [order[index], order[index + offset]] = [order[index + offset], order[index]]; save(); render(`${key}:${name}`);
        }, 'secondary order-move');
        control.setAttribute('aria-label', `Move "${label}" ${name}`); control.dataset.focus = `${key}:${name}`;
        control.disabled = index + offset < 0 || index + offset >= order.length; return control;
      };
      const controls = append(node('span', 'order-controls'), move(-1, 'up'), move(1, 'down'));
      if (distractors) {
        const toggle = node('label', 'order-leave'), box = node('input'); box.type = 'checkbox'; box.checked = left.has(key);
        box.dataset.focus = `${key}:leave`;
        box.addEventListener('change', () => { if (box.checked) left.add(key); else left.delete(key); save(); render(`${key}:leave`); });
        toggle.append(box, node('span', '', 'Leave out')); controls.append(toggle);
      }
      row.append(content(item), controls); list.append(row);
    });
    if (focus) list.querySelector(`[data-focus="${CSS.escape(focus)}"]`)?.focus();
  }
  render();
  const validate = () => {
    const used = order.filter(key => !left.has(key));
    const correct = check.answers.some(answer => answer.length === used.length && answer.every((key, index) => used[index] === key));
    const placed = target.filter((key, index) => used[index] === key).length;
    return { valid: used.length > 1, correct, repairs: [check.feedback, `${placed} of ${target.length} positions match an accepted order.`] };
  };
  return { root, validate, showResult: () => {} };
}

export function renderResponse(check, draft, edit, identity) {
  const root = node('div', 'exercise-response');
  let value = draft, validate = () => ({ valid: true, correct: false, repairs: [] }), showResult = () => {};
  const change = next => { value = next; edit(next); };
  if (!check) return { root, validate, showResult };
  if (check.kind === 'choice') {
    const choices = node('fieldset', 'exercise-choices'); choices.append(node('legend', 'visually-hidden', 'Your answer'));
    for (const option of check.options) {
      const label = node('label', 'option'), input = node('input'); input.type = 'radio'; input.name = identity;
      input.value = option.key; input.checked = value === option.key;
      input.addEventListener('change', () => change(option.key)); label.append(input, studyText('span', 'option-body', option.text)); choices.append(label);
    }
    root.append(choices);
    validate = () => ({ valid: check.options.some(option => option.key === value), correct: value === check.correct,
      repairs: [check.options.find(option => option.key === value)?.feedback || 'Choose an answer.'] });
  } else if (check.kind === 'numeric' || check.kind === 'self_check') {
    const format = check.format || 'text';
    const { wrapper, input } = field(check.kind === 'numeric' || format === 'text' ? 'Your answer' : format === 'code' ? `${check.language || 'Code'} draft` : 'Working', check.kind === 'self_check', value, change);
    if (check.kind === 'numeric') {
      input.inputMode = 'decimal'; input.classList.add('numeric-input');
      root.append(studyText('p', 'small', `Enter ${check.tolerance === 0 ? 'the exact value' : 'a decimal'}${check.unit ? ` in ${check.unit}` : ''}${check.tolerance ? ` (within ${check.tolerance} of the target)` : ''}.`), wrapper);
      validate = () => ({ valid: number(value), correct: number(value) && Math.abs(Number(value) - check.answer) <= check.tolerance,
        repairs: [check.feedback] });
    } else {
      const details = node(format === 'text' ? 'details' : 'div', format === 'text' ? 'disclosure response-writing' : 'response-writing');
      if (format === 'text') { details.open = Boolean(value); details.append(node('summary', '', 'Write')); }
      details.append(wrapper);
      if (format === 'code') {
        input.classList.add('code-input'); input.spellcheck = false; input.autocapitalize = 'off';
        input.rows = 5;
        if (check.starter_code) {
          const use = button('Use starter code', () => {
            if (input.value) return;
            input.value = check.starter_code; change(input.value); use.disabled = true; input.focus();
          }, 'secondary');
          use.disabled = Boolean(value);
          input.addEventListener('input', () => { use.disabled = Boolean(input.value); });
          const starter = node('details', 'disclosure starter-code'); starter.append(node('summary', '', 'Starter code'), append(node('pre'), node('code', '', check.starter_code)), use);
          const listing = starter.querySelector('pre'); listing.tabIndex = 0; listing.setAttribute('role', 'region'); listing.setAttribute('aria-label', 'Starter code');
          details.append(starter);
        }
      } else if (format === 'math') { input.classList.add('math-input'); input.rows = 5; }
      root.append(node('p', 'small', format === 'code' ? 'Optional draft. Code is not run or graded.'
        : format === 'math' ? 'Work on paper or draft in plain text / LaTeX.' : 'Work on paper or draft here.'), details);
    }
  } else if (check.kind === 'table') {
    const cells = structured(value), inputs = [];
    const region = node('div', 'table-region answer-table'); region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', check.caption);
    const table = node('table'), header = node('tr'); table.append(studyText('caption', '', check.caption));
    const rowTitle = node('th'); rowTitle.scope = 'col'; rowTitle.append(node('span', 'visually-hidden', 'Row')); header.append(rowTitle);
    for (const title of check.columns) { const th = studyText('th', '', title); th.scope = 'col'; header.append(th); }
    table.append(append(node('thead'), header)); const body = node('tbody');
    for (const row of check.rows) {
      const tr = node('tr'), th = studyText('th', '', row.label); th.scope = 'row'; tr.append(th);
      row.cells.forEach((cell, index) => {
        const td = node('td');
        if (cell.kind === 'given') td.append(studyText('span', '', cell.text));
        else {
          const input = node('input'); input.type = 'text'; input.maxLength = 200; input.autocomplete = 'off';
          input.value = typeof cells[cell.key] === 'string' ? cells[cell.key].slice(0, 200) : '';
          input.setAttribute('aria-label', `${row.label}: ${check.columns[index]}`);
          if (cell.kind === 'numeric') input.inputMode = 'decimal';
          input.addEventListener('input', () => { cells[cell.key] = input.value; change(JSON.stringify(cells)); });
          inputs.push({ cell, input, label: `${row.label}, ${check.columns[index]}` }); td.append(input);
        }
        tr.append(td);
      }); body.append(tr);
    }
    table.append(body); region.append(table); root.append(node('p', 'small', 'Complete each answer cell before checking.'), region);
    const matches = ({ cell, input }) => cell.kind === 'numeric' ? number(input.value) && Math.abs(Number(input.value) - cell.answer) <= cell.tolerance
      : cell.accepted.some(answer => normalize(input.value) === normalize(answer));
    validate = () => ({ valid: inputs.every(({ cell, input }) => cell.kind === 'numeric' ? number(input.value) : Boolean(input.value.trim())),
      correct: inputs.every(matches), repairs: inputs.filter(item => !matches(item)).map(item => `${item.label}: ${item.cell.feedback}`) });
    showResult = checked => { for (const item of inputs) { if (checked && !matches(item)) item.input.setAttribute('aria-invalid', 'true'); else item.input.removeAttribute('aria-invalid'); } };
  } else if (check.kind === 'text') {
    const code = check.format === 'code';
    const { wrapper, input } = field(code ? `${check.language || 'Code'} answer` : 'Your answer', false, value, change);
    if (code) { input.classList.add('code-input'); input.spellcheck = false; input.autocapitalize = 'off'; }
    root.append(wrapper);
    const shape = text => {
      const spaced = check.whitespace === 'exact' ? text : check.whitespace === 'ignore' ? text.replace(/\s+/g, '') : text.trim().replace(/\s+/g, ' ');
      return check.case_sensitive ? spaced : spaced.toLowerCase();
    };
    validate = () => ({ valid: Boolean(value.trim()), correct: check.accepted.some(answer => shape(answer) === shape(value)), repairs: [check.feedback] });
  } else if (check.kind === 'order') return orderResponse(check, draft, edit, identity);
  else if (check.kind === 'graph') return graphResponse(check, draft, edit);
  else if (check.kind === 'plot') return plotResponse(check, draft, edit);
  return { root, validate: () => validate(), showResult: checked => showResult(checked) };
}
