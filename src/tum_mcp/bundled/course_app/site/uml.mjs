import { node, svgNode, studyText } from './dom.mjs';

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
// Where the line from a box's centre towards (x, y) leaves the box.
function exit(box, x, y) {
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2, dx = x - cx, dy = y - cy;
  const scale = Math.min(Math.abs((box.w / 2) / (dx || 1e-9)), Math.abs((box.h / 2) / (dy || 1e-9)));
  return [cx + dx * scale, cy + dy * scale];
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

const relationStyle = {
  inheritance: { dashed: false, end: 'triangle' },
  realization: { dashed: true, end: 'triangle' },
  association: { dashed: false },
  directed_association: { dashed: false, end: 'open' },
  aggregation: { dashed: false, start: 'diamond' },
  composition: { dashed: false, start: 'filled-diamond' },
  dependency: { dashed: true, end: 'open' },
};

function classDiagram(block) {
  const boxes = new Map();
  for (const item of block.classes) {
    const stereotype = item.stereotype ? `\u00ab${item.stereotype}\u00bb` : '';
    const texts = [width(item.name, true), stereotype && width(stereotype), ...[...item.attributes, ...item.operations].map(member => width(member.text))];
    const w = Math.min(320, Math.max(120, Math.max(...texts.filter(Boolean)) + 2 * PAD));
    const header = (stereotype ? LINE : 0) + LINE + PAD;
    const section = members => (members.length ? members.length * LINE + PAD / 2 : PAD / 2) + PAD / 2;
    boxes.set(item.key, { item, stereotype, w, header, h: header + section(item.attributes) + section(item.operations), x: 0, y: 0 });
  }
  // Layers: parents above children, wholes above parts; other relations stay side by side.
  const level = new Map(block.classes.map(item => [item.key, 0]));
  for (let round = 0; round < block.classes.length; round++) {
    let changed = false;
    for (const relation of block.relations) {
      const [upper, lower] = ['inheritance', 'realization'].includes(relation.kind) ? [relation.end, relation.start]
        : ['aggregation', 'composition'].includes(relation.kind) ? [relation.start, relation.end] : [null, null];
      if (upper && upper !== lower && level.get(lower) < level.get(upper) + 1) { level.set(lower, level.get(upper) + 1); changed = true; }
    }
    if (!changed) break;
  }
  // Then usage: a client sits above what it uses, unless the hierarchy already orders them.
  const ordered = new Set(block.relations.filter(relation => !['association', 'directed_association', 'dependency'].includes(relation.kind)).flatMap(relation => [`${relation.start}|${relation.end}`, `${relation.end}|${relation.start}`]));
  for (let round = 0; round < block.classes.length; round++) {
    let changed = false;
    for (const relation of block.relations) {
      if (!['directed_association', 'dependency'].includes(relation.kind) || relation.start === relation.end || ordered.has(`${relation.start}|${relation.end}`)) continue;
      if (level.get(relation.end) < level.get(relation.start) + 1) { level.set(relation.end, level.get(relation.start) + 1); changed = true; }
    }
    if (!changed) break;
  }
  const rows = [];
  for (const item of block.classes) (rows[level.get(item.key)] ||= []).push(item.key);
  const rowList = rows.filter(Boolean);
  const neighbours = key => block.relations.flatMap(relation => relation.start === key ? [relation.end] : relation.end === key ? [relation.start] : []);
  const GAP_X = 48, GAP_Y = 72;
  const place = () => {
    let y = 24;
    for (const row of rowList) {
      const total = row.reduce((sum, key) => sum + boxes.get(key).w, 0) + GAP_X * (row.length - 1);
      let x = -total / 2;
      for (const key of row) { const box = boxes.get(key); box.x = x; box.y = y; x += box.w + GAP_X; }
      y += Math.max(...row.map(key => boxes.get(key).h)) + GAP_Y;
    }
  };
  place();
  for (let sweep = 0; sweep < 4; sweep++) {
    for (const row of rowList) {
      const centre = key => { const linked = neighbours(key).filter(other => !row.includes(other)).map(other => boxes.get(other)); return linked.length ? linked.reduce((sum, box) => sum + box.x + box.w / 2, 0) / linked.length : boxes.get(key).x; };
      row.sort((a, b) => centre(a) - centre(b));
    }
    place();
  }
  const all = [...boxes.values()];
  const left = Math.min(...all.map(box => box.x)) - 40, right = Math.max(...all.map(box => box.x + box.w)) + 40;
  const bottom = Math.max(...all.map(box => box.y + box.h)) + 24;
  const svg = svgNode('svg', { viewBox: `${left} 0 ${right - left} ${bottom}`, width: right - left, height: bottom, class: 'uml', role: 'img' });
  const notes = [];
  const pairKey = relation => [relation.start, relation.end].sort().join('|');
  const pairs = new Map();
  for (const relation of block.relations) pairs.set(pairKey(relation), [...(pairs.get(pairKey(relation)) || []), relation]);
  for (const relation of block.relations) {
    const a = boxes.get(relation.start), b = boxes.get(relation.end), style = relationStyle[relation.kind];
    if (a === b) continue;
    // Relations between the same two classes run side by side, not on one line.
    const siblings = pairs.get(pairKey(relation)), shift = (siblings.indexOf(relation) - (siblings.length - 1) / 2) * 22;
    const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
    const span = Math.hypot(bx - ax, by - ay) || 1, sx = -(by - ay) / span * shift * (relation.start < relation.end ? 1 : -1), sy = (bx - ax) / span * shift * (relation.start < relation.end ? 1 : -1);
    const [x1, y1] = exit({ ...a, x: a.x + sx, y: a.y + sy }, bx + sx, by + sy), [x2, y2] = exit({ ...b, x: b.x + sx, y: b.y + sy }, ax + sx, ay + sy);
    const length = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / length, uy = (y2 - y1) / length;
    const startInset = style.start ? 18 : 0, endInset = style.end === 'triangle' ? 14 : 0;
    svg.append(svgNode('line', { x1: x1 + ux * startInset, y1: y1 + uy * startInset, x2: x2 - ux * endInset, y2: y2 - uy * endInset, class: `uml-line${style.dashed ? ' dashed' : ''}`, 'data-relation': relation.kind }));
    if (style.end) head(svg, style.end, x2, y2, ux, uy);
    if (style.start) head(svg, style.start, x1, y1, -ux, -uy);
    // Labels go on the side away from parallel relations, so they never sit on a neighbour.
    // Each note tries its preferred side first, then the other side, then slides along the line,
    // and takes the first spot that touches no class and no earlier note.
    const side = shift ? Math.sign(-uy * sx + ux * sy) || 1 : 1;
    const note = (x, y, text) => {
      const w = width(text);
      let chosen = null;
      for (const s of [side, -side]) for (const d of [0, 12, -12, 24, -24]) {
        const px = -uy * s, py = ux * s;
        const cx = x + ux * d + px * 14 + (Math.abs(px) > 0.5 ? Math.sign(px) * w / 2 : 0), cy = y + uy * d + py * 14 + 4;
        const rect = { l: cx - w / 2 - 3, r: cx + w / 2 + 3, t: cy - 12, b: cy + 4 };
        const clear = [...notes, ...all.map(box => ({ l: box.x, r: box.x + box.w, t: box.y, b: box.y + box.h }))]
          .every(other => rect.r <= other.l || rect.l >= other.r || rect.b <= other.t || rect.t >= other.b);
        chosen ||= { cx, cy, rect };
        if (clear) { chosen = { cx, cy, rect }; break; }
      }
      notes.push(chosen.rect);
      svg.append(label(chosen.cx, chosen.cy, text, { className: 'uml-note' }));
    };
    if (relation.label) note((x1 + x2) / 2, (y1 + y2) / 2, relation.label);
    if (relation.start_multiplicity) note(x1 + ux * 28, y1 + uy * 28, relation.start_multiplicity);
    if (relation.end_multiplicity) note(x2 - ux * 28, y2 - uy * 28, relation.end_multiplicity);
  }
  for (const box of all) {
    const { item } = box, group = svgNode('g', { class: 'uml-class', 'data-class': item.key });
    group.append(svgNode('rect', { x: box.x, y: box.y, width: box.w, height: box.h, rx: 2 }));
    const cx = box.x + box.w / 2;
    let y = box.y + PAD + FONT - 1;
    if (box.stereotype) { group.append(label(cx, y, box.stereotype, { className: 'uml-note' })); y += LINE; }
    group.append(label(cx, y, item.name, { bold: true, italic: item.stereotype === 'abstract' }));
    let top = box.y + box.header;
    for (const members of [item.attributes, item.operations]) {
      group.append(svgNode('line', { x1: box.x, y1: top, x2: box.x + box.w, y2: top, class: 'uml-divider' }));
      members.forEach((member, index) => group.append(label(box.x + PAD, top + PAD / 2 + FONT + index * LINE, member.text, { anchor: 'start', italic: member.abstract, underline: member.static })));
      top += (members.length ? members.length * LINE + PAD / 2 : PAD / 2) + PAD / 2;
    }
    svg.append(group);
  }
  return svg;
}

function sequenceDiagram(block) {
  const ROW = 44, SELF = 58, TOP = 24, BOX_H = 36;
  const columns = new Map();
  let x = 24;
  for (const item of block.participants) {
    const w = Math.max(96, width(item.name, true) + 2 * PAD);
    columns.set(item.key, { item, w, x, centre: x + w / 2 });
    x += w + 56;
  }
  const right = x - 56 + 24;
  // A fragment's tab gets its own space above its first message.
  const heights = block.messages.map((message, index) => (message.start === message.end ? SELF : ROW) + 26 * block.fragments.filter(item => item.first === index).length);
  const opening = index => 26 * block.fragments.filter(item => item.first === index).length;
  const rowsTop = TOP + BOX_H + (block.participants.some(item => item.kind === 'actor') ? 24 : 0) + 28;
  const tops = heights.reduce((list, height, index) => [...list, index ? list[index - 1] + heights[index - 1] : rowsTop], []);
  const end = (tops.at(-1) ?? rowsTop) + (heights.at(-1) ?? 0) + 24;
  const svg = svgNode('svg', { viewBox: `0 0 ${right} ${end}`, width: right, height: end, class: 'uml', role: 'img' });
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
    if (fragment.condition) group.append(label(fx + tag + 8, fy + 13, `[${fragment.condition}]`, { anchor: 'start', className: 'uml-note' }));
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
      group.append(label(from + 40, y + 4, message.text, { anchor: 'start', className: 'uml-message-text' }));
    } else {
      const direction = Math.sign(to - from);
      group.append(svgNode('line', { x1: from, y1: y, x2: to - direction * (tip === 'filled' ? 10 : 0), y2: y, class: `uml-line${dashed ? ' dashed' : ''}` }));
      head(group, tip, to, y, direction, 0);
      group.append(label((from + to) / 2, y - 7, message.text, { className: 'uml-message-text' }));
    }
    svg.append(group);
  });
  return svg;
}

