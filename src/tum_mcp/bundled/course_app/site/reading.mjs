import data from './data.mjs';
import { node, studyText, append, sourcesNote, svgNode } from './dom.mjs';
import { iconButton } from './navigation.mjs';
import { renderPlot } from './plot.mjs';
import { renderFormula } from './formulas.mjs';

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
export function diagram(block) {
  const box = node('div', 'surface diagram');
  // Crop unused canvas height so the drawing, not empty space, fills narrow screens.
  const reach = item => item.shape === 'box' ? 28 : 24;
  const top = Math.max(0, Math.min(...block.nodes.map(item => item.y - reach(item))) - 24);
  const bottom = Math.min(320, Math.max(...block.nodes.map(item => item.y + reach(item))) + 24);
  const graph = svgNode('svg', { viewBox: `0 ${top} 600 ${bottom - top}`, class: 'graph', role: 'img', 'aria-label': studyText('span', '', block.description).textContent });
  const nodes = new Map(block.nodes.map(item => [item.key, item]));
  function boundary(item, ux, uy) {
    return item.shape === 'box' ? Math.min(72 / (Math.abs(ux) || 1e-9), 30 / (Math.abs(uy) || 1e-9)) : 26;
  }
  for (const edge of block.edges) {
    const start = nodes.get(edge.start), end = nodes.get(edge.end);
    const dx = end.x - start.x, dy = end.y - start.y, distance = Math.hypot(dx, dy) || 1;
    const ux = dx / distance, uy = dy / distance;
    const a = boundary(start, ux, uy), b = boundary(end, ux, uy);
    const ex = end.x - b * ux, ey = end.y - b * uy;
    graph.append(svgNode('line', { x1: start.x + a * ux, y1: start.y + a * uy, x2: ex, y2: ey, 'data-edge-key': `${edge.start}--${edge.end}` }));
    if (edge.directed) {
      graph.append(svgNode('path', { d: `M${ex-10*ux+5*uy},${ey-10*uy-5*ux} L${ex},${ey} L${ex-10*ux-5*uy},${ey-10*uy+5*ux}`, class: 'arrow' }));
    }
    if (edge.label) {
      const label = svgNode('text', { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 - 12, class: 'edge-label' });
      label.textContent = edge.label; graph.append(label);
    }
  }
  const groups = new Map();
  for (const item of block.nodes) {
    const group = svgNode('g', { class: item.shape === 'box' ? 'node-box' : '', 'data-node-key': item.key });
    const label = svgNode('text', { x: item.x, y: item.y });
    if (item.shape === 'box' && item.label.length > 15) {
      label.setAttribute('y', item.y - 9);
      for (let offset = 0; offset < item.label.length; offset += 15) {
        const line = svgNode('tspan', { x: item.x, dy: offset ? 18 : 0 }); line.textContent = item.label.slice(offset, offset + 15); label.append(line);
      }
    } else label.textContent = item.label;
    group.append(item.shape === 'box' ? svgNode('rect', { x: item.x - 70, y: item.y - 28, width: 140, height: 56, rx: 6 }) : svgNode('circle', { cx: item.x, cy: item.y, r: 24 }), label);
    groups.set(item.key, group); graph.append(group);
  }
  const description = studyText('p', 'small', block.description);
  const state = node('div', 'diagram-state'); state.setAttribute('aria-live', 'polite');
  const caption = node('p'), frontier = node('p', 'small'); state.append(caption, frontier);
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
    caption.replaceChildren(...studyText('span', '', frame.caption).childNodes);
    frontier.hidden = block.state_labels === 'caption' || (block.frames.length === 1 && !frame.frontier.length && !frame.visited.length);
    frontier.textContent = `Frontier: ${frame.frontier.map(key => nodes.get(key).label).join(', ') || 'empty'} · Seen: ${frame.visited.map(key => nodes.get(key).label).join(', ') || 'none'}`;
    counter.textContent = `${index + 1} / ${block.frames.length}`;
    prev.disabled = index === 0; next.disabled = index === block.frames.length - 1;
  }
  const region = node('div', 'graph-region');
  region.append(graph);
  update(); controls.hidden = block.frames.length < 2; box.append(description, region, state, controls);
  return box;
}
export function renderReading(unit) {
  const root = node('div');
  for (const [index, block] of unit.blocks.entries()) {
    const section = node('section', 'read-section'); section.dataset.blockIndex = String(index);
    const material = node('div', 'reading-material'); material.dataset.commentTarget = 'content'; material.append(append(node('div', 'section-heading'), studyText('h2', '', block.title), sourcesNote(block.sources, data.sources, data.course.synthetic, block.title)));
    material.append(renderBlockBody(block));
    section.append(material); root.append(section);
  }
  return root;
}

export function renderBlockBody(block) {
  const root = node('div', 'block-body');
    switch (block.kind) {
      case 'text':
        for (const text of block.paragraphs) root.append(studyText('p', '', text));
        if (block.points.length) root.append(append(node('ul'), ...block.points.map(text => studyText('li', '', text))));
        break;
      case 'formula': root.append(renderFormula(block)); break;
      case 'table': root.append(table(block)); break;
      case 'diagram': root.append(diagram(block)); break;
      case 'plot': root.append(renderPlot(block).root); break;
      case 'code': {
        const region = node('div', 'code-region'); region.tabIndex = 0;
        region.setAttribute('role', 'region'); region.setAttribute('aria-label', `${block.language} code`);
        region.append(node('span', 'small', block.language), append(node('pre'), node('code', '', block.code)));
        root.append(region, studyText('p', '', block.explanation)); break;
      }
      default: throw new Error('Unsupported study block. Rebuild the site with a compatible renderer.');
    }
  return root;
}
