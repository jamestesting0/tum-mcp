import { node, studyText, append, plainText, segmented } from '../shell/dom.mjs';
import { iconButton, iconGlyph, arrowPaging, cycleIndex } from '../shell/navigation.mjs';
import { drawGrids } from '../visuals/grid.mjs';
import { drawGraph, setNodeValue } from '../visuals/graph.mjs';
import { renderCode, languageName, lineSet, markLines } from './code.mjs';
import { renderDerivation } from './derivation.mjs';
import { renderPlot } from '../visuals/plot.mjs';

// Two runs part at the first step that does or shows something different; the reason and
// the pitfall may be worded differently without making it a different step.
const shape = step => JSON.stringify({ ...step, why: undefined, note: undefined });
export function divergence(first, second) {
  const shared = Math.min(first.length, second.length);
  for (let index = 0; index < shared; index++) if (shape(first[index]) !== shape(second[index])) return index;
  return first.length === second.length ? null : shared;
}

// The picture the steps move over. Each kind marks what one step reaches: graph nodes and
// edges, table rows and changed cells, running code lines, lines of working, plot series,
// figure layers.
function stageView(stage, renderBody, steps, runs = [steps]) {
  switch (stage.kind) {
    case 'diagram': {
      // Every value a node shows in any step, so the layout leaves room for the widest.
      const values = Object.fromEntries(stage.nodes.map(item => [item.key, steps.map(step => step.node_values?.[item.key]).filter(Boolean)]));
      const { graph, groups } = drawGraph(stage, plainText(stage.description), values);
      const ends = new Map(stage.edges.map(edge => [`${edge.start}--${edge.end}`, edge]));
      let current = null;
      // A tree whose steps never say which nodes exist yet still shows every node, as the
      // slides do, but the ones no step has generated so far stay faint until one does.
      const grows = stage.layout === 'tree' && !steps.some(step => step.visible_nodes);
      const reach = [];
      for (const [index, step] of steps.entries()) {
        reach.push(new Set([...(reach[index - 1] || []), ...(step.active || []), ...(step.frontier || []), ...(step.cutoff || []), ...(step.visited || [])]));
      }
      const used = new Set();
      steps.forEach((step, index) => {
        for (const item of stage.nodes) {
          if (step.visible_nodes && !step.visible_nodes.includes(item.key)) continue;
          if (step.active.includes(item.key)) used.add('active');
          else if (step.frontier.includes(item.key)) used.add('frontier');
          else if (step.cutoff?.includes(item.key)) used.add('cutoff');
          else if (step.visited.includes(item.key)) used.add('visited');
          if (grows && reach[index].size && !reach[index].has(item.key)) used.add('unreached');
        }
      });
      const legend = node('div', 'graph walk-legend');
      for (const [state, label] of [['active', 'Current'], ['frontier', 'Frontier'], ['cutoff', 'Cut off'], ['visited', 'Expanded'], ['unreached', 'Not reached yet']]) {
        if (!used.has(state)) continue;
        const swatch = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        swatch.setAttribute('class', 'walk-legend-swatch'); swatch.setAttribute('viewBox', '0 0 18 18'); swatch.setAttribute('aria-hidden', 'true');
        const group = document.createElementNS(swatch.namespaceURI, 'g');
        group.setAttribute('class', state);
        const circle = document.createElementNS(swatch.namespaceURI, 'circle');
        circle.setAttribute('cx', '9'); circle.setAttribute('cy', '9'); circle.setAttribute('r', '6');
        group.append(circle); swatch.append(group);
        legend.append(append(node('span', 'walk-legend-item'), swatch, node('span', '', label)));
      }
      const show = step => {
        current = step;
        const shown = key => !step.visible_nodes || step.visible_nodes.includes(key);
        const reached = grows && reach[steps.indexOf(step)]?.size ? reach[steps.indexOf(step)] : null;
        for (const [key, group] of groups) {
          const active = step.active.includes(key);
          const frontier = !active && step.frontier.includes(key);
          const cutoff = !active && !frontier && (step.cutoff?.includes(key) || false);
          group.classList.toggle('active', active);
          group.classList.toggle('frontier', frontier);
          group.classList.toggle('cutoff', cutoff);
          group.classList.toggle('visited', !active && !frontier && !cutoff && step.visited.includes(key));
          group.setAttribute('visibility', shown(key) ? 'visible' : 'hidden');
          group.classList.toggle('unreached', Boolean(reached) && !reached.has(key));
          setNodeValue(group, step.node_values?.[key]);
        }
        const marked = new Set(stage.edges.filter(edge => step.edges.some(mark =>
          (mark.start === edge.start && mark.end === edge.end) ||
          (!edge.directed && mark.start === edge.end && mark.end === edge.start)
        )).map(edge => `${edge.start}--${edge.end}`));
        for (const line of graph.querySelectorAll('[data-edge-key], [data-arrow-key], [data-label-edge]')) {
          const key = line.dataset.edgeKey || line.dataset.arrowKey || line.dataset.labelEdge, edge = ends.get(key);
          line.classList.toggle('active', marked.has(key));
          line.setAttribute('visibility', !edge || (shown(edge.start) && shown(edge.end)) ? 'visible' : 'hidden');
          line.classList.toggle('unreached', Boolean(reached && edge) && !reached.has(edge.end));
        }
      };
      graph.addEventListener('graphdraw', () => { if (current) show(current); });
      return { element: append(node('div', 'graph-region'), graph), legend: used.size ? legend : null, show };
    }
    case 'table': {
      const element = renderBody(stage), rows = [...element.querySelectorAll('tbody tr')];
      return { element, show(step) {
        rows.forEach((row, index) => { row.hidden = index >= (step.shown ?? rows.length); });
        element.querySelectorAll('.walk-changed').forEach(cell => cell.classList.remove('walk-changed'));
        for (const cell of step.cells) {
          const [row, column] = cell.split(':').map(Number);
          rows[row - 1]?.children[column - 1]?.classList.add('walk-changed');
        }
      } };
    }
    case 'code': {
      const region = node('div', 'code-region'); region.tabIndex = 0;
      region.setAttribute('role', 'region'); region.setAttribute('aria-label', `${languageName(stage.language) || 'Code'} listing`);
      const pre = renderCode(stage.code, stage.language, { numbers: true });
      region.append(node('span', 'small code-language', /\s/.test(stage.language) ? stage.language : languageName(stage.language)), pre);
      return { element: region, show(step) {
        markLines(pre, step.lines ? lineSet(step.lines) : new Set());
        const marked = pre.querySelector('.code-line.marked');
        if (marked && region.scrollHeight > region.clientHeight) region.scrollTop = Math.max(0, marked.offsetTop - region.clientHeight / 3);
      } };
    }
    case 'derivation': {
      const element = renderDerivation(stage), lines = [...element.querySelectorAll('.derivation-line')];
      return { element, show(step) {
        const shown = step.shown ?? lines.length;
        lines.forEach((line, index) => { line.hidden = index >= shown; line.classList.toggle('current', index === shown - 1); });
      } };
    }
    case 'plot': {
      // Axes stay fixed and each step redraws the series drawn so far.
      const element = node('div', 'walk-plot');
      let drawn = null;
      return { element, show(step) {
        const keys = step.series ?? stage.series.map(line => line.key);
        if (drawn === keys.join()) return;
        drawn = keys.join();
        const series = stage.series.filter(line => keys.includes(line.key));
        element.replaceChildren(renderPlot({ ...stage, series, areas: (stage.areas || []).filter(area => keys.includes(area.series)) }).root);
      } };
    }
    case 'figure': {
      const element = renderBody(stage);
      if (stage.image) return imageStage(element, stage, steps);
      const named = new Set(steps.flatMap(step => step.layers || []));
      // Ids carry a per-figure prefix in the page; layers are named as authored.
      const layers = [...element.querySelectorAll('svg [id]')].filter(item => named.has(item.id.replace(/^figure-\d+-/, '')));
      return { element, show(step) {
        for (const layer of layers) {
          const shown = !step.layers || step.layers.includes(layer.id.replace(/^figure-\d+-/, ''));
          layer.setAttribute('visibility', shown ? 'visible' : 'hidden');
        }
      } };
    }
    case 'grid': {
      // A value a step writes holds for the later steps of its run.
      const values = new Map();
      for (const run of runs) {
        const held = new Map();
        for (const step of run) {
          for (const item of step.grid_values || []) held.set(`${item.grid}:${item.cell}`, item.value);
          values.set(step, new Map(held));
        }
      }
      const { svg, show } = drawGrids(stage, { captions: steps.some(step => (step.grid_arrows || []).some(arrow => arrow.label)) });
      const used = new Set(steps.flatMap(step => (step.grid_marks || []).map(mark => mark.mark || 'active')));
      const legend = node('div', 'graph walk-legend');
      for (const [state, label] of [['active', 'Current'], ['frontier', 'Frontier'], ['visited', 'Done'], ['path', 'Path']]) {
        if (!used.has(state)) continue;
        const swatch = node('span', `grid-swatch ${state}`); swatch.setAttribute('aria-hidden', 'true');
        legend.append(append(node('span', 'walk-legend-item'), swatch, node('span', '', label)));
      }
      return { element: append(node('div', 'grid-region'), svg), legend: used.size > 1 ? legend : null, show(step) {
        show({ marks: step.grid_marks || [], arrows: step.grid_arrows || [], values: values.get(step) });
      } };
    }
    default: throw new Error('Unsupported walkthrough stage. Rebuild the site with a compatible renderer.');
  }
}