function stateDiagram(block) {
  const H = 40, ACT = 18, R = 9, ROW_GAP = 44;
  const shapes = new Map();
  for (const item of block.states) {
    if (item.kind !== 'state') { const size = item.kind === 'initial' ? 2 * R : 2 * R + 6; shapes.set(item.key, { item, w: size, h: size, x: 0, y: 0 }); continue; }
    const w = Math.max(96, width(item.name, true) + 2 * PAD + 8, item.activity ? width(item.activity) + 2 * PAD : 0);
    shapes.set(item.key, { item, w, h: H + (item.activity ? ACT + 4 : 0), x: 0, y: 0 });
  }
  // Columns by distance from the initial state, so the machine reads left to right.
  const first = block.states.find(item => item.kind === 'initial') || block.states[0];
  const column = new Map([[first.key, 0]]), queue = [first.key];
  while (queue.length) {
    const key = queue.shift();
    for (const item of block.transitions) if (item.start === key && !column.has(item.end)) { column.set(item.end, column.get(key) + 1); queue.push(item.end); }
  }
  const deepest = Math.max(...column.values());
  for (const item of block.states) if (!column.has(item.key)) column.set(item.key, item.kind === 'final' ? deepest + 1 : deepest);
  const columns = [];
  for (const item of block.states) (columns[column.get(item.key)] ||= []).push(item.key);
  const labels = block.transitions.map(item => item.label ? width(item.label) : 0);
  const gap = Math.min(220, Math.max(110, Math.max(0, ...labels) + 48));
  const loops = new Set(block.transitions.filter(item => item.start === item.end).map(item => item.start));
  let x = 24;
  const heights = columns.filter(Boolean).map(keys => keys.reduce((sum, key) => sum + shapes.get(key).h + (loops.has(key) ? 40 : 0), 0) + ROW_GAP * (keys.length - 1));
  const tallest = Math.max(...heights);
  for (const keys of columns.filter(Boolean)) {
    const w = Math.max(...keys.map(key => shapes.get(key).w));
    let y = 40 + (tallest - keys.reduce((sum, key) => sum + shapes.get(key).h + (loops.has(key) ? 40 : 0), 0) - ROW_GAP * (keys.length - 1)) / 2;
    for (const key of keys) {
      const shape = shapes.get(key); y += loops.has(key) ? 40 : 0;
      shape.x = x + (w - shape.w) / 2; shape.y = y; y += shape.h + ROW_GAP;
    }
    x += w + gap;
  }
  const right = x - gap + 24, bottom = 40 + tallest + 32;
  const svg = svgNode('svg', { viewBox: `0 0 ${right} ${bottom}`, width: right, height: bottom, class: 'uml', role: 'img' });
  const pair = new Set(block.transitions.map(item => `${item.start}|${item.end}`));
  block.transitions.forEach((item, index) => {
    const a = shapes.get(item.start), b = shapes.get(item.end), group = svgNode('g', { class: 'uml-transition' });
    if (a === b) {
      const cx = a.x + a.w / 2, top = a.y;
      group.append(svgNode('path', { d: `M${cx - 14},${top} C${cx - 30},${top - 44} ${cx + 30},${top - 44} ${cx + 14},${top}`, class: 'uml-line', fill: 'none' }));
      head(group, 'open', cx + 14, top, -0.35, 0.94);
      if (item.label) group.append(label(cx, top - 38, item.label, { className: 'uml-note uml-halo' }));
      svg.append(group); return;
    }
    const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
    const bend = pair.has(`${item.end}|${item.start}`) ? 18 : 0;
    const length = Math.hypot(bx - ax, by - ay) || 1, nx = -(by - ay) / length, ny = (bx - ax) / length;
    const mx = (ax + bx) / 2 + nx * bend * 2, my = (ay + by) / 2 + ny * bend * 2;
    const [x1, y1] = exit(a, mx, my), [x2, y2] = exit(b, mx, my);
    const tip = Math.hypot(x2 - mx, y2 - my) || 1;
    group.append(svgNode('path', { d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`, class: 'uml-line', fill: 'none', 'data-transition': String(index) }));
    head(group, 'open', x2, y2, (x2 - mx) / tip, (y2 - my) / tip);
    if (item.label) {
      const lx = (x1 + 2 * mx + x2) / 4 + nx * 12, ly = (y1 + 2 * my + y2) / 4 + ny * 12 + 4;
      group.append(label(lx, ly, item.label, { className: 'uml-note uml-halo' }));
    }
    svg.append(group);
  });
  for (const shape of shapes.values()) {
    const { item } = shape, group = svgNode('g', { class: `uml-state ${item.kind}`, 'data-state': item.key });
    const cx = shape.x + shape.w / 2, cy = shape.y + shape.h / 2;
    if (item.kind === 'initial') group.append(svgNode('circle', { cx, cy, r: R, class: 'uml-filled' }));
    else if (item.kind === 'final') group.append(svgNode('circle', { cx, cy, r: R + 3, class: 'uml-hollow' }), svgNode('circle', { cx, cy, r: R - 3, class: 'uml-filled' }));
    else {
      group.append(svgNode('rect', { x: shape.x, y: shape.y, width: shape.w, height: shape.h, rx: 12 }));
      group.append(label(cx, shape.y + H / 2 + 5, item.name, { bold: true }));
      if (item.activity) {
        group.append(svgNode('line', { x1: shape.x, y1: shape.y + H, x2: shape.x + shape.w, y2: shape.y + H, class: 'uml-divider' }));
        group.append(label(cx, shape.y + H + ACT - 2, item.activity, { className: 'uml-note' }));
      }
    }
    svg.append(group);
  }
  return svg;
}

export function renderUml(block) {
  const region = node('div', 'uml-region'); region.tabIndex = 0;
  region.setAttribute('role', 'region');
  region.setAttribute('aria-label', `UML ${block.diagram} diagram`);
  const svg = block.diagram === 'class' ? classDiagram(block) : block.diagram === 'state' ? stateDiagram(block) : sequenceDiagram(block);
  svg.setAttribute('aria-label', studyText('span', '', block.description).textContent);
  region.append(svg);
  return region;
}
