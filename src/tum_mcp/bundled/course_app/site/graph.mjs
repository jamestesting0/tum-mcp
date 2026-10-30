// Geometry for `diagram` blocks. The author places each node in a lattice cell (row, col); this
// module sizes nodes from their labels, spaces rows and columns from their widest member, bends
// edges around nodes, separates two-way pairs, draws self-loops, and places every edge label
// where it touches no node, line or other label. The drawing is cropped to what it shows.
import { svgNode } from './dom.mjs';

export const SIZES = { circle: 18, box: 16, label: 14 };
const LINE = 20, PAD = 12;
// Spacing steps tried from roomy to tight until the drawing fits the reading column.
const STEPS = [{ gap: 56, wrap: 176 }, { gap: 44, wrap: 150 }, { gap: 32, wrap: 128 }, { gap: 22, wrap: 108 }];
let context = null;

export function textWidth(text, size) {
  context ||= document.createElement('canvas').getContext('2d');
  const family = getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim() || 'sans-serif';
  context.font = `500 ${size}px ${family}`;
  return context.measureText(text).width || text.length * size * 0.56;
}

// A box label wraps at word boundaries into at most two lines.
function wrap(text, size, limit = 176) {
  if (textWidth(text, size) <= limit) return [text];
  const words = text.split(/\s+/);
  let best = [text];
  for (let cut = 1; cut < words.length; cut++) {
    const lines = [words.slice(0, cut).join(' '), words.slice(cut).join(' ')];
    const widest = Math.max(...lines.map(line => textWidth(line, size)));
    if (best.length === 1 || widest < Math.max(...best.map(line => textWidth(line, size)))) best = lines;
  }
  return best;
}

function measure(item, limit) {
  if (item.shape === 'box') {
    const lines = wrap(item.label, SIZES.box, limit), widest = Math.max(...lines.map(line => textWidth(line, SIZES.box)));
    return { lines, w: Math.max(96, Math.ceil(widest) + 32), h: lines.length > 1 ? 64 : 44 };
  }
  const r = Math.max(24, Math.ceil(textWidth(item.label, SIZES.circle) / 2) + 12);
  return { lines: [item.label], w: 2 * r, h: 2 * r, r };
}