// A lecture figure the steps work on: each step may outline the parts it uses (the rest dims)
// and may swap in another crop for a picture the lecture builds over several slides.
const SVG_NS = 'http://www.w3.org/2000/svg';
function imageStage(element, stage, steps) {
  const image = element.querySelector('img'), frame = node('div', 'figure-frame');
  image.loading = 'eager';
  image.replaceWith(frame); frame.append(image);
  for (const source of new Set(steps.map(step => step.frame).filter(Boolean))) new Image().src = source;
  const overlay = document.createElementNS(SVG_NS, 'svg');
  overlay.setAttribute('class', 'figure-regions'); overlay.setAttribute('viewBox', '0 0 1 1');
  overlay.setAttribute('preserveAspectRatio', 'none'); overlay.setAttribute('aria-hidden', 'true');
  const labels = node('div', 'figure-region-labels');
  frame.append(overlay, labels);
  return { element, show(step) {
    const source = step.frame || stage.image;
    if (image.getAttribute('src') !== source) image.src = source;
    const regions = step.regions || [];
    overlay.replaceChildren(); labels.replaceChildren();
    frame.classList.toggle('marked', regions.length > 0);
    if (!regions.length) return;
    const dim = document.createElementNS(SVG_NS, 'path');
    dim.setAttribute('class', 'figure-dim'); dim.setAttribute('fill-rule', 'evenodd');
    dim.setAttribute('d', ['M0 0H1V1H0Z', ...regions.map(r => `M${r.x} ${r.y}h${r.w}v${r.h}h${-r.w}Z`)].join(''));
    overlay.append(dim);
    for (const region of regions) {
      const outline = document.createElementNS(SVG_NS, 'rect');
      for (const [name, value] of Object.entries({ x: region.x, y: region.y, width: region.w, height: region.h })) outline.setAttribute(name, value);
      outline.setAttribute('class', 'figure-outline'); outline.setAttribute('vector-effect', 'non-scaling-stroke');
      overlay.append(outline);
      if (region.label) {
        const tag = studyText('span', 'figure-region-label', region.label);
        tag.style.left = `${region.x * 100}%`;
        tag.style.top = `${(region.y < 0.08 ? region.y + region.h : region.y) * 100}%`;
        tag.classList.toggle('below', region.y < 0.08);
        labels.append(tag);
      }
    }
  } };
}

