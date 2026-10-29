import data from './data.mjs';
import { node, studyText, append, sourcesNote, svgNode } from './dom.mjs';
import { iconButton } from './navigation.mjs';
import { renderPlot } from './plot.mjs';
import { renderCode, languageName, lineSet, markLines } from './code.mjs';
import { renderFiles, fileIcon } from './files.mjs';
import { renderFormula } from './formulas.mjs';
import { renderUml } from './uml.mjs';
import { videoPanel } from './video.mjs';

function table(block) {
  const region = node('div', 'table-region');
  region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', studyText('span', '', block.caption).textContent);
  const grid = node('table'); grid.append(studyText('caption', '', block.caption));
  const headings = node('tr');
  for (const label of block.columns) { const th = studyText('th', '', label); th.scope = 'col'; headings.append(th); }
  grid.append(append(node('thead'), headings));
  const body = node('tbody');
  for (const cells of block.rows) {
    const row = node('tr');
    cells.forEach((text, index) => { const cell = studyText(index ? 'td' : 'th', '', text); if (!index) cell.scope = 'row'; row.append(cell); });
    body.append(row);
  }
  region.append(append(grid, body));
  return region;
}
// Box labels wrap at word boundaries into at most two lines of about fifteen characters.
function labelLines(text) {
  const lines = [];
  for (const word of text.split(/\s+/)) {
    const current = lines.at(-1);
    if (current !== undefined && current.length + word.length < 15) lines[lines.length - 1] = `${current} ${word}`;
    else lines.push(word);
  }
  return lines.length <= 2 && lines.every(line => line.length <= 15) ? lines : [text.slice(0, 15), text.slice(15)];
}
const RADIUS = 26;
export function diagram(block) {
  const box = node('div', 'surface diagram');
  // Crop unused canvas height so the drawing, not empty space, fills narrow screens.
  const reach = item => item.shape === 'box' ? 28 : RADIUS;
  const nodes = new Map(block.nodes.map(item => [item.key, item]));
  function boundary(item, ux, uy) {
    return item.shape === 'box' ? Math.min(72 / (Math.abs(ux) || 1e-9), 30 / (Math.abs(uy) || 1e-9)) : RADIUS;
  }
  const strokes = [], labels = [];
  for (const edge of block.edges) {
    const start = nodes.get(edge.start), end = nodes.get(edge.end);
    const dx = end.x - start.x, dy = end.y - start.y, distance = Math.hypot(dx, dy) || 1;
    const ux = dx / distance, uy = dy / distance;
    const a = boundary(start, ux, uy), b = boundary(end, ux, uy);
    const ex = end.x - b * ux, ey = end.y - b * uy;
    strokes.push(svgNode('line', { x1: start.x + a * ux, y1: start.y + a * uy, x2: ex, y2: ey, 'data-edge-key': `${edge.start}--${edge.end}` }));
    if (edge.directed) {
      strokes.push(svgNode('path', { d: `M${ex-10*ux+5*uy},${ey-10*uy-5*ux} L${ex},${ey} L${ex-10*ux-5*uy},${ey-10*uy+5*ux}`, class: 'arrow' }));
    }
    if (edge.label) {
      // Beside the line on its upper side; a label wider than the gap between the two shapes
      // moves clear of them, so no node ever covers it.
      const [nx, ny] = ux > 0 ? [uy, -ux] : [-uy, ux];
      const fits = edge.label.length * 7.5 + 8 <= distance - a - b;
      const offset = fits ? 14 : Math.max(reach(start), reach(end)) + 12;
      labels.push({ text: edge.label, x: (start.x + end.x) / 2 + offset * nx, y: (start.y + end.y) / 2 + offset * ny });
    }
  }
  // Crop unused canvas height so the drawing, not empty space, fills narrow screens.
  const top = Math.max(0, Math.min(...block.nodes.map(item => item.y - reach(item)), ...labels.map(item => item.y - 12)) - 24);
  const bottom = Math.min(320, Math.max(...block.nodes.map(item => item.y + reach(item)), ...labels.map(item => item.y + 6)) + 24);
  const graph = svgNode('svg', { viewBox: `0 ${top} 600 ${bottom - top}`, class: 'graph', role: 'img', 'aria-label': studyText('span', '', block.description).textContent });
  graph.append(...strokes);
  const groups = new Map();
  for (const item of block.nodes) {
    const group = svgNode('g', { class: item.shape === 'box' ? 'node-box' : 'node-circle', 'data-node-key': item.key });
    const label = svgNode('text', { x: item.x, y: item.y });
    const lines = item.shape === 'box' && item.label.length > 15 ? labelLines(item.label) : [item.label];
    if (lines.length > 1) {
      label.setAttribute('y', item.y - 9);
      lines.forEach((text, index) => {
        const line = svgNode('tspan', { x: item.x, dy: index ? 18 : 0 }); line.textContent = text; label.append(line);
      });
    } else label.textContent = item.label;
    group.append(item.shape === 'box' ? svgNode('rect', { x: item.x - 70, y: item.y - 28, width: 140, height: 56, rx: 6 }) : svgNode('circle', { cx: item.x, cy: item.y, r: RADIUS }), label);
    groups.set(item.key, group); graph.append(group);
  }
  for (const item of labels) {
    const label = svgNode('text', { x: item.x, y: item.y, class: 'edge-label' }); label.textContent = item.text; graph.append(label);
  }
  const description = studyText('p', 'small', block.description);
  const state = node('div', 'diagram-state'); state.setAttribute('aria-live', 'polite');
  const caption = node('p'), frontier = node('p', 'small'), rows = node('dl', 'frame-state');
  state.append(caption, rows, frontier);
  const lines = [...graph.querySelectorAll('line[data-edge-key]')];
  let index = 0;
  const prev = iconButton('Previous step', 'left', () => { index--; update(); });
  const next = iconButton('Next step', 'right', () => { index++; update(); });
  const counter = node('span', 'small');
  const controls = append(node('div', 'diagram-controls'), prev, counter, next);
  function update() {
    const frame = block.frames[index];
    for (const [key, group] of groups) {
      group.classList.toggle('active', frame.active.includes(key)); group.classList.toggle('visited', frame.visited.includes(key) && !frame.active.includes(key));
    }
    const marked = new Set((frame.edges || []).flatMap(edge => [`${edge.start}--${edge.end}`, `${edge.end}--${edge.start}`]));
    for (const line of lines) line.classList.toggle('active', marked.has(line.dataset.edgeKey));
    caption.replaceChildren(...studyText('span', '', frame.caption).childNodes);
    // The algorithm's own state (a queue, the domains) at this step; what changed since the last step is marked.
    const before = new Map((block.frames[index - 1]?.state || []).map(row => [row.label, row.value]));
    rows.replaceChildren(...(frame.state || []).flatMap(row => {
      const changed = index > 0 && before.get(row.label) !== row.value, value = studyText('dd', changed ? 'changed' : '', row.value);
      if (changed) value.append(node('span', 'visually-hidden', ' (changed)'));
      return [studyText('dt', '', row.label), value];
    }));
    rows.hidden = !frame.state?.length;
    frontier.hidden = Boolean(frame.state?.length) || block.state_labels === 'caption' || (block.frames.length === 1 && !frame.frontier.length && !frame.visited.length);
    frontier.textContent = `Frontier: ${frame.frontier.map(key => nodes.get(key).label).join(', ') || 'empty'} · Seen: ${frame.visited.map(key => nodes.get(key).label).join(', ') || 'none'}`;
    counter.textContent = `${index + 1} / ${block.frames.length}`;
    prev.disabled = index === 0; next.disabled = index === block.frames.length - 1;
  }
  const region = node('div', 'graph-region');
  region.append(graph);
  update(); controls.hidden = block.frames.length < 2; box.append(description, region, state, controls);
  // A single picture says it once: its caption is visible, its description stays the image's name.
  if (block.frames.length < 2) { box.classList.add('static'); description.hidden = true; }
  return box;
}
// A listing, optionally walked through: each stop marks its lines and says what they do.
function codeBlock(block) {
  const steps = block.walkthrough || [];
  const region = node('div', 'code-region'); region.tabIndex = 0;
  region.setAttribute('role', 'region'); region.setAttribute('aria-label', `${languageName(block.language) || 'Code'} listing`);
  const pre = renderCode(block.code, block.language, { numbers: block.line_numbers || steps.length > 0 });
  // A one-word label is a language name such as "java"; a longer one is kept as written.
  region.append(node('span', 'small code-language', /\s/.test(block.language) ? block.language : languageName(block.language)), pre);
  if (!steps.length) return region;
  let at = 0;
  const counter = node('span', 'small code-walk-count'), note = node('p', 'code-walk-note'); note.setAttribute('aria-live', 'polite');
  const prev = iconButton('Previous stop', 'left', () => show(at - 1)), next = iconButton('Next stop', 'right', () => show(at + 1));
  function show(index) {
    at = index; const step = steps[at];
    markLines(pre, lineSet(step.lines));
    const [first, last = first] = step.lines.split('-');
    counter.textContent = `${at + 1} / ${steps.length} · ${first === last ? `line ${first}` : `lines ${first}–${last}`}`;
    note.replaceChildren(studyText('span', '', step.note));
    prev.disabled = at === 0; next.disabled = at === steps.length - 1;
    const marked = pre.querySelector('.code-line.marked');
    if (marked && region.scrollHeight > region.clientHeight) region.scrollTop = Math.max(0, marked.offsetTop - region.clientHeight / 3);
  }
  show(0);
  return append(node('div', 'code-walkthrough'), region, append(node('div', 'code-walk'), append(node('div', 'code-walk-controls'), prev, counter, next), note));
}

