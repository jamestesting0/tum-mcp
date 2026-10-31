import { node, svgNode, studyText, plainText } from './dom.mjs';
import { drawUml } from './uml-layout.mjs';

// UML class, sequence and state diagrams, laid out from their structure so authors never place
// coordinates. Shapes follow UML 2 notation; colours come from the theme.
const FONT = 13, LINE = 18, PAD = 12;
let measurer;
function width(text, bold = false) {
  measurer ||= document.createElement('canvas').getContext('2d');
  measurer.font = `${bold ? 650 : 400} ${FONT}px ${getComputedStyle(document.documentElement).getPropertyValue('--font-ui') || 'sans-serif'}`;
  return measurer.measureText(text).width;
}
function label(x, y, text, { anchor = 'middle', className = '', italic = false, underline = false, bold = false } = {}) {
  const element = svgNode('text', { x, y, 'text-anchor': anchor, class: className });
  if (italic) element.setAttribute('font-style', 'italic');
  if (underline) element.setAttribute('text-decoration', 'underline');
  if (bold) element.setAttribute('font-weight', '650');
  element.textContent = text;
  return element;
}
// A head at (x, y) pointing along unit vector (ux, uy).
function head(svg, kind, x, y, ux, uy) {
  const px = -uy, py = ux;
  const at = (along, across) => `${x - ux * along + px * across},${y - uy * along + py * across}`;
  if (kind === 'triangle') svg.append(svgNode('path', { d: `M${x},${y} L${at(14, 8)} L${at(14, -8)} Z`, class: 'uml-hollow' }));
  else if (kind === 'diamond' || kind === 'filled-diamond') svg.append(svgNode('path', { d: `M${x},${y} L${at(9, 6)} L${at(18, 0)} L${at(9, -6)} Z`, class: kind === 'diamond' ? 'uml-hollow' : 'uml-filled' }));
  else if (kind === 'open') svg.append(svgNode('path', { d: `M${at(11, 6)} L${x},${y} L${at(11, -6)}`, class: 'uml-open' }));
  else if (kind === 'filled') svg.append(svgNode('path', { d: `M${x},${y} L${at(11, 5)} L${at(11, -5)} Z`, class: 'uml-filled' }));
}


