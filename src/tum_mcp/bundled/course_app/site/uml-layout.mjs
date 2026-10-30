// Class diagrams, state machines and flowcharts laid out by ELK (the Eclipse Layout Kernel,
// vendored as elk.bundled.js and loaded only when a page shows one of these diagrams) and
// drawn here in the app's theme. Authors give structure only; the order they list classes,
// states and steps in is the order the layout keeps.
import { svgNode } from './dom.mjs';

const FONT = 14, SMALL = 13, LINE = 19, PAD = 10;
let measurer = null, loading = null;

function width(text, size = FONT, weight = 400) {
  measurer ||= document.createElement('canvas').getContext('2d');
  measurer.font = `${weight} ${size}px ${getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim() || 'sans-serif'}`;
  return measurer.measureText(text).width || text.length * size * 0.56;
}
function text(x, y, value, { anchor = 'middle', className = '', italic = false, underline = false, bold = false } = {}) {
  const element = svgNode('text', { x, y, 'text-anchor': anchor, 'dominant-baseline': 'central', class: className });
  if (italic) element.setAttribute('font-style', 'italic');
  if (underline) element.setAttribute('text-decoration', 'underline');
  if (bold) element.setAttribute('font-weight', '650');
  element.textContent = value;
  return element;
}
// Text wraps at word boundaries to stay inside `limit` pixels, in lines of even length.
function wrap(value, limit, size = FONT) {
  const words = value.split(/\s+/);
  const greedy = within => {
    const lines = [];
    for (const word of words) {
      const last = lines.at(-1);
      if (last !== undefined && width(`${last} ${word}`, size) <= within) lines[lines.length - 1] = `${last} ${word}`;
      else lines.push(word);
    }
    return lines;
  };
  const count = greedy(limit).length;
  let low = Math.max(...words.map(word => width(word, size))), high = Math.max(low, limit);
  while (count > 1 && high - low > 2) { const mid = (low + high) / 2; if (greedy(mid).length > count) low = mid; else high = mid; }
  return greedy(high);
}

function loadElk() {
  if (globalThis.ELK) return Promise.resolve(globalThis.ELK);
  loading ||= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = new URL('./elk.bundled.js', import.meta.url).href;
    script.onload = () => resolve(globalThis.ELK);
    script.onerror = () => reject(new Error('The diagram layout engine did not load.'));
    document.head.append(script);
  });
  return loading;
}

const BASE = {
  'elk.algorithm': 'layered',
  'elk.direction': 'DOWN',
  'elk.layered.cycleBreaking.strategy': 'MODEL_ORDER',
  'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
  'elk.layered.thoroughness': '10',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
  'elk.layered.nodePlacement.favorStraightEdges': 'true',
  'elk.layered.edgeRouting.selfLoopDistribution': 'EQUALLY',
  'elk.spacing.nodeNode': '40',
  'elk.layered.spacing.nodeNodeBetweenLayers': '56',
  'elk.spacing.edgeNode': '20',
  'elk.layered.spacing.edgeNodeBetweenLayers': '20',
  'elk.spacing.edgeEdge': '14',
  'elk.layered.spacing.edgeEdgeBetweenLayers': '14',
  'elk.spacing.edgeLabel': '6',
  'elk.spacing.nodeSelfLoop': '24',
  'elk.padding': '[top=12,left=12,bottom=12,right=12]',
};
const FAMILY = {
  class: { 'elk.edgeRouting': 'ORTHOGONAL' },
  state: { 'elk.edgeRouting': 'SPLINES', 'elk.layered.edgeRouting.splines.mode': 'CONSERVATIVE' },
  flowchart: { 'elk.edgeRouting': 'SPLINES', 'elk.layered.edgeRouting.splines.mode': 'CONSERVATIVE', 'elk.layered.spacing.nodeNodeBetweenLayers': '48' },
};