const centre = n => [n.x, n.y];
function rim(n, toward) {
  const dx = toward[0] - n.x, dy = toward[1] - n.y, length = Math.hypot(dx, dy) || 1, ux = dx / length, uy = dy / length;
  const t = n.r ?? Math.min(n.w / 2 / (Math.abs(ux) || 1e-9), n.h / 2 / (Math.abs(uy) || 1e-9));
  return [n.x + ux * (t + 1), n.y + uy * (t + 1)];
}
const quad = (a, c, b, t) => [(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]];
const cubic = (a, c1, c2, b, t) => [0, 1].map(i => (1 - t) ** 3 * a[i] + 3 * (1 - t) ** 2 * t * c1[i] + 3 * (1 - t) * t * t * c2[i] + t ** 3 * b[i]);
const boxOf = (n, pad = 0) => ({ l: n.x - n.w / 2 - pad, r: n.x + n.w / 2 + pad, t: n.y - n.h / 2 - pad, b: n.y + n.h / 2 + pad });
const inside = (p, box) => p[0] > box.l && p[0] < box.r && p[1] > box.t && p[1] < box.b;
const overlaps = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
const grow = (box, by) => ({ l: box.l - by, r: box.r + by, t: box.t - by, b: box.b + by });
function crosses(p, q, r, s) {
  const turn = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  // A sample landing exactly on the other line still counts, as symmetric layouts often do.
  return turn(p, q, r) * turn(p, q, s) < 0 && turn(r, s, p) * turn(r, s, q) <= 0;
}
function segmentHits(a, b, box) {
  let t0 = 0, t1 = 1; const dx = b[0] - a[0], dy = b[1] - a[1];
  for (const [p, q] of [[-dx, a[0] - box.l], [dx, box.r - a[0]], [-dy, a[1] - box.t], [dy, box.b - a[1]]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p; if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return t0 < t1;
}

// The roomiest layout that fits `maxWidth`, or the tightest one when none does.
// A label that finds no free spot first gets more room between rows.
export function layoutGraph(block, maxWidth = Infinity) {
  let laid = null;
  for (const step of STEPS) {
    for (let extra = 0; extra <= 72; extra += 24) {
      laid = layoutWith(block, { ...step, extra });
      if (!laid.edges.some(edge => edge.labelBox?.onLine)) break;
    }
    if (laid.width <= maxWidth) break;
  }
  return laid;
}

function layoutWith(block, { gap: GAP, wrap: limit, extra }) {
  const nodes = block.nodes.map(item => ({ ...item, ...measure(item, limit) }));
  const byKey = new Map(nodes.map(item => [item.key, item]));
  const cols = Math.max(...nodes.map(item => item.col)) + 1, rows = Math.max(...nodes.map(item => item.row)) + 1;
  const colW = Array.from({ length: cols }, (_, c) => Math.max(0, ...nodes.filter(item => item.col === c).map(item => item.w)));
  const rowH = Array.from({ length: rows }, (_, r) => Math.max(0, ...nodes.filter(item => item.row === r).map(item => item.h)));
  // A worded edge between neighbouring columns of one row widens that gap to fit its label.
  const hgap = Array.from({ length: cols }, () => GAP), vgap = Array.from({ length: rows }, () => GAP + extra);
  for (const edge of block.edges) {
    const a = byKey.get(edge.start), b = byKey.get(edge.end);
    if (!edge.label || a === b) continue;
    if (a.row === b.row && Math.abs(a.col - b.col) === 1) hgap[Math.min(a.col, b.col)] = Math.max(hgap[Math.min(a.col, b.col)], textWidth(edge.label, SIZES.label) + 28);
    if (a.col === b.col && Math.abs(a.row - b.row) === 1) vgap[Math.min(a.row, b.row)] = Math.max(vgap[Math.min(a.row, b.row)], 48);
  }
  const xs = [], ys = [];
  colW.forEach((w, c) => xs.push(c ? xs[c - 1] + colW[c - 1] / 2 + hgap[c - 1] + w / 2 : w / 2));
  rowH.forEach((h, r) => ys.push(r ? ys[r - 1] + rowH[r - 1] / 2 + vgap[r - 1] + h / 2 : h / 2));
  for (const item of nodes) { item.x = xs[item.col]; item.y = ys[item.row]; }

  const pairs = new Set(block.edges.map(edge => `${edge.start}>${edge.end}`));
  const chords = block.edges.filter(edge => edge.start !== edge.end).map(edge => [byKey.get(edge.start), byKey.get(edge.end)]);
  // 1. Route: straight when the centre line is clear; otherwise a curve around the blocking nodes.
  const routes = block.edges.map(edge => {
    const a = byKey.get(edge.start), b = byKey.get(edge.end), result = { ...edge, key: `${edge.start}--${edge.end}`, a, b };
    if (a === b) return { ...result, ...selfLoop(a, nodes, block.edges) };
    const others = nodes.filter(item => item !== a && item !== b).map(item => boxOf(item, 8));
    const two = edge.directed && pairs.has(`${edge.end}>${edge.start}`);
    const length = Math.hypot(b.x - a.x, b.y - a.y) || 1, nx = -(b.y - a.y) / length, ny = (b.x - a.x) / length;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, ends = [[a.x, a.y], [b.x, b.y]];
    const clear = c => { for (let t = 0.04; t < 0.97; t += 0.02) { const p = c ? quad(ends[0], c, ends[1], t) : [a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t]; if (others.some(box => inside(p, box))) return false; } return true; };
    const crossings = c => {
      const points = Array.from({ length: 25 }, (_, i) => quad(ends[0], c, ends[1], i / 24));
      return chords.filter(([p, q]) => ![p, q].some(n => n === a || n === b))
        .reduce((sum, [p, q]) => sum + points.slice(1).filter((point, i) => crosses(points[i], point, [p.x, p.y], [q.x, q.y])).length, 0);
    };
    // The two arrows of a two-way pair bow apart, each to its own right, so each keeps its label.
    const bowed = two && clear([mx + nx * 26, my + ny * 26]);
    let ctrl = bowed ? [mx + nx * 26, my + ny * 26] : null;
    if (!ctrl && (two || !clear(null))) {
      // A blocked edge bends around the nodes in its way, to the side where it crosses fewest edges.
      let best = null;
      for (const offset of two ? [56, 84, 120, 160] : [56, -56, 84, -84, 120, -120, 160, -160]) {
        const c = [mx + nx * offset, my + ny * offset];
        if (!clear(c)) continue;
        const cost = crossings(c);
        if (!best || cost < best.cost) best = { c, cost };
        if (!cost) break;
      }
      ctrl = best?.c || [mx + nx * 56, my + ny * 56];
    }
    return { ...result, ctrl, bowed };
  });
  // 2. Attach: a box takes each edge on the side that faces it, spread along that side when
  //    several edges share it, so lines meet sides rather than corners; a circle takes it on its rim.
  const sideOf = (n, toward) => {
    const dx = toward[0] - n.x, dy = toward[1] - n.y;
    return Math.abs(dx) / n.w > Math.abs(dy) / n.h ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'bottom' : 'top');
  };
  const slots = new Map();
  for (const route of routes.filter(item => !item.loop)) for (const [n, other, end] of [[route.a, route.b, 'start'], [route.b, route.a, 'end']]) {
    if (n.r) continue;
    // A bowed pair leaves through the sides that face each other, each arrow on its own half.
    const toward = route.ctrl || [other.x, other.y], side = sideOf(n, route.bowed ? [other.x, other.y] : toward);
    const key = `${n.key}:${side}`, along = side === 'top' || side === 'bottom' ? toward[0] : toward[1];
    (slots.get(key) || slots.set(key, []).get(key)).push({ route, end, along, side, n });
  }
  for (const list of slots.values()) {
    list.sort((p, q) => p.along - q.along);
    const n = list[0].n, horizontal = list[0].side === 'top' || list[0].side === 'bottom', span = (horizontal ? n.w : n.h) - 24, step = Math.min(22, span / Math.max(1, list.length - 1));
    list.forEach((slot, index) => {
      const offset = (index - (list.length - 1) / 2) * step;
      const point = horizontal ? [n.x + offset, n.y + (slot.side === 'top' ? -1 : 1) * (n.h / 2 + 1)] : [n.x + (slot.side === 'left' ? -1 : 1) * (n.w / 2 + 1), n.y + offset];
      slot.route[slot.end === 'start' ? 'startPoint' : 'endPoint'] = point;
    });
  }
  const edges = routes.map(route => {
    const { a, b, ctrl, bowed, ...edge } = route;
    if (route.loop) return edge;
    const start = route.startPoint || rim(a, ctrl || [b.x, b.y]);
    const end = route.endPoint || rim(b, ctrl || [a.x, a.y]);
    delete edge.startPoint; delete edge.endPoint;
    const points = ctrl ? Array.from({ length: 25 }, (_, i) => quad(start, ctrl, end, i / 24)) : [start, end];
    // The side a curve bows to; its label sits on the outside of the bow.
    const bend = ctrl ? Math.sign(-(end[1] - start[1]) * (ctrl[0] - (start[0] + end[0]) / 2) + (end[0] - start[0]) * (ctrl[1] - (start[1] + end[1]) / 2)) : 0;
    return { ...edge, path: ctrl ? `M${start} Q${ctrl} ${end}` : `M${start} L${end}`, points, tip: end, from: ctrl || start, bend };
  });
  placeLabels(nodes, edges);
  return { nodes, edges, ...crop(nodes, edges) };
}

// A self-loop leaves and re-enters the side of its node that the fewest edges use.
function selfLoop(n, nodes, allEdges) {
  const sides = [[0, -1], [1, 0], [0, 1], [-1, 0]];
  const used = side => allEdges.filter(edge => edge.start !== edge.end && (edge.start === n.key || edge.end === n.key)).map(edge => {
    const other = nodes.find(item => item.key === (edge.start === n.key ? edge.end : edge.start));
    const dx = other.x - n.x, dy = other.y - n.y, length = Math.hypot(dx, dy) || 1;
    return (dx * side[0] + dy * side[1]) / length;
  }).reduce((sum, value) => sum + Math.max(0, value), 0) + nodes.filter(item => item !== n && inside([n.x + side[0] * (n.w / 2 + 40), n.y + side[1] * (n.h / 2 + 40)], boxOf(item, 30))).length * 5;
  const [sx, sy] = sides.reduce((best, side) => used(side) < used(best) - 1e-6 ? side : best);
  const px = -sy, py = sx, reach = (sx ? n.w : n.h) / 2;
  const spread = n.r ? n.r * 0.7 : Math.min(18, (sx ? n.h : n.w) / 3);
  const start = [n.x + sx * reach + px * spread, n.y + sy * reach + py * spread];
  const end = [n.x + sx * reach - px * spread, n.y + sy * reach - py * spread];
  if (n.r) { // on a circle, start and end sit on the rim
    for (const point of [start, end]) { const dx = point[0] - n.x, dy = point[1] - n.y, length = Math.hypot(dx, dy); point[0] = n.x + dx / length * (n.r + 1); point[1] = n.y + dy / length * (n.r + 1); }
  }
  const out = Math.max(48, (n.r || 24) * 1.9), wide = (n.r ? n.r * 0.9 : 20), c1 = [start[0] + sx * out + px * wide, start[1] + sy * out + py * wide], c2 = [end[0] + sx * out - px * wide, end[1] + sy * out - py * wide];
  const points = Array.from({ length: 25 }, (_, i) => cubic(start, c1, c2, end, i / 24));
  return { path: `M${start} C${c1} ${c2} ${end}`, points, tip: end, from: c2, loop: [sx, sy] };
}

// Each label tries spots beside its own line, nearest the middle first, and takes the first
// that is clear of every node, every line (its own included) and every earlier label.
function placeLabels(nodes, edges) {
  const placed = [], blocks = nodes.map(item => boxOf(item, 4));
  const cx = nodes.reduce((sum, item) => sum + item.x, 0) / nodes.length, cy = nodes.reduce((sum, item) => sum + item.y, 0) / nodes.length;
  const segments = edges.flatMap(edge => edge.points.slice(1).map((p, i) => [edge.points[i], p]));
  const free = box => !blocks.some(other => overlaps(box, other)) && !placed.some(other => overlaps(grow(box, 6), other)) && !segments.some(([a, b]) => segmentHits(a, b, box));
  for (const edge of edges.filter(item => item.label)) {
    const w = textWidth(edge.label, SIZES.label) + 8, h = 20, pts = edge.points;
    let chosen = null;
    const at = (t, side, d) => {
      const i = Math.min(pts.length - 2, Math.floor(t * (pts.length - 1))), a = pts[i], b = pts[i + 1];
      const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy) || 1;
      let nx = -dy / length * side, ny = dx / length * side;
      if (edge.loop) { nx = edge.loop[0]; ny = edge.loop[1]; }
      const p = edge.loop ? pts[12] : [a[0] + dx * ((t * (pts.length - 1)) % 1), a[1] + dy * ((t * (pts.length - 1)) % 1)];
      const reach = Math.abs(nx) * w / 2 + Math.abs(ny) * h / 2 + d;
      const cx = p[0] + nx * reach, cy = p[1] + ny * reach;
      return { l: cx - w / 2, r: cx + w / 2, t: cy - h / 2, b: cy + h / 2, cx, cy };
    };
    // Prefer the side of the line that faces away from the drawing's middle, so labels sit
    // outside a ring or a pair of curves rather than inside it.
    const mid = pts[Math.floor(pts.length / 2)] || pts[0], [a0, b0] = [pts[0], pts.at(-1)];
    const dx0 = b0[0] - a0[0], dy0 = b0[1] - a0[1], outward = (-dy0) * (mid[0] - cx) + dx0 * (mid[1] - cy);
    const firstSide = edge.bend || (Math.abs(outward) < 1 ? ((dx0 >= 0) ? -1 : 1) : outward > 0 ? 1 : -1);
    search: for (const side of [firstSide, -firstSide]) for (const d of [6, 12, 20, 32]) for (const t of edge.loop ? [0.5] : [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74]) {
      const box = at(t, side, d);
      if (free(box)) { chosen = box; break search; }
    }
    chosen ||= { ...at(0.5, firstSide, 6), onLine: true };
    placed.push(chosen); edge.labelBox = chosen;
  }
}