function sequenceDiagram(block) {
  const ROW = 44, SELF = 58, TOP = 24, BOX_H = 36;
  // Lifelines stand far enough apart for every message label between them, so no label
  // crosses a lifeline; a self-call's label needs room to the right of its own lifeline.
  const order = block.participants.map(item => item.key), at = new Map(order.map((key, index) => [key, index]));
  const widths = block.participants.map(item => Math.max(96, width(item.name, true) + 2 * PAD));
  const gaps = widths.slice(1).map((w, i) => (widths[i] + w) / 2 + 40);
  for (const message of block.messages) {
    const i = at.get(message.start), j = at.get(message.end), need = width(message.text) + 28;
    if (i === j) { if (i < gaps.length) gaps[i] = Math.max(gaps[i], need + 44); continue; }
    const [lo, hi] = [Math.min(i, j), Math.max(i, j)], span = gaps.slice(lo, hi).reduce((sum, g) => sum + g, 0);
    if (span < need) for (let k = lo; k < hi; k++) gaps[k] += (need - span) / (hi - lo);
  }
  const columns = new Map();
  let centre = 24 + widths[0] / 2;
  block.participants.forEach((item, index) => {
    if (index) centre += gaps[index - 1];
    columns.set(item.key, { item, w: widths[index], x: centre - widths[index] / 2, centre });
  });
  const lastSelf = block.messages.filter(m => m.start === m.end && at.get(m.start) === order.length - 1).map(m => width(m.text) + 52);
  const right = centre + Math.max(widths.at(-1) / 2, ...lastSelf) + 24;
  // A fragment's tab gets its own space above its first message.
  const heights = block.messages.map((message, index) => (message.start === message.end ? SELF : ROW) + 26 * block.fragments.filter(item => item.first === index).length);
  const opening = index => 26 * block.fragments.filter(item => item.first === index).length;
  const rowsTop = TOP + BOX_H + (block.participants.some(item => item.kind === 'actor') ? 24 : 0) + 28;
  const tops = heights.reduce((list, height, index) => [...list, index ? list[index - 1] + heights[index - 1] : rowsTop], []);
  const end = (tops.at(-1) ?? rowsTop) + (heights.at(-1) ?? 0) + 24;
  const svg = svgNode('svg', { viewBox: `0 0 ${right} ${end}`, width: right, height: end, class: 'uml', role: 'img' });
  svg.style.minWidth = `${Math.ceil(right * 12 / 13)}px`;
  // Fragments first, so lines and labels stay on top.
  block.fragments.forEach((fragment, index) => {
    const involved = block.messages.slice(fragment.first, fragment.last + 1).flatMap(message => [message.start, message.end]).map(key => columns.get(key).centre);
    const inset = 8 * (block.fragments.filter((other, at) => at < index && other.first <= fragment.first && other.last >= fragment.last).length);
    const fx = Math.min(...involved) - 40 + inset, fw = Math.max(...involved) - Math.min(...involved) + 80 + (block.messages.slice(fragment.first, fragment.last + 1).some(m => m.start === m.end) ? 40 : 0) - 2 * inset;
    const fy = tops[fragment.first] + 4 + inset, fh = tops[fragment.last] + heights[fragment.last] - fy - 4 - inset;
    const group = svgNode('g', { class: 'uml-fragment', 'data-fragment': fragment.kind });
    group.append(svgNode('rect', { x: fx, y: fy, width: fw, height: fh }));
    const tag = width(fragment.kind, true) + 16;
    group.append(svgNode('path', { d: `M${fx},${fy} h${tag} v10 l-6,8 h${-(tag - 6)} Z`, class: 'uml-tag' }));
    group.append(label(fx + 6, fy + 13, fragment.kind, { anchor: 'start', bold: true, className: 'uml-note' }));
    if (fragment.condition) group.append(label(fx + tag + 8, fy + 13, `[${fragment.condition}]`, { anchor: 'start', className: 'uml-note uml-halo' }));
    svg.append(group);
  });
  for (const column of columns.values()) {
    const group = svgNode('g', { class: 'uml-participant', 'data-participant': column.item.key });
    let lifeTop = TOP + BOX_H;
    if (column.item.kind === 'actor') {
      const cx = column.centre, y = TOP;
      group.append(svgNode('circle', { cx, cy: y + 6, r: 6 }), svgNode('path', { d: `M${cx},${y + 12} v14 M${cx - 10},${y + 17} h20 M${cx},${y + 26} l-8,10 M${cx},${y + 26} l8,10`, class: 'uml-open' }));
      group.append(label(cx, y + 52, column.item.name, { bold: true }));
      lifeTop = y + 58;
    } else {
      group.append(svgNode('rect', { x: column.x, y: TOP, width: column.w, height: BOX_H, rx: 2 }));
      group.append(label(column.centre, TOP + BOX_H / 2 + 5, column.item.name, { bold: true, underline: column.item.name.includes(':') }));
    }
    group.append(svgNode('line', { x1: column.centre, y1: lifeTop, x2: column.centre, y2: end - 12, class: 'uml-line dashed' }));
    svg.append(group);
  }
  block.messages.forEach((message, index) => {
    const from = columns.get(message.start).centre, to = columns.get(message.end).centre, y = tops[index] + opening(index) + 22;
    const dashed = message.kind === 'return' || message.kind === 'create';
    const tip = message.kind === 'call' ? 'filled' : 'open';
    const group = svgNode('g', { class: 'uml-message', 'data-message': message.kind });
    if (from === to) {
      group.append(svgNode('path', { d: `M${from},${y} h34 v20 h-34`, class: `uml-line${dashed ? ' dashed' : ''}`, fill: 'none' }));
      head(group, tip, from, y + 20, -1, 0);
      group.append(label(from + 40, y + 4, message.text, { anchor: 'start', className: 'uml-message-text uml-halo' }));
    } else {
      const direction = Math.sign(to - from);
      group.append(svgNode('line', { x1: from, y1: y, x2: to - direction * (tip === 'filled' ? 10 : 0), y2: y, class: `uml-line${dashed ? ' dashed' : ''}` }));
      head(group, tip, to, y, direction, 0);
      group.append(label((from + to) / 2, y - 7, message.text, { className: 'uml-message-text uml-halo' }));
    }
    svg.append(group);
  });
  return svg;
}

// Sequence diagrams are drawn here; class, state and flowchart layouts come from ELK, which
// loads on first use, so the region reserves room and fills in when the layout is ready.
export function renderUml(block) {
  const region = node('div', 'uml-region'); region.tabIndex = 0;
  region.setAttribute('role', 'region');
  region.setAttribute('aria-label', block.diagram === 'flowchart' ? 'Flowchart' : `UML ${block.diagram} diagram`);
  const name = plainText(block.description);
  if (block.diagram === 'sequence') {
    const svg = sequenceDiagram(block); svg.setAttribute('aria-label', name); region.append(svg);
    return region;
  }
  region.classList.add('uml-pending');
  region.dataset.layout = 'pending';
  // The room inside the region once it is on the page; a layout wider than that is redone tighter.
  const room = () => {
    if (!region.isConnected) return Infinity;
    const style = getComputedStyle(region);
    return region.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  };
  drawUml(block, room).then(svg => {
    svg.setAttribute('aria-label', name); region.replaceChildren(svg); region.dataset.layout = 'done';
    requestAnimationFrame(() => { region.scrollLeft = (region.scrollWidth - region.clientWidth) / 2; });
  })
    .catch(error => { region.replaceChildren(node('p', 'small', `${name} (${error.message})`)); region.dataset.layout = 'failed'; })
    .finally(() => region.classList.remove('uml-pending'));
  return region;
}