function labelOf(id, value, placement, inline) {
  const layoutOptions = { 'elk.edgeLabels.placement': placement };
  if (inline) layoutOptions['elk.edgeLabels.inline'] = 'true';
  return { id, text: value, width: Math.ceil(width(value, SMALL)) + (inline ? 10 : 6), height: 18, layoutOptions };
}

// ---------------------------------------------------------------- shapes per diagram kind
function classNode(item) {
  const stereotype = item.stereotype ? `\u00ab${item.stereotype}\u00bb` : '';
  const widest = Math.max(width(item.name, FONT, 650), stereotype ? width(stereotype, SMALL) : 0, ...[...item.attributes, ...item.operations].map(member => width(member.text, SMALL)));
  const header = (stereotype ? LINE : 0) + LINE + PAD;
  const section = members => Math.max(1, members.length) * LINE - (members.length ? 0 : LINE - 8) + PAD;
  return { id: item.key, item, kind: 'class', width: Math.ceil(Math.max(120, widest + 2 * PAD + 4)), height: header + section(item.attributes) + section(item.operations), header };
}
function stateNode(item) {
  if (item.kind === 'initial') return { id: item.key, item, kind: 'initial', width: 18, height: 18 };
  if (item.kind === 'final') return { id: item.key, item, kind: 'final', width: 24, height: 24 };
  const w = Math.max(96, width(item.name, FONT, 650) + 32, item.activity ? width(item.activity, SMALL) + 28 : 0);
  return { id: item.key, item, kind: 'state', width: Math.ceil(w), height: item.activity ? 62 : 40 };
}
// A tight layout (phones, or a drawing that would overflow its column) wraps text narrower and
// packs closer before it ever needs to scroll.
function stepNode(item, tight) {
  const limit = tight ? (item.kind === 'decision' ? 96 : 150) : (item.kind === 'decision' ? 150 : 210), lines = wrap(item.text, limit), widest = Math.max(...lines.map(line => width(line)));
  if (item.kind === 'decision') {
    // A diamond holds its question when it is about 1.7 times as wide as the text.
    const w = Math.max(132, widest * 1.7 + 28), h = Math.max(76, w * 0.42, lines.length * LINE * 1.8 + 28);
    return { id: item.key, item, kind: 'decision', lines, width: Math.ceil(w), height: Math.ceil(h) };
  }
  const h = lines.length * LINE + 26;
  return { id: item.key, item, kind: item.kind === 'start' || item.kind === 'end' ? 'terminal' : item.kind, lines, width: Math.ceil(Math.max(item.kind === 'start' || item.kind === 'end' ? 88 : 110, widest + 36)), height: h };
}

const RELATION = {
  inheritance: { tail: 'triangle', flip: true },
  realization: { tail: 'triangle', flip: true, dashed: true },
  association: {},
  directed_association: { head: 'open' },
  aggregation: { tail: 'diamond' },
  composition: { tail: 'filled-diamond' },
  dependency: { head: 'open', dashed: true },
};

