import { node, svgNode, studyText, button, append } from './dom.mjs';
import { graphResponse, plotResponse } from './graph-response.mjs';
import { renderCode, codeEditor, languageName } from './code.mjs';
import { openInWorkspace } from './files.mjs';

// A code model answer stays code: highlighted, literal and labelled with its language.
function modelAnswer(check) {
  if (check.format !== 'code') return studyText('p', '', check.model_answer);
  const region = node('div', 'code-region model-code'); region.tabIndex = 0;
  region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Model answer');
  region.append(node('span', 'small code-language', languageName(check.language, check.file || '') || 'Code'), renderCode(check.model_answer, check.language || (check.file || '').split('.').pop()));
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
  box.append(node('summary', '', 'Show reasoning'));
  const list = node('ul', 'option-explanation-list');
  for (const option of check.options) {
    const right = option.key === check.correct, item = node('li', right ? 'right' : 'wrong');
    const mark = node('span', 'option-mark'), icon = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
    icon.append(svgNode('path', { d: right ? 'M3.5 8.5 6.5 11.5 12.5 4.5' : 'M4.5 4.5l7 7M11.5 4.5l-7 7' }));
    mark.append(icon, node('span', 'visually-hidden', right ? 'Correct: ' : 'Incorrect: '));
    item.append(mark, append(node('div', 'option-explanation-body'), studyText('p', 'option-explanation-title', option.text), studyText('p', '', option.feedback)));
    list.append(item);
  }
  box.append(list);
  return box;
}

// Only a choice is answered on screen. Code opens its skeleton in an editor and diagrams
// and plots stay interactive; every other answer is worked on paper, then compared.
// `shown` lists the files whose lines the step already shows; those open from the excerpt.
export function renderResponse(check, draft, edit, identity, shown = []) {
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
  if (check.kind === 'self_check' && check.format === 'code' && check.file) {
    // The code is written where it lives: in the project file, as in the real exercise.
    if (!shown.includes(check.file)) root.append(button(`Open ${check.file.split('/').pop()}`, () => openInWorkspace(check.file), 'secondary project-target'));
    return result;
  }
  if (check.kind === 'self_check' && check.format === 'code') {
    // A linked label, not a wrapping one, so the editor's highlighted copy stays out of its name.
    const input = node('textarea'), label = node('label', '', `Your code${check.language ? ` (${languageName(check.language)})` : ''}`);
    input.id = `code-${identity}`; label.htmlFor = input.id;
    const wrapper = append(node('div', 'stack'), label);
    input.value = draft || check.starter_code || ''; input.maxLength = 20000;
    input.addEventListener('input', () => edit(input.value));
    wrapper.append(codeEditor(input, check.language));
    root.append(wrapper, node('p', 'small code-editor-hint', 'Code is not run. Tab indents; Esc, then Tab, leaves the editor.'));
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
    root.append(region);
  }
  return result;
}