function stateRows(step, before) {
  const rows = node('dl', 'frame-state walk-state');
  const previous = new Map((before?.state || []).map(row => [row.label, row.value]));
  for (const row of step.state || []) {
    const changed = before && previous.get(row.label) !== row.value, value = studyText('dd', changed ? 'changed' : '', row.value);
    if (changed) value.append(node('span', 'visually-hidden', ' (changed)'));
    rows.append(studyText('dt', '', row.label), value);
  }
  rows.hidden = !step.state?.length;
  return rows;
}

// Every step at once: what was done, why, and the state it reached, grouped by subgoal.
function traceTable(steps) {
  const labels = [...new Set(steps.flatMap(step => (step.state || []).map(row => row.label)))];
  const head = append(node('tr'), ...['Step', 'Action', 'Why', ...labels].map(label => { const th = studyText('th', '', label); th.scope = 'col'; return th; }));
  const body = node('tbody');
  steps.forEach((step, index) => {
    if (step.subgoal && step.subgoal !== steps[index - 1]?.subgoal) {
      const cell = studyText('th', '', step.subgoal); cell.colSpan = 3 + labels.length; cell.scope = 'colgroup';
      body.append(append(node('tr', 'walk-subgoal'), cell));
    }
    const values = new Map((step.state || []).map(row => [row.label, row.value]));
    const number = node('th', '', String(index + 1)); number.scope = 'row';
    const why = studyText('td', '', step.why);
    if (step.note) why.append(' ', append(node('span', 'walk-note-inline'), node('strong', '', 'Pitfall: '), studyText('span', '', step.note)));
    body.append(append(node('tr'), number, studyText('td', '', step.action), why, ...labels.map(label => studyText('td', '', values.get(label) || ''))));
  });
  const grid = append(node('table', 'walk-trace'), append(node('thead'), head), body);
  const region = append(node('div', 'table-region'), grid);
  region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'All steps');
  return region;
}