function model(block, tight) {
  if (block.diagram === 'class') {
    const nodes = block.classes.map(classNode);
    // Subclasses hang from one shared port under their parent, so their arrows join into one trunk.
    const parents = new Set(block.relations.filter(r => RELATION[r.kind].flip).map(r => r.end));
    for (const n of nodes) if (parents.has(n.id)) n.ports = [{ id: `${n.id}:gen`, width: 1, height: 1, layoutOptions: { 'elk.port.side': 'SOUTH' } }];
    const order = new Map(block.classes.map((item, index) => [item.key, index]));
    const edges = block.relations.map((r, index) => {
      const style = RELATION[r.kind], id = `r${index}`;
      // Generalizations run parent → child so the parent sits above; other relations run start → end.
      const [from, to] = style.flip ? [r.end, r.start] : [r.start, r.end];
      const labels = [];
      // A whole-part relation names the part's role, which UML writes at the part's end.
      if (r.label) labels.push(r.kind === 'aggregation' || r.kind === 'composition' ? labelOf(`${id}:r`, r.label, 'HEAD', false) : labelOf(`${id}:c`, r.label, 'CENTER', false));
      if (r.end_multiplicity) labels.push(labelOf(`${id}:${style.flip ? 't' : 'h'}`, r.end_multiplicity, style.flip ? 'TAIL' : 'HEAD', false));
      if (r.start_multiplicity) labels.push(labelOf(`${id}:${style.flip ? 'h' : 't'}`, r.start_multiplicity, style.flip ? 'HEAD' : 'TAIL', false));
      // A relation from a class listed later runs up into its target. When the target is a
      // supertype, whose sides are fixed for its trunk, it enters from below beside the trunk.
      const target = nodes.find(n => n.id === to);
      let port = to;
      if (!style.flip && target.ports && order.get(from) > order.get(to)) {
        port = `${to}:${id}`;
        target.ports.push({ id: port, width: 1, height: 1, layoutOptions: { 'elk.port.side': 'SOUTH' } });
      }
      return { id, from: style.flip ? `${from}:gen` : from, fromNode: from, to: port, toNode: to, style, labels, priority: style.flip };
    });
    return { nodes, edges };
  }
  if (block.diagram === 'state') {
    return {
      nodes: block.states.map(stateNode),
      edges: block.transitions.map((t, index) => ({ id: `t${index}`, from: t.start, fromNode: t.start, to: t.end, toNode: t.end, style: { head: 'open' }, labels: t.label ? [labelOf(`t${index}:c`, t.label, 'CENTER', true)] : [] })),
    };
  }
  return {
    nodes: block.steps.map(item => stepNode(item, tight)),
    edges: block.flows.map((f, index) => ({ id: `f${index}`, from: f.start, fromNode: f.start, to: f.end, toNode: f.end, style: { head: 'filled' }, labels: f.label ? [labelOf(`f${index}:c`, f.label, 'CENTER', true)] : [] })),
  };
}

