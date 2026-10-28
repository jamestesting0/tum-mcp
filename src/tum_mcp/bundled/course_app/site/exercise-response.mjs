import { node, studyText, button, append } from './dom.mjs';
import { graphResponse, plotResponse } from './graph-response.mjs';

// A textarea that behaves like a small code editor: Tab indents, Enter keeps the
// indentation, and Esc then Tab leaves it, so keyboard users are never trapped.
function codeEditor(input) {
  let leaving = false;
  const fit = () => { input.rows = Math.max(8, input.value.split('\n').length + 1); };
  const insert = text => {
    if (document.execCommand('insertText', false, text)) return;
    input.setRangeText(text, input.selectionStart, input.selectionEnd, 'end'); input.dispatchEvent(new Event('input'));
  };
  input.addEventListener('keydown', event => {
    const plain = !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey;
    if (event.key === 'Tab' && plain && !leaving) { event.preventDefault(); insert('    '); }
    else if (event.key === 'Enter' && plain && !event.isComposing) {
      const before = input.value.slice(0, input.selectionStart), line = before.slice(before.lastIndexOf('\n') + 1);
      event.preventDefault(); insert(`\n${line.match(/^[ \t]*/)[0]}${/[{:([]\s*$/.test(line) ? '    ' : ''}`);
    }
    leaving = event.key === 'Escape';
  });
  input.addEventListener('blur', () => { leaving = false; });
  input.addEventListener('input', fit); fit();
}
// A code model answer stays code: monospaced, literal and labelled with its language.
function modelAnswer(check) {
  if (check.format !== 'code') return studyText('p', '', check.model_answer);
  const region = node('div', 'code-region model-code'); region.tabIndex = 0;
  region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Model answer');
  region.append(node('span', 'small', check.language || 'code'), append(node('pre'), node('code', '', check.model_answer)));
  return region;
}
// What a learner compares their own work with, for every check except a choice.
export function expectedAnswer(check) {
  const box = node('div', 'expected-answer');
  const value = text => studyText('p', 'expected-value', text);
  const number = item => `${item.answer}${item.unit ? ` ${item.unit}` : ''}`;
  switch (check.kind) {
    case 'self_check':
      box.append(modelAnswer(check), append(node('ul'), ...check.rubric.map(text => studyText('li', '', text))));
      break;
    case 'text': box.append(check.format === 'code' ? modelAnswer({ format: 'code', language: check.language, model_answer: check.answer }) : value(check.answer)); break;
    case 'numeric': box.append(value(number(check))); break;
    case 'table': {
      const table = node('table'), header = node('tr');
      for (const title of ['', ...check.columns]) { const th = studyText('th', '', title); th.scope = 'col'; header.append(th); }
      const body = node('tbody');
      for (const row of check.rows) body.append(append(node('tr'), studyText('th', '', row.label),
        ...row.cells.map(cell => studyText('td', '', cell.kind === 'given' ? cell.text : cell.kind === 'numeric' ? number(cell) : cell.answer))));
      table.append(append(node('thead'), header), body);
      const region = append(node('div', 'table-region'), table); region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Expected answer');
      box.append(region);
      break;
    }
    case 'graph': {
      const label = new Map(check.graph.nodes.map(item => [item.key, item.label]));
      const name = key => key.split('--').map(part => label.get(part) || part).join('\u2013');
      box.append(value(`${{ nodes: 'Nodes', edges: 'Edges', path: 'Path' }[check.mode]}: ${check.answers[0].map(name).join(check.mode === 'path' ? ' \u2192 ' : ', ')}`));
      break;
    }
    case 'plot': {
      const table = node('table');
      table.append(append(node('thead'), append(node('tr'), studyText('th', '', check.plot.x_label), studyText('th', '', check.plot.y_label))));
      table.append(append(node('tbody'), ...check.x_values.map((x, i) => append(node('tr'), node('td', '', String(x)), node('td', '', String(check.answer[i]))))));
      box.append(append(node('div', 'table-region'), table));
      break;
    }
  }
  return box;
}

