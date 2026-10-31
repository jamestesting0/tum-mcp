import data from './data.mjs';
import { node, studyText, append, sourcesNote, plainText } from './dom.mjs';
import { iconButton } from './navigation.mjs';
import { renderPlot } from './plot.mjs';
import { renderCode, languageName, lineSet, markLines } from './code.mjs';
import { renderFiles, fileIcon } from './files.mjs';
import { renderFormula } from './formulas.mjs';
import { renderDerivation } from './derivation.mjs';
import { renderUml } from './uml.mjs';
import { drawGraph } from './graph.mjs';
import { videoPanel } from './video.mjs';

// A step or point that opens with a short label ("Initialize: ...") shows the label in bold,
// so a procedure reads as named stages and an example as named sub-results.
function labelledItem(text) {
  const label = /^([A-Z][^:`\\{}()]{0,30}):\s+(?=\S)/.exec(text);
  const item = studyText('li', '', label ? text.slice(label[0].length) : text);
  if (label) item.prepend(node('strong', 'item-label', `${label[1]}:`), ' ');
  return item;
}

function table(block) {
  const region = node('div', 'table-region');
  region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', plainText(block.caption));
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
export function diagram(block) {
  const box = node('div', 'surface diagram');
  const nodes = new Map(block.nodes.map(item => [item.key, item]));
  const { graph, groups } = drawGraph(block, plainText(block.description));
  const description = studyText('p', 'small', block.description);
  const state = node('div', 'diagram-state'); state.setAttribute('aria-live', 'polite');
  const caption = node('p'), frontier = node('p', 'small'), rows = node('dl', 'frame-state');
  state.append(caption, rows, frontier);
  const lines = [...graph.querySelectorAll('[data-edge-key], [data-arrow-key]')];
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
    for (const line of lines) line.classList.toggle('active', marked.has(line.dataset.edgeKey || line.dataset.arrowKey));
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

// The heading element for a titled block: level 1 sits one below the enclosing heading.
export const headingTag = (block, depth = 1) => `h${Math.min(6, (block.level || 1) + depth)}`;
const continues = block => block.kind === 'definition' || !block.title;

// A titled block opens a section at its level. A term or an untitled block continues the
// section above, under that heading and its citation; one that opens the passage shares an
// untitled section. `depth` shifts every level under an enclosing heading, such as a step's.
export function renderReading(unit, { depth = 1, withVideo = true } = {}) {
  const root = node('div');
  const video = withVideo ? videoPanel(unit) : null;
  if (video) root.append(video);
  let material = null;
  for (const [index, block] of unit.blocks.entries()) {
    if (material && continues(block)) {
      if (block.kind === 'definition') {
        const last = material.lastElementChild;
        const list = last?.matches('dl.definitions') ? last : material.appendChild(node('dl', 'definitions'));
        const item = definitionItem(block); item.dataset.blockIndex = String(index);
        if (block.key) item.dataset.block = block.key;
        list.append(item);
      } else {
        const body = renderBlockBody(block); body.dataset.blockIndex = String(index);
        if (block.key) body.dataset.block = block.key;
        material.append(body);
      }
      continue;
    }
    const section = node('section', 'read-section'); section.dataset.blockIndex = String(index);
    section.dataset.level = String(block.title ? block.level || 1 : 1);
    if (block.key) section.dataset.block = block.key;
    material = node('div', 'reading-material'); material.dataset.commentTarget = 'content';
    // The section cites everything it holds, so untitled blocks below share its citation.
    const members = [block];
    for (const next of unit.blocks.slice(index + 1)) { if (!continues(next)) break; members.push(next); }
    const cited = [...new Set(members.flatMap(item => item.kind === 'definition' && item !== block ? [] : item.sources))];
    if (block.kind !== 'definition') {
      const heading = append(node('div', `section-heading${block.title ? '' : ' untitled'}`));
      if (block.title) heading.append(studyText(headingTag(block, depth), '', block.title));
      heading.append(sourcesNote(cited, data.sources, data.course.synthetic, block.title || unit.title || '', {}, block.pages));
      material.append(heading);
    }
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
    svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', plainText(block.alt));
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
    const image = node('img'); image.src = block.image; image.alt = plainText(block.alt); image.loading = 'lazy';
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
  const tree = append(node('ul', 'tree'), branch(block.root)); tree.setAttribute('aria-label', plainText(block.title || 'Tree'));
  if (block.description) figure.append(studyText('figcaption', 'small', block.description));
  figure.append(tree);
  return figure;
}

// The direct answers of a solution, one labelled answer per original part, then any notes.
export function renderAnswers(solution, target = element => element, answerIndex = null) {
  const root = node('div', 'solution-answers');
  solution.answers.forEach((answer, index) => {
    if (answerIndex !== null && index !== answerIndex) return;
    const item = node('section', 'solution-answer');
    if (answerIndex === null && answer.label) item.append(studyText('h3', 'solution-label', answer.label));
    item.append(target(append(node('div', 'reading-material'), ...answer.blocks.map(block => renderBlockBody(block))), `solution:${index}`));
    root.append(item);
  });
  if (answerIndex === null && solution.notes?.length) {
    const notes = renderReading({ blocks: solution.notes }, { depth: 2 });
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
        if (block.steps?.length) root.append(append(node('ol', 'steps'), ...block.steps.map(labelledItem)));
        if (block.points.length) root.append(append(node('ul'), ...block.points.map(labelledItem)));
        break;
      case 'definition': root.append(append(node('dl', 'definitions'), definitionItem(block, term))); break;
      case 'formula': root.append(renderFormula(block)); break;
      case 'derivation': root.append(renderDerivation(block, visual => renderBlockBody(visual))); break;
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
