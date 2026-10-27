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
  } else if (check.kind === 'graph') return graphResponse(check, draft, edit);
  else if (check.kind === 'plot') return plotResponse(check, draft, edit);
  return { root, validate: () => validate(), showResult: checked => showResult(checked) };
}
