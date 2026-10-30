import { node, button, append, svgNode } from './dom.mjs';
import { diagram } from './reading.mjs';
import { renderPlot, plotNumber } from './plot.mjs';
import { iconButton } from './navigation.mjs';

function savedArray(value) {
  try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed : []; }
  catch { return []; }
}
function activate(element, action) {
  element.tabIndex = 0;
  element.addEventListener('click', action);
  element.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!event.repeat) action(); }
  });
}

export function graphResponse(check, draft, edit) {
  const root = node('div', 'exercise-response graph-response reading-material'), drawing = diagram(check.graph);
  root.append(node('p', 'small', check.mode === 'path' ? 'Select nodes in order.' : `Select ${check.mode}.`), drawing);
  drawing.querySelector('.diagram-state').hidden = true;
  drawing.querySelector('.diagram-controls').hidden = true;
  const graph = drawing.querySelector('svg'); graph.setAttribute('role', 'group');
  const nodes = new Map(check.graph.nodes.map(item => [item.key, item.label]));
  let selected = savedArray(draft).filter(key => typeof key === 'string').slice(0, 100);
  const controls = [], options = check.mode === 'edges' ? check.graph.edges.map(edge => ({ key: `${edge.start}--${edge.end}`, label: `${nodes.get(edge.start)} ${edge.directed ? '→' : '—'} ${nodes.get(edge.end)}` })) : check.graph.nodes;
  selected = selected.filter(key => options.some(item => item.key === key));
  const summary = node('p', 'graph-selection'); summary.setAttribute('aria-live', 'polite');
  const undo = iconButton('Undo', 'undo', () => { selected.pop(); change(); });
  const clear = button('Clear', () => { selected = []; change(); }, 'secondary');
  function choose(key) {
    if (check.mode === 'path') { if (selected.length >= 100) return; selected.push(key); }
    else selected = selected.includes(key) ? selected.filter(item => item !== key) : [...selected, key];
    change();
  }
  function change() { paint(); edit(JSON.stringify(selected)); }
  function paint() {
    summary.replaceChildren();
    summary.append(node('span', 'small', check.mode === 'path' ? 'Path:' : 'Selected:'));
    for (const [index, key] of selected.entries()) {
      if (index) summary.append(' ', node('span', 'small', check.mode === 'path' ? '→' : '·'));
      summary.append(' ', node('span', 'selection-chip', options.find(item => item.key === key).label));
    }
    if (!selected.length) summary.append(node('span', 'small', '—'));
    for (const { key, element } of controls) {
      element.classList.toggle('answer-selected', selected.includes(key));
      if (check.mode !== 'path') element.setAttribute('aria-checked', String(selected.includes(key)));
    }
    undo.disabled = clear.disabled = !selected.length;
  }
  for (const option of options) {
    let element = [...graph.querySelectorAll(check.mode === 'edges' ? '[data-edge-key]' : '[data-node-key]')].find(el => (el.dataset.nodeKey || el.dataset.edgeKey) === option.key);
    if (check.mode === 'edges') {
      // A wide transparent copy of the edge takes the tap; its arrowhead moves into the control.
      const group = svgNode('g', { class: 'graph-edge-control' }), hit = element.cloneNode(); hit.removeAttribute('data-edge-key'); hit.classList.add('graph-hit');
      const head = graph.querySelector(`[data-arrow-key="${option.key}"]`);
      element.before(group); group.append(hit, element, ...(head ? [head] : [])); element = group;
    } else element.prepend(svgNode('circle', { cx: element.dataset.cx, cy: element.dataset.cy, r: element.dataset.reach, class: 'graph-hit' }));
    element.classList.add('graph-control'); element.setAttribute('role', check.mode === 'path' ? 'button' : 'checkbox'); element.setAttribute('aria-label', option.label);
    activate(element, () => choose(option.key)); controls.push({ key: option.key, element });
  }
  root.append(append(node('div', 'graph-answer-bar'), summary, ...(check.mode === 'path' ? [undo] : []), clear)); paint();
  return { root, showResult: () => {}, validate: () => ({ valid: selected.length > 0,
    correct: check.answers.some(answer => selected.length === answer.length && (check.mode === 'path' ? answer.every((key, i) => selected[i] === key) : answer.every(key => selected.includes(key)))), repairs: [check.feedback] }) };
}