export function renderReading(unit) {
  const root = node('div');
  const video = videoPanel(unit);
  if (video) root.append(video);
  let material = null;
  for (const [index, block] of unit.blocks.entries()) {
    // A term joins the passage it belongs to, under that passage's heading and citation;
    // terms that open the lesson share one untitled section.
    if (block.kind === 'definition' && material) {
      const last = material.lastElementChild;
      const list = last?.matches('dl.definitions') ? last : material.appendChild(node('dl', 'definitions'));
      const item = definitionItem(block); item.dataset.blockIndex = String(index);
      if (block.key) item.dataset.block = block.key;
      list.append(item); continue;
    }
    const section = node('section', 'read-section'); section.dataset.blockIndex = String(index);
    if (block.key) section.dataset.block = block.key;
    material = node('div', 'reading-material'); material.dataset.commentTarget = 'content';
    if (block.kind !== 'definition') material.append(append(node('div', 'section-heading'), studyText('h2', '', block.title), sourcesNote(block.sources, data.sources, data.course.synthetic, block.title, {}, block.pages)));
    material.append(block.kind === 'definition' ? append(node('dl', 'definitions'), definitionItem(block)) : renderBlockBody(block));
    section.append(material); root.append(section);
  }
  return root;
}

function definitionItem(block, term = true) {
  const item = node('div', 'definition-item');
  if (term) item.append(studyText('dt', '', block.term));
  const meaning = append(studyText('dd', '', block.statement));
  if (block.conditions?.length) meaning.append(append(node('ul'), ...block.conditions.map(text => studyText('li', '', text))));
  item.append(meaning);
  return item;
}