function crop(nodes, edges) {
  const xs = [], ys = [];
  for (const item of nodes) { xs.push(item.x - item.w / 2, item.x + item.w / 2); ys.push(item.y - item.h / 2, item.y + item.h / 2); }
  for (const edge of edges) {
    for (const p of edge.points) { xs.push(p[0]); ys.push(p[1]); }
    if (edge.labelBox) { xs.push(edge.labelBox.l, edge.labelBox.r); ys.push(edge.labelBox.t, edge.labelBox.b); }
  }
  const left = Math.min(...xs) - PAD, top = Math.min(...ys) - PAD;
  return { left, top, width: Math.max(...xs) + PAD - left, height: Math.max(...ys) + PAD - top };
}

function arrow([x, y], [fx, fy]) {
  const dx = x - fx, dy = y - fy, length = Math.hypot(dx, dy) || 1, ux = dx / length, uy = dy / length;
  return `M${x - 10 * ux + 5 * uy},${y - 10 * uy - 5 * ux} L${x},${y} L${x - 10 * ux - 5 * uy},${y - 10 * uy + 5 * ux}`;
}

// The drawing at its natural size: 1 unit = 1 CSS pixel. On narrow screens it shrinks only until
// its smallest text (14 px edge labels) reaches 12 px; beyond that its region scrolls sideways.
export function drawGraph(block, label = '') {
  // The reading column is about 600 px wide; on a phone it is the viewport less its margins.
  const laid = layoutGraph(block, Math.min(620, (globalThis.innerWidth || 1280) - 72));
  const graph = svgNode('svg', { viewBox: `${laid.left} ${laid.top} ${laid.width} ${laid.height}`, width: Math.round(laid.width), height: Math.round(laid.height), class: 'graph', role: 'img', 'aria-label': label });
  graph.style.minWidth = `${Math.ceil(laid.width * 12 / SIZES.label)}px`;
  for (const edge of laid.edges) {
    graph.append(svgNode('path', { d: edge.path, class: 'edge', 'data-edge-key': edge.key }));
    if (edge.directed) graph.append(svgNode('path', { d: arrow(edge.tip, edge.from), class: 'arrow', 'data-arrow-key': edge.key }));
  }
  const groups = new Map();
  for (const item of laid.nodes) {
    const group = svgNode('g', { class: item.shape === 'box' ? 'node-box' : 'node-circle', 'data-node-key': item.key, 'data-cx': item.x, 'data-cy': item.y, 'data-reach': Math.max(item.w, item.h) / 2 + 10 });
    group.append(item.shape === 'box' ? svgNode('rect', { x: item.x - item.w / 2, y: item.y - item.h / 2, width: item.w, height: item.h, rx: 6 }) : svgNode('circle', { cx: item.x, cy: item.y, r: item.r }));
    const text = svgNode('text', { x: item.x, y: item.y });
    item.lines.forEach((line, index) => {
      const span = svgNode('tspan', { x: item.x, y: item.y + (index - (item.lines.length - 1) / 2) * LINE, 'dominant-baseline': 'central' });
      span.textContent = line; text.append(span);
    });
    group.append(text); groups.set(item.key, group); graph.append(group);
  }
  for (const edge of laid.edges.filter(item => item.labelBox)) {
    const text = svgNode('text', { x: edge.labelBox.cx, y: edge.labelBox.cy, class: 'edge-label', 'dominant-baseline': 'central' });
    text.textContent = edge.label; graph.append(text);
  }
  return { graph, groups, laid };
}