// A worked process one step at a time: the stage on top shows the state each step reaches,
// the controls sit right under it, and the card below says what is done and why. A short
// walkthrough shows one dot per step; a long one shows where the reader is ("Step 7 of 26 ·
// Limit 2") with a list to jump to any step or group, and a thin track split by group.
// Controls stay between the picture and the text, so a long explanation never pushes them
// away from the picture. "All steps" lists the whole trace. A variant replays a second run on
// the same stage, and the contrast appears at the step where the runs part.
const DOTS = 6;
export function renderWalkthrough(block, renderBody) {
  const box = node('div', 'walk');
  const runs = [{ label: block.label, steps: block.steps }, ...(block.variant ? [block.variant] : [])];
  const parts = runs.length > 1 ? divergence(runs[0].steps, runs[1].steps) : null;
  let run = 0, index = 0, all = false, view = null;
  const stage = node('div', 'walk-stage'), card = node('div', 'walk-card'), trace = node('div', 'walk-all');
  card.setAttribute('aria-live', 'polite');
  const prev = iconButton('Previous step', 'left', () => go(index - 1));
  const next = iconButton('Next step', 'right', () => go(index + 1));
  const position = node('div', 'walk-position');
  const pager = append(node('div', 'walk-pager'), prev, position, next);
  const whole = node('button', 'quiet walk-toggle', 'All steps');
  whole.type = 'button'; whole.setAttribute('aria-pressed', 'false');
  whole.addEventListener('click', () => { all = !all; close(); update(); });
  const track = node('div', 'walk-track'); track.setAttribute('aria-hidden', 'true');
  const controls = append(node('div', 'walk-controls'), track, pager, whole);
  if (block.stage) {
    view = stageView(block.stage, renderBody, runs.flatMap(item => item.steps), runs.map(item => item.steps));
    stage.append(view.element);
    if (view.legend) stage.append(view.legend);
  } else stage.hidden = true;
  let choice = null;
  if (runs.length > 1) {
    choice = segmented('Run', runs.map((item, place) => ({ value: String(place), label: item.label })), value => {
      run = Number(value); index = Math.min(index, runs[run].steps.length - 1); close(); update();
    }, { selected: '0' });
    box.append(choice.element);
  }
  box.append(stage, controls, card, trace);
  arrowPaging(box, prev, next);
  // Search opens the first step whose text holds every searched word.
  box.showMatch = words => {
    const text = step => [step.subgoal, step.action, step.why, step.note].filter(Boolean).join(' ').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    for (const [place, item] of runs.entries()) {
      const found = item.steps.findIndex(step => words.every(word => text(step).includes(word)));
      if (found < 0) continue;
      if (place !== run && choice) { choice.set(String(place)); run = place; }
      all = false; go(found); return true;
    }
    return false;
  };

  // Consecutive steps with one subgoal form a group: a run, a pass, a limit.
  const groupsOf = steps => steps.reduce((groups, step, place) => {
    if (!groups.length || step.subgoal !== steps[place - 1].subgoal) groups.push({ subgoal: step.subgoal, start: place, length: 0 });
    groups.at(-1).length++;
    return groups;
  }, []);

  // A short walkthrough: one dot per step, grouped by subgoal.
  function drawDots(steps) {
    const dots = node('div', 'walk-dots');
    for (const group of groupsOf(steps)) {
      const set = node('span', 'walk-group');
      if (group.subgoal) set.title = plainText(group.subgoal);
      for (let place = group.start; place < group.start + group.length; place++) {
        const dot = node('button', 'walk-dot'); dot.type = 'button';
        dot.setAttribute('aria-label', `Step ${place + 1}: ${plainText(steps[place].action)}`);
        dot.addEventListener('click', () => go(place));
        set.append(dot);
      }
      dots.append(set);
    }
    return dots;
  }

  // A long walkthrough: where the reader is, and a list to jump anywhere.
  const jump = node('button', 'walk-jump'); jump.type = 'button';
  jump.setAttribute('aria-haspopup', 'true'); jump.setAttribute('aria-expanded', 'false');
  const jumpCount = node('span', 'walk-jump-count'), jumpGroup = node('span', 'walk-jump-group');
  jump.append(jumpCount, jumpGroup, iconGlyph('updown'));
  const menu = node('div', 'walk-menu'); menu.hidden = true; menu.setAttribute('role', 'dialog'); menu.setAttribute('aria-label', 'Jump to a step');
  const list = node('ol', 'walk-menu-list'); menu.append(list);
  jump.addEventListener('click', () => (menu.hidden ? open() : close(true)));
  menu.addEventListener('keydown', event => {
    const items = [...menu.querySelectorAll('button')], at = items.indexOf(document.activeElement);
    if (event.key === 'Escape') { event.preventDefault(); close(true); }
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      items[Math.max(0, Math.min(items.length - 1, at + (event.key === 'ArrowDown' ? 1 : -1)))]?.focus();
    } else if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); items.at(event.key === 'Home' ? 0 : -1)?.focus(); }
  });
  const outside = event => { if (!menu.contains(event.target) && !jump.contains(event.target)) close(); };
  function fillMenu(steps) {
    list.replaceChildren();
    for (const group of groupsOf(steps)) {
      const entries = node('ol', 'walk-menu-steps');
      if (group.subgoal) {
        const heading = node('button', 'walk-menu-group'); heading.type = 'button';
        heading.append(studyText('span', '', group.subgoal), node('span', 'walk-menu-range', group.length > 1 ? `${group.start + 1}–${group.start + group.length}` : String(group.start + 1)));
        heading.addEventListener('click', () => { go(group.start); close(true); });
        list.append(append(node('li'), heading, entries));
      } else list.append(append(node('li'), entries));
      for (let place = group.start; place < group.start + group.length; place++) {
        const item = node('button', 'walk-menu-step'); item.type = 'button';
        item.append(node('span', 'walk-menu-number', String(place + 1)), studyText('span', '', steps[place].action));
        if (place === index) item.setAttribute('aria-current', 'step');
        item.addEventListener('click', () => { go(place); close(true); });
        entries.append(append(node('li'), item));
      }
    }
  }
  function open() {
    fillMenu(runs[run].steps);
    menu.hidden = false; jump.setAttribute('aria-expanded', 'true');
    document.addEventListener('pointerdown', outside, true);
    const current = menu.querySelector('[aria-current="step"]');
    current?.scrollIntoView({ block: 'nearest' });
    current?.focus({ preventScroll: true });
  }
  function close(refocus = false) {
    if (menu.hidden) return;
    menu.hidden = true; jump.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', outside, true);
    if (refocus) jump.focus({ preventScroll: true });
  }

  function go(place) { index = cycleIndex(place, runs[run].steps.length); update(); }
  let drawnRun = null, dots = null, long = false;
  function layout(steps) {
    long = steps.length > DOTS;
    controls.classList.toggle('long', long);
    dots = long ? null : drawDots(steps);
    position.replaceChildren(...(long ? [jump, menu] : [dots]));
    track.replaceChildren(...(long ? groupsOf(steps).map(group => {
      const part = node('span', 'walk-track-part'); part.style.flexGrow = group.length; part.dataset.start = group.start; part.dataset.length = group.length;
      return part;
    }) : []));
  }
  function update() {
    const steps = runs[run].steps, step = steps[all ? steps.length - 1 : index];
    if (drawnRun !== run) { layout(steps); drawnRun = run; }
    view?.show(step);
    if (long) {
      jumpCount.textContent = `Step ${index + 1} of ${steps.length}`;
      jumpGroup.replaceChildren(...(step.subgoal ? [studyText('span', '', step.subgoal)] : []));
      jump.setAttribute('aria-label', `Step ${index + 1} of ${steps.length}${step.subgoal ? `, ${plainText(step.subgoal)}` : ''}. Jump to a step`);
      for (const part of track.children) {
        const start = Number(part.dataset.start), length = Number(part.dataset.length);
        part.style.setProperty('--filled', String(Math.max(0, Math.min(1, (index + 1 - start) / length))));
        part.classList.toggle('current', index >= start && index < start + length);
      }
    } else {
      [...dots.querySelectorAll('.walk-dot')].forEach((dot, place) => {
        dot.classList.toggle('done', place < index);
        if (place === index) dot.setAttribute('aria-current', 'step'); else dot.removeAttribute('aria-current');
      });
    }
    card.hidden = all; pager.hidden = all; track.hidden = all;
    trace.replaceChildren(...(all ? [traceTable(steps)] : []));
    whole.textContent = all ? 'Step through' : 'All steps';
    whole.setAttribute('aria-pressed', String(all));
    prev.disabled = next.disabled = steps.length < 2;
    if (all) return;
    const content = [];
    // The jump control already says where the reader is; dots do not, so the card says it.
    if (!long) {
      const eyebrow = node('p', 'eyebrow walk-eyebrow', `Step ${index + 1} of ${steps.length}`);
      if (step.subgoal) eyebrow.append(' · ', studyText('span', '', step.subgoal));
      content.push(eyebrow);
    }
    content.push(studyText('p', 'walk-action', step.action), studyText('p', 'walk-why', step.why));
    card.replaceChildren(...content);
    if (step.note) card.append(append(node('p', 'walk-note'), node('strong', '', 'Pitfall: '), studyText('span', '', step.note)));
    if (parts !== null && index === parts && block.contrast) card.append(studyText('p', 'walk-contrast', block.contrast));
    card.append(stateRows(step, index ? steps[index - 1] : null));
  }
  update();
  return box;
}
