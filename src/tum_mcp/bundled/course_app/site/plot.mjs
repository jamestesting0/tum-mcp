import { node, studyText, append, svgNode, button } from './dom.mjs';

// Plots keep one look: a framed area, a dotted grid, accent lines told apart by dash pattern,
// and a legend below. The drawing is made at the width it is shown at (1 unit = 1 CSS pixel) and
// redrawn when that width changes, so tick and axis text stays legible on a phone.
export const plotNumber = value => value && (Math.abs(value) >= 10000 || Math.abs(value) < .001) ? value.toExponential(2).replace(/\.?0+e/, 'e') : Number(value.toPrecision(5)).toString();
const DASH = ['none', '8 5', '2 4', '12 4 2 4', '4 3'];
const TICK = 14, TITLE = 15;
let measurer = null;
function textWidth(text, size) {
  measurer ||= document.createElement('canvas').getContext('2d');
  measurer.font = `${size}px ${getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim() || 'sans-serif'}`;
  return measurer.measureText(text).width || text.length * size * 0.55;
}
// Tick labels: thousands grouped with a narrow space; a minus sign, not a hyphen.
function tickText(value) {
  const text = Math.abs(value) >= 1000 && Number.isInteger(value) ? String(Math.abs(value)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f') : String(Math.abs(Number(value.toPrecision(6))));
  return value < 0 ? `\u2212${text}` : text;
}
// Round tick values (1, 2, 2.5 or 5 times a power of ten) inside the bounds.
export function niceTicks(min, max, target, integer = false) {
  const raw = (max - min) / target, magnitude = 10 ** Math.floor(Math.log10(raw));
  let best = null;
  for (const factor of [1, 2, 2.5, 5, 10]) {
    const step = factor * magnitude;
    if (integer && (step < 1 || !Number.isInteger(step))) continue;
    const first = Math.ceil(min / step - 1e-9) * step, count = Math.floor((max - first) / step + 1e-9) + 1;
    const score = Math.abs(count - target) + (factor === 2.5 ? 0.3 : 0);
    if (count >= 2 && (!best || score < best.score)) best = { step, first, count, score };
  }
  return Array.from({ length: best.count }, (_, i) => Number((best.first + i * best.step).toPrecision(12)));
}
const logTicks = (min, max) => {
  const ticks = [];
  for (let power = Math.ceil(Math.log10(min) - 1e-9); 10 ** power <= max * (1 + 1e-9); power++) ticks.push(10 ** power);
  return ticks;
};

function segmentHits(a, b, box) {
  let t0 = 0, t1 = 1; const dx = b[0] - a[0], dy = b[1] - a[1];
  for (const [p, q] of [[-dx, a[0] - box.l], [dx, box.r - a[0]], [-dy, a[1] - box.t], [dy, box.b - a[1]]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p; if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return t0 < t1;
}
// The pieces of a series: sampled function pieces from the build, or its data points.
const pieces = line => line.pieces?.length ? line.pieces.map(piece => piece.map(([x, y]) => ({ x, y }))) : [line.points];
const style = line => line.style || 'line';

// One row per x when every series shares the same x values (x, then a column per series),
// otherwise one row per point named by its series; numbers line up on the right.
function dataTable(block, data) {
  const xs = data[0].points.map(point => point.x);
  const shared = data.every(line => line.points.length === xs.length && line.points.every((point, i) => point.x === xs[i]));
  const columns = shared ? [block.x_label, ...(data.length === 1 ? [block.y_label] : data.map(line => line.label))] : ['Series', block.x_label, block.y_label];
  const rows = shared ? xs.map((x, i) => [plotNumber(x), ...data.map(line => plotNumber(line.points[i].y))])
    : data.flatMap(line => line.points.map(point => [line.label, plotNumber(point.x), plotNumber(point.y)]));
  const table = node('table', `plot-table${shared ? ' numeric' : ''}`), head = node('tr'), body = node('tbody');
  for (const title of columns) { const th = studyText('th', '', title); th.scope = 'col'; head.append(th); }
  for (const row of rows) {
    const [first, ...values] = row, label = studyText('th', '', first);
    label.scope = 'row';
    body.append(append(node('tr'), label, ...values.map(value => node('td', '', value))));
  }
  return append(table, append(node('thead'), head), body);
}

export function renderPlot(block) {
  const root = node('div', 'plot'), graph = svgNode('svg', { role: 'img', 'aria-label': block.description });
  const holder = node('div', 'plot-drawing'); holder.append(graph);
  const marks = svgNode('g'), series = svgNode('g', { class: 'plot-interaction' });
  const area = { left: 0, right: 0, top: 0, bottom: 0 }, listeners = [];
  const log = block.y_scale === 'log';
  let X = value => value, Y = value => value, drawnWidth = 0;
  const labelled = block.series.filter(line => line.label);
  const direct = block.legend === 'direct' && labelled.length > 1;

  function draw(W) {
    drawnWidth = W;
    const narrow = W < 460, H = Math.round(Math.min(380, Math.max(240, W * 0.6)));
    // Whole-number data (steps, counts) gets whole-number ticks.
    const integer = block.series.every(line => !line.function && line.points.every(p => Number.isInteger(p.x)));
    const xTicks = block.x_ticks?.length ? block.x_ticks : niceTicks(block.x_min, block.x_max, narrow ? 4 : 6, integer);
    const yTicks = block.y_ticks?.length ? block.y_ticks : log ? logTicks(block.y_min, block.y_max) : niceTicks(block.y_min, block.y_max, narrow ? 4 : 5);
    const yTitle = studyText('span', '', block.y_label).textContent, xTitle = studyText('span', '', block.x_label).textContent;
    // A short axis symbol sits upright above the axis; a longer title turns along it.
    const upright = yTitle.length <= 3;
    const tickRoom = Math.max(...yTicks.map(value => textWidth(tickText(value), TICK)));
    const directRoom = direct ? Math.max(...labelled.map(line => textWidth(studyText('span', '', line.label).textContent, TICK))) + 14 : 0;
    Object.assign(area, { left: Math.ceil(tickRoom + 14 + (upright ? 0 : 26)), right: W - 12 - directRoom, top: upright ? 30 : 14, bottom: H - 56 });
    const lo = log ? Math.log10(block.y_min) : block.y_min, hi = log ? Math.log10(block.y_max) : block.y_max;
    X = value => area.left + (value - block.x_min) / (block.x_max - block.x_min) * (area.right - area.left);
    Y = value => area.bottom - ((log ? Math.log10(value) : value) - lo) / (hi - lo) * (area.bottom - area.top);
    graph.setAttribute('viewBox', `0 0 ${W} ${H}`); graph.setAttribute('width', W); graph.setAttribute('height', H);
    marks.replaceChildren();
    const text = (value, attributes, className = '') => { const element = svgNode('text', { ...attributes, ...(className ? { class: className } : {}) }); element.textContent = value; marks.append(element); return element; };
    marks.append(svgNode('rect', { x: area.left, y: area.top, width: area.right - area.left, height: area.bottom - area.top, class: 'plot-area' }));
    for (const value of xTicks) {
      marks.append(svgNode('line', { x1: X(value), y1: area.top, x2: X(value), y2: area.bottom, class: 'plot-grid' }));
      text(tickText(value), { x: X(value), y: area.bottom + 20, 'text-anchor': 'middle' });
    }
    for (const value of yTicks) {
      marks.append(svgNode('line', { x1: area.left, y1: Y(value), x2: area.right, y2: Y(value), class: 'plot-grid' }));
      text(tickText(value), { x: area.left - 8, y: Y(value) + 5, 'text-anchor': 'end' });
    }
    // The y axis at x = 0 is drawn unless a stem or point already stands there.
    const pointAtZero = block.series.some(line => ['stems', 'points', 'markers'].includes(style(line)) && line.points.some(p => p.x === 0));
    if (block.x_min < 0 && block.x_max > 0 && !pointAtZero) marks.append(svgNode('line', { x1: X(0), y1: area.top, x2: X(0), y2: area.bottom, class: 'plot-axis' }));
    if (!log && block.y_min < 0 && block.y_max > 0) marks.append(svgNode('line', { x1: area.left, y1: Y(0), x2: area.right, y2: Y(0), class: 'plot-axis' }));
    text(xTitle, { x: (area.left + area.right) / 2, y: H - 12, 'text-anchor': 'middle' }, 'plot-title');
    if (upright) text(yTitle, { x: area.left, y: 18, 'text-anchor': 'middle' }, 'plot-title');
    else text(yTitle, { transform: `translate(16 ${(area.top + area.bottom) / 2}) rotate(-90)`, 'text-anchor': 'middle' }, 'plot-title');

    const clip = svgNode('clipPath', { id: `plot-clip-${uid}` });
    clip.append(svgNode('rect', { x: area.left, y: area.top - 2, width: area.right - area.left, height: area.bottom - area.top + 4 }));
    const inside = svgNode('g', { 'clip-path': `url(#plot-clip-${uid})` }), above = svgNode('g');
    marks.append(append(svgNode('defs'), clip), inside, above);
    const base = log ? block.y_min : Math.max(block.y_min, Math.min(0, block.y_max)), areaLabels = [];
    for (const shade of block.areas || []) {
      const line = block.series.find(item => item.key === shade.series);
      const points = pieces(line).flat().filter(p => p.x >= shade.x_from && p.x <= shade.x_to);
      if (points.length < 2) continue;
      inside.append(svgNode('polygon', { points: [[X(points[0].x), Y(base)], ...points.map(p => [X(p.x), Y(p.y)]), [X(points.at(-1).x), Y(base)]].map(p => p.join(',')).join(' '), class: 'plot-fill' }));
      if (shade.label) areaLabels.push({ shade, points });
    }
    const ends = [];
    block.series.forEach((line, index) => {
      const dash = DASH[index % DASH.length], kind = style(line);
      if (kind === 'stems') {
        for (const p of line.points) {
          inside.append(svgNode('line', { x1: X(p.x), y1: Y(base), x2: X(p.x), y2: Y(p.y), class: 'plot-line plot-stem' }));
          above.append(svgNode('circle', { cx: X(p.x), cy: Y(p.y), r: 5, class: 'plot-dot' }));
        }
      } else if (kind === 'steps') {
        // Each value holds from its x to the next point's x; the last runs to the right edge.
        const points = line.points.flatMap((p, i) => [[p.x, p.y], [line.points[i + 1]?.x ?? block.x_max, p.y]]);
        inside.append(svgNode('polyline', { points: points.map(([x, y]) => `${X(x)},${Y(y)}`).join(' '), class: 'plot-line', 'stroke-dasharray': dash }));
      } else {
        if (kind !== 'points') for (const piece of pieces(line)) inside.append(svgNode('polyline', { points: piece.map(p => `${X(p.x)},${Y(p.y)}`).join(' '), class: `plot-line${kind === 'markers' ? ' plot-guide' : ''}`, 'stroke-dasharray': dash }));
        if (kind === 'points' || kind === 'markers') for (const p of line.points) above.append(svgNode('circle', { cx: X(p.x), cy: Y(p.y), r: 4, class: index ? 'plot-dot plot-open' : 'plot-dot' }));
      }
      if (line.values) for (const p of line.points) text(plotNumber(p.y), { x: X(p.x), y: Y(p.y) - 11, 'text-anchor': 'middle' }, 'plot-value');
      const last = pieces(line).flat().at(-1);
      if (last && line.label) ends.push({ line, x: kind === 'steps' ? block.x_max : last.x, y: last.y });
    });
    // A note takes the first corner around its point where its text crosses no curve.
    const strokes = block.series.flatMap(line => style(line) === 'stems' ? [] : pieces(line).map(piece => piece.map(p => [X(p.x), Y(p.y)])));
    const crosses = box => strokes.some(line => line.some(([x, y], i) => i && segmentHits(line[i - 1], [x, y], box)));
    // An area's value sits inside it, halfway up, beside the y axis rather than across it.
    const axisX = block.x_min < 0 && block.x_max > 0 && !pointAtZero ? X(0) : null;
    for (const { shade, points } of areaLabels) {
      const label = studyText('span', '', shade.label).textContent, w = textWidth(label, TICK) + 8;
      const spot = x => {
        const near = points.reduce((best, p) => Math.abs(p.x - x) < Math.abs(best.x - x) ? p : best), cx = X(x), cy = (Y(base) + Y(near.y)) / 2;
        return { cx, cy, box: { l: cx - w / 2, r: cx + w / 2, t: cy - 10, b: cy + 10 } };
      };
      const middle = (shade.x_from + shade.x_to) / 2, halves = axisX !== null && shade.x_from < 0 && shade.x_to > 0 ? [shade.x_to / 2, shade.x_from / 2] : [];
      const clear = ({ box }) => !crosses(box) && (axisX === null || axisX < box.l || axisX > box.r);
      const found = [middle, ...halves].map(spot).find(clear), chosen = found || spot(middle);
      // With no clear spot, a knockout opens the lines behind the value.
      if (!found) marks.append(svgNode('rect', { x: chosen.box.l, y: chosen.box.t, width: w, height: 20, rx: 3, class: 'plot-knockout' }));
      text(label, { x: chosen.cx, y: chosen.cy + 5, 'text-anchor': 'middle' }, 'plot-strong');
    }
    for (const note of block.notes || []) {
      above.append(svgNode('circle', { cx: X(note.x), cy: Y(note.y), r: 4.5, class: 'plot-dot plot-mark' }));
      const label = studyText('span', '', note.text).textContent, w = textWidth(label, TICK) + 6, cx = X(note.x), cy = Y(note.y);
      // Corners first, then beside the point, each a little further out until one is clear.
      const spots = [8, 18, 30].flatMap(gap => [[1, -1], [-1, 1], [1, 1], [-1, -1], [1, 0], [-1, 0]].map(([sx, sy]) => {
        const t = sy > 0 ? cy + gap - 2 : sy < 0 ? cy - gap - 16 : cy - 9;
        return { sx, box: { l: sx > 0 ? cx + gap : cx - gap - w, r: sx > 0 ? cx + gap + w : cx - gap, t, b: t + 18 } };
      }));
      const fits = spot => spot.box.l >= area.left && spot.box.r <= area.right && spot.box.t >= area.top && spot.box.b <= area.bottom;
      const clear = spot => fits(spot) && !crosses(spot.box) && (axisX === null || axisX < spot.box.l || axisX > spot.box.r);
      const found = spots.find(clear), best = found || spots.find(fits) || spots[0];
      if (!found) marks.append(svgNode('rect', { x: best.box.l, y: best.box.t, width: w, height: 18, rx: 3, class: 'plot-knockout' }));
      text(label, { x: best.sx > 0 ? best.box.l + 3 : best.box.r - 3, y: best.box.b - 5, 'text-anchor': best.sx > 0 ? 'start' : 'end' }, 'plot-strong');
    }
    // Direct labels sit at the end of their series, nudged apart so they never overlap.
    if (direct) {
      // Placed from the bottom up, each at least one line above the next and inside the frame.
      let ceiling = area.bottom - 2;
      for (const end of ends.sort((p, q) => Y(q.y) - Y(p.y))) {
        const placed = Math.min(Y(end.y) + 5, ceiling); ceiling = placed - 18;
        text(studyText('span', '', end.line.label).textContent, { x: area.right + 8, y: placed }, 'plot-strong');
      }
    }
    graph.append(series);
    for (const listener of listeners) listener();
  }

  const uid = Math.random().toString(36).slice(2);
  graph.append(marks, series);
  root.append(studyText('p', 'small', block.description), holder);
  // Under the drawing, one quiet row: the legend on the left, the data toggle on the right.
  const footer = node('div', 'plot-footer');
  if (labelled.length > 1 && !direct) {
    const legend = node('ul', 'plot-legend');
    block.series.forEach((line, i) => {
      if (!line.label) return;
      const sample = svgNode('svg', { viewBox: '0 0 32 12', 'aria-hidden': 'true' });
      sample.append(style(line) === 'stems' || style(line) === 'points' ? svgNode('circle', { cx: 16, cy: 6, r: 4, class: i ? 'plot-dot plot-open' : 'plot-dot' }) : svgNode('line', { x1: 0, x2: 32, y1: 6, y2: 6, class: 'plot-line', 'stroke-dasharray': DASH[i % DASH.length] }));
      legend.append(append(node('li'), sample, studyText('span', '', line.label)));
    });
    footer.append(legend);
  }
  // Data series list their values; a function shows its formula instead of 200 samples.
  const data = block.series.filter(line => line.points?.length);
  if (data.length) {
    const region = node('div', 'table-region plot-data');
    region.id = `plot-data-${uid}`; region.hidden = true; region.tabIndex = 0;
    region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Graph data');
    region.append(dataTable(block, data));
    const toggle = button('Data', () => {
      region.hidden = !region.hidden; toggle.setAttribute('aria-expanded', String(!region.hidden));
    }, 'plot-data-toggle');
    toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-controls', region.id);
    footer.append(toggle);
    root.append(footer, region);
  } else if (footer.childElementCount) root.append(footer);
  draw(600);
  new ResizeObserver(() => {
    const width = Math.round(holder.clientWidth);
    if (width && Math.abs(width - drawnWidth) > 2) draw(width);
  }).observe(holder);
  return { root, graph, series, area, x: value => X(value), y: value => Y(value), onResize: listener => listeners.push(listener) };
}