// A picture of the idea itself: an allowlisted SVG drawing, checked at build, or an image
// from the app's figures folder. Marker ids get a per-figure prefix so arrowheads never collide.
let figures = 0;
function figureBlock(block) {
  const figure = node('figure', 'figure');
  if (block.svg) {
    const markup = block.svg.includes('xmlns=') ? block.svg : block.svg.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
    const svg = document.importNode(new DOMParser().parseFromString(markup, 'image/svg+xml').documentElement, true);
    const prefix = `figure-${++figures}-`;
    for (const element of svg.querySelectorAll('[id]')) element.id = prefix + element.id;
    for (const element of svg.querySelectorAll('[marker-start], [marker-end]')) {
      for (const name of ['marker-start', 'marker-end']) {
        const value = element.getAttribute(name);
        if (value) element.setAttribute(name, value.replace('url(#', `url(#${prefix}`));
      }
    }
    svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', studyText('span', '', block.alt).textContent);
    // Never wider than drawn, so a 16-unit label reads as 16 px text and only shrinks on narrow screens.
    svg.style.maxWidth = `${svg.viewBox.baseVal.width}px`;
    figure.append(svg);
    // Crop to what is drawn, once it is on screen, so unused canvas never leaves empty space.
    const crop = new ResizeObserver(() => {
      const box = svg.getBBox();
      if (!box.width || !box.height) return;
      svg.setAttribute('viewBox', `${box.x - 12} ${box.y - 12} ${box.width + 24} ${box.height + 24}`);
      svg.style.maxWidth = `${box.width + 24}px`;
      crop.disconnect();
    });
    crop.observe(svg);
  } else {
    const image = node('img'); image.src = block.image; image.alt = studyText('span', '', block.alt).textContent; image.loading = 'lazy';
    figure.append(image);
  }
  if (block.caption) figure.append(studyText('figcaption', 'small', block.caption));
  return figure;
}