// After a choice is checked: why every option is right or wrong, collapsed by default.
export function optionExplanations(check) {
  const box = node('details', 'disclosure option-explanations');
  box.append(node('summary', '', 'Why each option is right or wrong'));
  const list = node('ul', 'option-explanation-list');
  for (const option of check.options) {
    const right = option.key === check.correct, item = node('li', right ? 'right' : 'wrong');
    item.append(append(node('p', 'option-explanation-title'), node('span', 'option-verdict', right ? 'Correct' : 'Incorrect'), studyText('span', '', option.text)), studyText('p', '', option.feedback));
    list.append(item);
  }
  box.append(list);
  return box;
}

// Only a choice is answered on screen. Code opens its skeleton in an editor and diagrams
// and plots stay interactive; every other answer is worked on paper, then compared.
export function renderResponse(check, draft, edit, identity) {
  const root = node('div', 'exercise-response');
  const result = { root, validate: () => ({ valid: true, correct: false, repairs: [] }), showResult: () => {} };
  if (!check) return result;
  if (check.kind === 'choice') {
    let value = draft;
    const choices = node('fieldset', 'exercise-choices'); choices.append(node('legend', 'visually-hidden', 'Your answer'));
    for (const option of check.options) {
      const label = node('label', 'option'), input = node('input'); input.type = 'radio'; input.name = identity;
      input.value = option.key; input.checked = value === option.key;
      input.addEventListener('change', () => { value = option.key; edit(option.key); }); label.append(input, studyText('span', 'option-body', option.text)); choices.append(label);
    }
    root.append(choices);
    result.validate = () => ({ valid: check.options.some(option => option.key === value), correct: value === check.correct,
      repairs: [check.options.find(option => option.key === value)?.feedback || 'Choose an answer.'] });
    return result;
  }
  if (check.kind === 'graph') return graphResponse(check, draft, edit);
  if (check.kind === 'plot') return plotResponse(check, draft, edit);
  if (check.kind === 'self_check' && check.format === 'code') {
    const wrapper = node('label', 'stack', `Your code${check.language ? ` (${check.language})` : ''}`), input = node('textarea');
    input.value = draft || check.starter_code || ''; input.maxLength = 20000;
    input.classList.add('code-input'); input.spellcheck = false; input.autocapitalize = 'off'; input.setAttribute('autocorrect', 'off');
    input.addEventListener('input', () => edit(input.value)); wrapper.append(input);
    codeEditor(input);
    root.append(node('p', 'small', 'Write the code here or in your own editor, then compare it with the model answer. Code is not run. Tab indents; Esc then Tab leaves the editor.'), wrapper);
    if (check.starter_code) root.append(append(node('div', 'cluster code-tools'), button('Reset to starter code', () => { input.value = check.starter_code; input.dispatchEvent(new Event('input')); input.focus(); }, 'quiet')));
    return result;
  }
  if (check.kind === 'table') {
    const region = node('div', 'table-region answer-table'); region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', check.caption);
    const table = node('table'), header = node('tr'); table.append(studyText('caption', '', check.caption));
    const rowTitle = node('th'); rowTitle.scope = 'col'; rowTitle.append(node('span', 'visually-hidden', 'Row')); header.append(rowTitle);
    for (const title of check.columns) { const th = studyText('th', '', title); th.scope = 'col'; header.append(th); }
    table.append(append(node('thead'), header)); const body = node('tbody');
    for (const row of check.rows) {
      const tr = node('tr'), th = studyText('th', '', row.label); th.scope = 'row'; tr.append(th);
      for (const cell of row.cells) tr.append(cell.kind === 'given' ? studyText('td', '', cell.text) : append(node('td', 'blank-cell'), node('span', 'visually-hidden', 'to fill in')));
      body.append(tr);
    }
    table.append(body); region.append(table);
    root.append(node('p', 'small', 'Fill in the empty cells on paper, then compare.'), region);
  }
  return result;
}