// ---------------------------------------------------------------- drawing
const smooth = points => {
  // ELK splines: start point, then cubic control points in threes.
  const [first, ...rest] = points;
  if (rest.length % 3) return null;
  let d = `M${first}`;
  for (let i = 0; i < rest.length; i += 3) d += ` C${rest[i]} ${rest[i + 1]} ${rest[i + 2]}`;
  return d;
};
function rounded(points) {
  let d = `M${points[0]}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i - 1], [x, y] = points[i], [nx, ny] = points[i + 1];
    const r = Math.min(6, Math.hypot(x - px, y - py) / 2, Math.hypot(nx - x, ny - y) / 2);
    d += ` L${x - Math.sign(x - px) * r},${y - Math.sign(y - py) * r} Q${x},${y} ${x + Math.sign(nx - x) * r},${y + Math.sign(ny - y) * r}`;
  }
  return `${d} L${points.at(-1)}`;
}
function dropCollinear(points) {
  return points.filter((p, i) => i === 0 || i === points.length - 1 || !((points[i - 1][0] === p[0] && p[0] === points[i + 1][0]) || (points[i - 1][1] === p[1] && p[1] === points[i + 1][1])));
}
function head(kind, [x, y], [fx, fy]) {
  const dx = x - fx, dy = y - fy, length = Math.hypot(dx, dy) || 1, ux = dx / length, uy = dy / length, px = -uy, py = ux;
  const at = (along, across) => `${x - ux * along + px * across},${y - uy * along + py * across}`;
  if (kind === 'triangle') return svgNode('path', { d: `M${x},${y} L${at(14, 8)} L${at(14, -8)} Z`, class: 'uml-hollow' });
  if (kind === 'diamond' || kind === 'filled-diamond') return svgNode('path', { d: `M${x},${y} L${at(9, 6)} L${at(18, 0)} L${at(9, -6)} Z`, class: kind === 'diamond' ? 'uml-hollow' : 'uml-filled' });
  if (kind === 'open') return svgNode('path', { d: `M${at(11, 6)} L${x},${y} L${at(11, -6)}`, class: 'uml-open' });
  if (kind === 'filled') return svgNode('path', { d: `M${x},${y} L${at(10, 5)} L${at(10, -5)} Z`, class: 'uml-filled' });
  return null;
}

function drawNode(n) {
  const { x, y, width: w, height: h, item } = n, cx = x + w / 2, cy = y + h / 2;
  const family = ['initial', 'final', 'state'].includes(n.kind) ? 'uml-state ' : ['decision', 'terminal', 'io', 'action'].includes(n.kind) ? 'uml-step ' : '';
  const group = svgNode('g', { class: `${family}uml-${n.kind}`, 'data-node': n.id });
  switch (n.kind) {
    case 'class': {
      group.append(svgNode('rect', { x, y, width: w, height: h, rx: 2 }));
      let line = y + PAD / 2 + LINE / 2 + 1;
      if (item.stereotype) { group.append(text(cx, line, `\u00ab${item.stereotype}\u00bb`, { className: 'uml-note' })); line += LINE; }
      group.append(text(cx, line, item.name, { bold: true, italic: item.stereotype === 'abstract' }));
      let top = y + n.header;
      for (const members of [item.attributes, item.operations]) {
        group.append(svgNode('line', { x1: x, y1: top, x2: x + w, y2: top, class: 'uml-divider' }));
        members.forEach((member, index) => group.append(text(x + PAD, top + PAD / 2 + LINE / 2 + index * LINE + 1, member.text, { anchor: 'start', className: 'uml-member', italic: member.abstract, underline: member.static })));
        top += Math.max(1, members.length) * LINE - (members.length ? 0 : LINE - 8) + PAD;
      }
      break;
    }
    case 'initial': group.append(svgNode('circle', { cx, cy, r: 9, class: 'uml-filled' })); break;
    case 'final': group.append(svgNode('circle', { cx, cy, r: 12, class: 'uml-hollow' }), svgNode('circle', { cx, cy, r: 7, class: 'uml-filled' })); break;
    case 'state': {
      group.append(svgNode('rect', { x, y, width: w, height: h, rx: 12 }));
      if (item.activity) {
        group.append(text(cx, y + 20, item.name, { bold: true }), svgNode('line', { x1: x, y1: y + 40, x2: x + w, y2: y + 40, class: 'uml-divider' }), text(cx, y + 51, item.activity, { className: 'uml-member' }));
      } else group.append(text(cx, cy, item.name, { bold: true }));
      break;
    }
    case 'decision':
      group.append(svgNode('path', { d: `M${cx},${y} L${x + w},${cy} L${cx},${y + h} L${x},${cy} Z` }));
      break;
    case 'terminal': group.append(svgNode('rect', { x, y, width: w, height: h, rx: h / 2 })); break;
    case 'io': group.append(svgNode('path', { d: `M${x + 12},${y} L${x + w},${y} L${x + w - 12},${y + h} L${x},${y + h} Z` })); break;
    default: group.append(svgNode('rect', { x, y, width: w, height: h, rx: 4 }));
  }
  if (n.lines) n.lines.forEach((line, index) => group.append(text(cx, cy + (index - (n.lines.length - 1) / 2) * LINE, line)));
  return group;
}

async function run(ELK, block, nodes, edges, loose, tight) {
  // Boxes joined by a straight association need room for its label between them.
  const room = Math.max(40, ...edges.filter(e => loose.has(e.id)).flatMap(e => e.labels.map(l => l.width + 36)));
  const graph = {
    id: 'root',
    layoutOptions: { ...BASE, ...FAMILY[block.diagram], ...(tight ? { 'elk.spacing.nodeNode': '24', 'elk.layered.spacing.nodeNodeBetweenLayers': '40' } : {}), ...(loose.size ? { 'elk.spacing.nodeNode': String(room) } : {}) },
    children: nodes.map(n => ({ id: n.id, width: n.width, height: n.height, ...(n.ports ? { ports: n.ports, layoutOptions: { 'elk.portConstraints': 'FIXED_SIDE' } } : {}) })),
    edges: edges.map(e => ({ id: e.id, sources: [e.from], targets: [e.to], labels: loose.has(e.id) ? [] : e.labels,
      layoutOptions: { ...(e.priority ? { 'elk.layered.priority.direction': '10', 'elk.layered.priority.shortness': '10' } : {}), ...(loose.has(e.id) ? { 'elk.noLayout': 'true' } : {}) } })),
  };
  return new ELK().layout(graph);
}

// Two subclasses of one parent that also know each other belong side by side, as UML
// textbooks draw them; a layered layout would stack them. Try leaving such relations out of
// the layout and drawing them straight between the two boxes; keep that only if it works.
function siblingRelations(block, edges) {
  if (block.diagram !== 'class') return new Set();
  const parentsOf = new Map();
  for (const r of block.relations) if (RELATION[r.kind].flip) (parentsOf.get(r.start) || parentsOf.set(r.start, new Set()).get(r.start)).add(r.end);
  return new Set(edges.filter((e, index) => {
    const r = block.relations[index];
    return !RELATION[r.kind].flip && [...(parentsOf.get(r.start) || [])].some(p => parentsOf.get(r.end)?.has(p));
  }).map(e => e.id));
}
function besideEachOther(result, edges, loose) {
  const box = new Map(result.children.map(c => [c.id, c]));
  const routes = new Map();
  for (const e of edges.filter(item => loose.has(item.id))) {
    const a = box.get(e.fromNode), b = box.get(e.toNode);
    const top = Math.max(a.y, b.y), bottom = Math.min(a.y + a.height, b.y + b.height);
    if (bottom - top < 24) return null;
    const [left, right] = a.x < b.x ? [a, b] : [b, a];
    if (result.children.some(c => c !== left && c !== right && c.x > left.x + left.width - 1 && c.x + c.width < right.x + 1 && c.y < bottom && c.y + c.height > top)) return null;
    const y = (top + bottom) / 2, start = a === left ? [a.x + a.width, y] : [a.x, y], end = b === left ? [b.x + b.width, y] : [b.x, y];
    routes.set(e.id, { start, end });
  }
  return routes;
}

// ELK attaches edges to a node's bounding box; a decision's edges continue to its diamond.
function onOutline(n, [px, py]) {
  if (n?.kind !== 'decision') return [px, py];
  const cx = n.x + n.width / 2, cy = n.y + n.height / 2, hw = n.width / 2, hh = n.height / 2;
  if (Math.abs(py - n.y) < 1 || Math.abs(py - n.y - n.height) < 1) return [px, cy + Math.sign(py - cy) * hh * Math.max(0, 1 - Math.abs(px - cx) / hw)];
  return [cx + Math.sign(px - cx) * hw * Math.max(0, 1 - Math.abs(py - cy) / hh), py];
}

export async function layoutUml(block, room = () => Infinity) {
  const ELK = await loadElk();
  const narrow = (globalThis.innerWidth || 1280) < 600, laid = await layoutWith(ELK, block, narrow);
  return narrow || laid.width <= room() ? laid : layoutWith(ELK, block, true);
}

async function layoutWith(ELK, block, tight) {
  const { nodes, edges } = model(block, tight);
  const loose = siblingRelations(block, edges);
  let result = await run(ELK, block, nodes, edges, new Set(), tight), straight = null;
  if (loose.size) {
    const second = await run(ELK, block, nodes, edges, loose, tight);
    straight = besideEachOther(second, edges, loose);
    if (straight) result = second;
  }
  const placed = new Map(result.children.map(c => [c.id, c]));
  for (const n of nodes) Object.assign(n, { x: placed.get(n.id).x, y: placed.get(n.id).y });
  for (const e of edges) {
    const out = result.edges.find(item => item.id === e.id);
    if (straight?.has(e.id)) {
      const { start, end } = straight.get(e.id), mid = [(start[0] + end[0]) / 2, start[1]];
      e.points = [start, end];
      e.placed = e.labels.map(l => l.id.endsWith(':c') ? { ...l, x: mid[0] - l.width / 2, y: start[1] - l.height - 4, inline: false }
        : { ...l, x: (l.id.endsWith(':h') ? end[0] - Math.sign(end[0] - start[0]) * (l.width / 2 + 12) : start[0] + Math.sign(end[0] - start[0]) * (l.width / 2 + 12)) - l.width / 2, y: start[1] + 4, inline: false });
      continue;
    }
    e.points = (out.sections || []).flatMap((s, i) => [...(i ? [] : [[s.startPoint.x, s.startPoint.y]]), ...(s.bendPoints || []).map(b => [b.x, b.y]), [s.endPoint.x, s.endPoint.y]]);
    e.placed = (out.labels || []).map(l => ({ ...l, inline: l.id.endsWith(':c') && block.diagram !== 'class' }));
    if (e.points.length > 1) {
      e.points[0] = onOutline(nodes.find(n => n.id === e.fromNode), e.points[0]);
      e.points[e.points.length - 1] = onOutline(nodes.find(n => n.id === e.toNode), e.points.at(-1));
    }
  }
  return { nodes, edges, width: result.width, height: result.height };
}

export async function drawUml(block, room) {
  const laid = await layoutUml(block, room);
  const svg = svgNode('svg', { viewBox: `0 0 ${laid.width} ${laid.height}`, width: Math.round(laid.width), height: Math.round(laid.height), class: 'uml', 'data-diagram': block.diagram, role: 'img' });
  // It may shrink to fit the column while its 13 px text stays at 12 px or more; beyond that it scrolls.
  svg.style.minWidth = `${Math.ceil(laid.width * 12 / 13)}px`;
  const lines = svgNode('g'), shapes = svgNode('g'), labels = svgNode('g');
  for (const e of laid.edges) {
    if (e.points.length < 2) continue;
    const group = svgNode('g', { class: `uml-edge ${{ class: 'uml-relation', state: 'uml-transition', flowchart: 'uml-flow' }[block.diagram]}`, 'data-edge': e.id });
    const curved = block.diagram !== 'class' && smooth(e.points);
    const points = curved ? e.points : dropCollinear(e.points);
    group.append(svgNode('path', { d: curved || rounded(points), class: `uml-line${e.style.dashed ? ' dashed' : ''}` }));
    // An arrowhead points along the last stretch of its line; a spline's last control point can
    // sit on the end itself, so the direction comes from the nearest point that differs.
    const apart = tip => point => Math.hypot(point[0] - tip[0], point[1] - tip[1]) > 1;
    const end = points.at(-1), start = points[0];
    const beforeEnd = points.slice(0, -1).findLast(apart(end)) || start, afterStart = points.slice(1).find(apart(start)) || end;
    for (const [kind, tip, from] of [[e.style.head, end, beforeEnd], [e.style.tail, start, afterStart]]) {
      const shape = kind && head(kind, tip, from);
      if (shape) group.append(shape);
    }
    lines.append(group);
    for (const l of e.placed) {
      if (l.inline) labels.append(svgNode('rect', { x: l.x, y: l.y, width: l.width, height: l.height, rx: 3, class: 'uml-knockout' }));
      labels.append(text(l.x + l.width / 2, l.y + l.height / 2, l.text, { className: 'uml-note' }));
    }
  }
  for (const n of laid.nodes) shapes.append(drawNode(n));
  svg.append(lines, shapes, labels);
  return svg;
}