const numeric = value => typeof value === 'string' && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim()) && Number.isFinite(Number(value));
export function plotResponse(check, draft, edit) {
  const root = node('div', 'exercise-response plot-response reading-material'), plot = renderPlot(check.plot);
  let values = savedArray(draft).slice(0, check.x_values.length).map(value => typeof value === 'string' ? value.slice(0, 200) : '');
  const inputs = [], handles = [], line = svgNode('path', { class: 'plot-line answer-line' }); plot.series.append(line);
  plot.graph.setAttribute('role', 'group');
  const instruction = node('p', 'small', 'Tap the graph or enter y values. Arrow keys adjust focused points.');
  root.append(instruction, plot.root);
  const fields = node('div', 'plot-values');
  function change(index, value) { values[index] = value; paint(); edit(JSON.stringify(values)); }
  const valid = i => numeric(values[i]) && Number(values[i]) >= check.plot.y_min && Number(values[i]) <= check.plot.y_max;
  function paint() {
    let drawing = '', connected = false;
    check.x_values.forEach((x, i) => {
      const ok = valid(i), y = ok ? Number(values[i]) : check.plot.y_min;
      inputs[i].value = values[i] || '';
      handles[i].setAttribute('cy', plot.y(y)); handles[i].classList.toggle('unplaced', !ok);
      handles[i].setAttribute('aria-valuenow', y);
      handles[i].setAttribute('aria-valuetext', ok ? plotNumber(y) : 'Not placed');
      handles[i].setAttribute('aria-label', `x = ${plotNumber(x)}, ${ok ? `y = ${plotNumber(y)}` : 'not placed'}`);
      if (ok) { drawing += `${connected ? 'L' : 'M'}${plot.x(x)},${plot.y(y)} `; connected = true; } else connected = false;
    }); line.setAttribute('d', drawing);
    clear.disabled = !values.some(Boolean);
  }
  check.x_values.forEach((x, i) => {
    const label = node('label', '', `x = ${plotNumber(x)}`), input = node('input'); input.type = 'text'; input.inputMode = 'decimal'; input.maxLength = 200; input.autocomplete = 'off';
    input.setAttribute('aria-label', `y at x = ${plotNumber(x)}`); input.addEventListener('input', () => change(i, input.value)); label.append(input); fields.append(label); inputs.push(input);
    const handle = svgNode('circle', { cx: plot.x(x), cy: plot.y(check.plot.y_min), r: 9, class: 'plot-handle', role: 'slider', tabindex: 0, 'aria-valuemin': check.plot.y_min, 'aria-valuemax': check.plot.y_max, 'aria-orientation': 'vertical' });
    handle.addEventListener('keydown', event => {
      if (!['ArrowUp','ArrowDown','Home','End','Delete','Backspace'].includes(event.key)) return;
      event.preventDefault();
      const current = valid(i) ? Number(values[i]) : check.plot.y_min;
      const next = event.key === 'Home' ? check.plot.y_min : event.key === 'End' ? check.plot.y_max : Math.min(check.plot.y_max, Math.max(check.plot.y_min, current + (event.key === 'ArrowUp' ? check.snap : -check.snap)));
      change(i, ['Delete','Backspace'].includes(event.key) ? '' : String(Math.max(check.plot.y_min, Math.min(check.plot.y_max, Number(next.toPrecision(15))))));
    });
    plot.series.append(handle); handles.push(handle);
  });
  plot.graph.addEventListener('click', event => {
    const position = plot.graph.createSVGPoint(); position.x = event.clientX; position.y = event.clientY;
    const point = position.matrixTransform(plot.graph.getScreenCTM().inverse());
    if (point.x < plot.area.left || point.x > plot.area.right || point.y < plot.area.top || point.y > plot.area.bottom) return;
    const closest = check.x_values.reduce((best, x, i) => Math.abs(plot.x(x) - point.x) < Math.abs(plot.x(check.x_values[best]) - point.x) ? i : best, 0);
    const raw = check.plot.y_max - (point.y - plot.area.top) / (plot.area.bottom - plot.area.top) * (check.plot.y_max - check.plot.y_min);
    const value = Math.max(check.plot.y_min, Math.min(check.plot.y_max, check.plot.y_min + Math.round((raw-check.plot.y_min)/check.snap)*check.snap));
    change(closest, String(Math.max(check.plot.y_min, Math.min(check.plot.y_max, Number(value.toPrecision(15)))))); handles[closest].focus({ preventScroll: true });
  });
  const clear = button('Clear', () => { values = []; paint(); edit(''); }, 'secondary');
  // The plot redraws at its shown width; its handles follow the new scale.
  plot.onResize(() => { check.x_values.forEach((x, i) => handles[i].setAttribute('cx', plot.x(x))); paint(); });
  root.append(fields, clear); paint();
  return { root, showResult: checked => inputs.forEach((input, i) => {
    if (checked && (!valid(i) || Math.abs(Number(values[i])-check.answer[i]) > check.tolerance)) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
  }), validate: () => ({ valid: check.x_values.every((_, i) => valid(i)), correct: check.x_values.every((_, i) => valid(i) && Math.abs(Number(values[i])-check.answer[i]) <= check.tolerance), repairs: [check.feedback] }) };
}
