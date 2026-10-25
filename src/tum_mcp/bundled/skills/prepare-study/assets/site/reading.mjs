import data from './data.mjs';
import { node, button, append, sourcesNote } from './dom.mjs';

function formula(block) {
  const box = node('div', 'surface');
  const expression = node('div', 'equation');
  expression.tabIndex = 0; expression.setAttribute('role', 'region');
  expression.setAttribute('aria-label', `Equation: ${block.plain}`);
  const parsed = new DOMParser().parseFromString(block.mathml, 'application/xml');
  const allowed = new Set('math mrow mi mn mo mtext mfrac msqrt mroot msub msup msubsup mtable mtr mtd munder mover munderover mmultiscripts mprescripts none mspace mstyle'.split(' '));
  const attrs = new Set(['display', 'mathvariant', 'displaystyle', 'stretchy', 'linethickness']);
  const valid = !parsed.querySelector('parsererror') && [...parsed.querySelectorAll('*')].every(element =>
    element.namespaceURI === 'http://www.w3.org/1998/Math/MathML' && allowed.has(element.localName) &&
    [...element.attributes].every(attr => attrs.has(attr.name) || attr.name === 'xmlns'));
  if (valid) expression.append(document.importNode(parsed.documentElement, true));
  else expression.append(node('p', '', block.plain));
  box.append(expression, node('p', '', block.plain));
  const glossary = node('dl', 'symbols');
  for (const symbol of block.symbols) glossary.append(node('dt', '', symbol.symbol), node('dd', '', symbol.meaning));
  box.append(glossary, node('p', 'small', block.conditions));
  return box;
}
function table(block) {
  const region = node('div', 'table-region');
  region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', block.caption);
  const grid = node('table'); grid.append(node('caption', '', block.caption));
  const headings = node('tr');
  for (const label of block.columns) { const th = node('th', '', label); th.scope = 'col'; headings.append(th); }
  grid.append(append(node('thead'), headings));
  const body = node('tbody');
  for (const cells of block.rows) {
    const row = node('tr');
    cells.forEach((text, index) => { const cell = node(index ? 'td' : 'th', '', text); if (!index) cell.scope = 'row'; row.append(cell); });
    body.append(row);
  }
  region.append(append(grid, body));
  return region;
}
function svgNode(tag, attributes) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
  return element;
}
function diagram(block) {
  const box = node('div', 'surface diagram');
  const graph = svgNode('svg', { viewBox: '0 0 600 320', class: 'graph', role: 'img', 'aria-label': block.description });
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
    graph.append(svgNode('line', { x1: start.x + a * ux, y1: start.y + a * uy, x2: ex, y2: ey }));
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
    const group = svgNode('g', { class: item.shape === 'box' ? 'node-box' : '' });
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
  const description = node('p', 'small', block.description);
  const state = node('div', 'diagram-state'); state.setAttribute('aria-live', 'polite');
  const caption = node('p'), frontier = node('p', 'small'); state.append(caption, frontier);
  let index = 0;
  const prev = button('Previous step', () => { index--; update(); });
  const next = button('Next step', () => { index++; update(); });
  const counter = node('span', 'small');
  const controls = append(node('div', 'diagram-controls'), prev, counter, next);
  function update() {
    const frame = block.frames[index];
    for (const [key, group] of groups) {
      group.classList.toggle('active', frame.active.includes(key)); group.classList.toggle('visited', frame.visited.includes(key) && !frame.active.includes(key));
    }
    caption.textContent = frame.caption;
    frontier.hidden = block.state_labels === 'caption' || (block.frames.length === 1 && !frame.frontier.length && !frame.visited.length);
    frontier.textContent = `Frontier: ${frame.frontier.map(key => nodes.get(key).label).join(', ') || 'empty'} · Seen: ${frame.visited.map(key => nodes.get(key).label).join(', ') || 'none'}`;
    counter.textContent = `${index + 1} / ${block.frames.length}`;
    prev.disabled = index === 0; next.disabled = index === block.frames.length - 1;
  }
  const region = node('div', 'graph-region'); region.tabIndex = 0;
  region.setAttribute('role', 'region'); region.setAttribute('aria-label', block.title);
  region.append(graph);
  update(); controls.hidden = block.frames.length < 2; box.append(description, region, state, controls);
  return box;
}
export function renderReading(unit) {
  const root = node('div');
  for (const block of unit.blocks) {
    const section = node('section', 'read-section'); section.append(node('h2', '', block.title));
    switch (block.kind) {
      case 'text':
        for (const text of block.paragraphs) section.append(node('p', '', text));
        if (block.points.length) section.append(append(node('ul'), ...block.points.map(text => node('li', '', text))));
        break;
      case 'formula': section.append(formula(block)); break;
      case 'table': section.append(table(block)); break;
      case 'diagram': section.append(diagram(block)); break;
      case 'code': {
        const region = node('div', 'code-region'); region.tabIndex = 0;
        region.setAttribute('role', 'region'); region.setAttribute('aria-label', `${block.language} example`);
        region.append(node('span', 'small', block.language), append(node('pre'), node('code', '', block.code)));
        section.append(region, node('p', '', block.explanation)); break;
      }
      default: throw new Error('Unsupported study block. Rebuild the site with a compatible renderer.');
    }
    section.append(sourcesNote(block.sources, data.sources, data.course.synthetic)); root.append(section);
  }
  return root;
}
