import { node, studyText, append, plainText, segmented } from '../shell/dom.mjs';
import { iconButton, arrowPaging, cycleIndex } from '../shell/navigation.mjs';
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
function stageView(stage, renderBody, steps) {
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
        reach.push(new Set([...(reach[index - 1] || []), ...(step.active || []), ...(step.frontier || []), ...(step.visited || [])]));
      }
      const show = step => {
        current = step;
        const shown = key => !step.visible_nodes || step.visible_nodes.includes(key);
        const reached = grows && reach[steps.indexOf(step)]?.size ? reach[steps.indexOf(step)] : null;
        for (const [key, group] of groups) {
          const active = step.active.includes(key);
          group.classList.toggle('active', active);
          group.classList.toggle('visited', !active && step.visited.includes(key));
          group.classList.toggle('frontier', !active && step.frontier.includes(key));
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
      return { element: append(node('div', 'graph-region'), graph), show };
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
// the card below says what is done and why. Dots group the steps by subgoal; "All steps"
// lists the whole trace. A variant replays a second run on the same stage, and the contrast
// appears at the step where the runs part.
export function renderWalkthrough(block, renderBody) {
  const box = node('div', 'walk');
  const runs = [{ label: block.label, steps: block.steps }, ...(block.variant ? [block.variant] : [])];
  const parts = runs.length > 1 ? divergence(runs[0].steps, runs[1].steps) : null;
  let run = 0, index = 0, all = false, view = null;
  const stage = node('div', 'walk-stage'), card = node('div', 'walk-card'), trace = node('div', 'walk-all');
  card.setAttribute('aria-live', 'polite');
  const prev = iconButton('Previous step', 'left', () => go(index - 1));
  const next = iconButton('Next step', 'right', () => go(index + 1));
  const dots = node('div', 'walk-dots');
  const whole = node('button', 'quiet walk-toggle', 'All steps');
  whole.type = 'button'; whole.setAttribute('aria-pressed', 'false');
  whole.addEventListener('click', () => { all = !all; update(); });
  const controls = append(node('div', 'diagram-controls walk-controls'), prev, dots, next, whole);
  if (block.stage) {
    view = stageView(block.stage, renderBody, runs.flatMap(item => item.steps));
    stage.append(view.element);
  } else stage.hidden = true;
  let choice = null;
  if (runs.length > 1) {
    choice = segmented('Run', runs.map((item, position) => ({ value: String(position), label: item.label })), value => {
      run = Number(value); index = Math.min(index, runs[run].steps.length - 1); update();
    }, { selected: '0' });
    box.append(choice.element);
  }
  box.append(stage, card, trace, controls);
  arrowPaging(box, prev, next);
  // Search opens the first step whose text holds every searched word.
  box.showMatch = words => {
    const text = step => [step.subgoal, step.action, step.why, step.note].filter(Boolean).join(' ').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    for (const [position, item] of runs.entries()) {
      const found = item.steps.findIndex(step => words.every(word => text(step).includes(word)));
      if (found < 0) continue;
      if (position !== run && choice) { choice.set(String(position)); run = position; }
      all = false; go(found); return true;
    }
    return false;
  };

  function go(position) { index = cycleIndex(position, runs[run].steps.length); update(); }
  function drawDots(steps) {
    dots.replaceChildren();
    let group = null;
    steps.forEach((step, position) => {
      if (!group || step.subgoal !== steps[position - 1].subgoal) {
        group = node('span', 'walk-group');
        if (step.subgoal) group.title = plainText(step.subgoal);
        dots.append(group);
      }
      const dot = node('button', 'walk-dot'); dot.type = 'button';
      dot.setAttribute('aria-label', `Step ${position + 1}: ${plainText(step.action)}`);
      dot.addEventListener('click', () => go(position));
      group.append(dot);
    });
  }
  let drawnRun = null;
  function update() {
    const steps = runs[run].steps, step = steps[all ? steps.length - 1 : index];
    if (drawnRun !== run) { drawDots(steps); drawnRun = run; }
    view?.show(step);
    [...dots.querySelectorAll('.walk-dot')].forEach((dot, position) => {
      dot.classList.toggle('done', position < index);
      if (position === index) dot.setAttribute('aria-current', 'step'); else dot.removeAttribute('aria-current');
    });
    card.hidden = all; dots.hidden = all; prev.hidden = all; next.hidden = all;
    trace.replaceChildren(...(all ? [traceTable(steps)] : []));
    whole.textContent = all ? 'Step through' : 'All steps';
    whole.setAttribute('aria-pressed', String(all));
    prev.disabled = next.disabled = steps.length < 2;
    if (all) return;
    const eyebrow = node('p', 'eyebrow walk-eyebrow', `Step ${index + 1} of ${steps.length}`);
    if (step.subgoal) eyebrow.append(' · ', studyText('span', '', step.subgoal));
    card.replaceChildren(eyebrow, studyText('p', 'walk-action', step.action), studyText('p', 'walk-why', step.why));
    if (step.note) card.append(append(node('p', 'walk-note'), node('strong', '', 'Pitfall: '), studyText('span', '', step.note)));
    if (parts !== null && index === parts && block.contrast) card.append(studyText('p', 'walk-contrast', block.contrast));
    card.append(stateRows(step, index ? steps[index - 1] : null));
  }
  update();
  return box;
}