// A hierarchy as an indented tree with connector lines; a note, such as a size, ends its row.
function treeBlock(block) {
  const figure = node('figure', 'tree-view');
  const branch = item => {
    const row = append(node('span', 'tree-row'), ...(item.kind === 'item' ? [] : [fileIcon(item.kind)]), studyText('span', 'tree-label', item.label));
    if (item.note) row.append(studyText('span', 'tree-note', item.note));
    const entry = append(node('li'), row);
    if (item.children.length) entry.append(append(node('ul'), ...item.children.map(branch)));
    return entry;
  };
  const tree = append(node('ul', 'tree'), branch(block.root)); tree.setAttribute('aria-label', studyText('span', '', block.title).textContent);
  if (block.description) figure.append(studyText('figcaption', 'small', block.description));
  figure.append(tree);
  return figure;
}

// The direct answers of a solution, one labelled answer per original part, then any notes.
export function renderAnswers(solution, target = element => element) {
  const root = node('div', 'solution-answers');
  solution.answers.forEach((answer, index) => {
    const item = node('section', 'solution-answer');
    if (answer.label) item.append(studyText('h3', 'solution-label', answer.label));
    item.append(target(append(node('div', 'reading-material'), ...answer.blocks.map(block => renderBlockBody(block))), `solution:${index}`));
    root.append(item);
  });
  if (solution.notes?.length) {
    const notes = renderReading({ blocks: solution.notes });
    [...notes.querySelectorAll('.reading-material')].forEach((element, index) => target(element, `solution-note:${index}`));
    root.append(notes);
  }
  return root;
}

export function renderBlockBody(block, { term = true } = {}) {
  const root = node('div', 'block-body');
    switch (block.kind) {
      case 'text':
        for (const text of block.paragraphs) root.append(studyText('p', '', text));
        if (block.steps?.length) root.append(append(node('ol', 'steps'), ...block.steps.map(text => studyText('li', '', text))));
        if (block.points.length) root.append(append(node('ul'), ...block.points.map(text => studyText('li', '', text))));
        break;
      case 'definition': root.append(append(node('dl', 'definitions'), definitionItem(block, term))); break;
      case 'formula': root.append(renderFormula(block)); break;
      case 'table': root.append(table(block)); break;
      case 'diagram': root.append(diagram(block)); break;
      case 'uml': root.append(renderUml(block)); break;
      case 'plot': root.append(renderPlot(block).root); break;
      case 'code': root.append(codeBlock(block), studyText('p', '', block.explanation)); break;
      case 'files': root.append(renderFiles(block)); break;
      case 'tree': root.append(treeBlock(block)); break;
      case 'figure': root.append(figureBlock(block)); break;
      default: throw new Error('Unsupported study block. Rebuild the site with a compatible renderer.');
    }
  return root;
}
