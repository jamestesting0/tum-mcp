import { node, svgNode, studyText, button, append, plainText } from '../shell/dom.mjs';
import { exam, concepts, topics, conceptBadge, quietLink } from './exam-state.mjs';
import { entry } from './exam-entry.mjs';
import { iconButton } from '../shell/navigation.mjs';

const kinds = { requires: 'needed for', derives: 'leads to', contrasts: 'contrasts with' };
function lines(text, width = 20) {
  const words = text.split(/\s+/), result = [];
  for (const word of words) {
    const last = result.at(-1);
    if (last && (last + ' ' + word).length <= width) result[result.length - 1] = `${last} ${word}`;
    else result.push(word);
  }
  return result.length > 2 ? [result[0], `${result.slice(1).join(' ').slice(0, width - 1)}…`] : result;
}
const plainTitle = key => studyText('span', '', concepts.get(key)?.title || key).textContent;

const ICONS = {
  out: 'M3.5 8h9', in: 'M8 3.5v9M3.5 8h9',
  fit: 'M5.5 2H2v3.5M10.5 2H14v3.5M14 10.5V14h-3.5M2 10.5V14h3.5M6 6h4v4H6z',
  enter: 'M2 6V2h4M2 2l4 4M14 6V2h-4M14 2l-4 4M2 10v4h4M2 14l4-4M14 10v4h-4M14 14l-4-4',
  exit: 'M6 2v4H2M6 6 2 2M10 2v4h4M10 6l4-4M6 14v-4H2M6 10l-4 4M10 14v-4h4M10 10l4 4',
};
function tool(name, d, action, extra = '') {
  const control = button('', action, `quiet exam-map-tool ${extra}`.trim());
  const icon = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
  icon.append(svgNode('path', { d })); control.append(icon);
  control.setAttribute('aria-label', name); control.title = name;
  return control;
}
function legendItem(dashed, text) {
  const sample = svgNode('svg', { viewBox: '0 0 28 10', 'aria-hidden': 'true', focusable: 'false' });
  sample.append(svgNode('path', { d: dashed ? 'M2 5h24' : 'M2 5h20', class: dashed ? 'dashed' : '' }));
  if (!dashed) sample.append(svgNode('path', { d: 'M20 1.5 26 5l-6 3.5z', class: 'head' }));
  return append(node('span', 'exam-map-legend-item'), sample, node('span', '', text));
}

// The semester map: build-time positions, focusable nodes and, for the selection, the same entry
// the cheatsheet list shows, so a student reads the details without leaving the map.
// The smallest scale a map opens at, so 13px card titles stay legible.
const READABLE = 0.8;

export function renderMap() {
  const map = exam.map;
  const root = node('section', 'exam-map'); root.setAttribute('aria-labelledby', 'exam-map-title');
  const title = node('h2', '', 'Semester map'); title.id = 'exam-map-title';
  const heading = append(node('div', 'section-heading exam-map-heading'), title);
  root.append(heading);
  if (!map?.nodes?.length) { root.hidden = true; return root; }
  const links = new Map(map.nodes.map(item => [item.key, []]));
  for (const edge of map.edges) { links.get(edge.start).push({ ...edge, other: edge.end, out: true }); links.get(edge.end).push({ ...edge, other: edge.start, out: false }); }
  const card = node('div', 'exam-map-card'); card.setAttribute('role', 'region'); card.hidden = true;
  // Only the selection is announced, never the whole entry.
  const status = node('p', 'visually-hidden'); status.setAttribute('aria-live', 'polite');
  // Once the student opens an entry, the next selection opens too, so they can browse details.
  let expanded = false;
  const ordered = [...map.nodes].sort((a, b) => a.column - b.column || a.y - b.y || a.x - b.x);
  const elements = new Map();
  let selected = null;
  function describe(key) {
    const concept = concepts.get(key);
    return [plainTitle(key), conceptBadge(concept), ...links.get(key).map(link => `${link.out ? kinds[link.kind] : link.kind === 'contrasts' ? 'contrasts with' : 'builds on'} ${plainTitle(link.other)}`)].join('. ');
  }
  function select(key, focus = false) {
    selected = key;
    const related = new Set([key, ...links.get(key).map(link => link.other)]);
    for (const [other, element] of elements) {
      element.classList.toggle('selected', other === key);
      element.classList.toggle('related', related.has(other) && other !== key);
      element.setAttribute('aria-pressed', String(other === key));
    }
    for (const edge of svg.querySelectorAll('[data-edge]')) edge.classList.toggle('related', edge.dataset.start === key || edge.dataset.end === key);
    const concept = concepts.get(key);
    // The open state carries over from the entry shown now, read when the selection changes.
    const current = card.querySelector('.exam-entry-details');
    if (current) expanded = current.open;
    const made = entry(concept, { id: false });
    if (made.details) made.details.open = expanded;
    card.setAttribute('aria-label', plainTitle(key));
    card.replaceChildren(iconButton('Close', 'close', deselect), made.article);
    card.append(append(node('p', 'small exam-map-more'), quietLink('Open in Cheatsheet', `#exam/sheet/${concept.key}`)));
    card.hidden = false;
    status.textContent = `Selected: ${plainTitle(key)}`;
    if (focus) elements.get(key).focus();
    // In full screen the details sit beside the map, which narrows: keep the node in view.
    if (root.classList.contains('expanded')) requestAnimationFrame(() => reveal(position.get(key)));
  }
  function deselect() {
    const key = selected;
    selected = null; card.hidden = true; card.replaceChildren(); status.textContent = '';
    for (const element of elements.values()) { element.classList.remove('selected', 'related'); element.setAttribute('aria-pressed', 'false'); }
    for (const edge of svg.querySelectorAll('[data-edge]')) edge.classList.remove('related');
    if (key) elements.get(key)?.focus({ preventScroll: true });
  }
  const scroller = node('div', 'exam-map-scroll'); scroller.tabIndex = 0;
  // The collapsed frame takes the map's shape, so a wide, short map leaves no empty band; it is
  // tall enough to show the map at a readable size when the whole map would not be.
  scroller.style.aspectRatio = `${map.width + 64} / ${map.height + 160}`;
  scroller.style.minHeight = `${Math.round(map.height * READABLE + 48)}px`;
  scroller.setAttribute('aria-label', 'Semester map canvas. Arrow keys move it, plus and minus zoom, 0 fits it.');
  scroller.title = 'Drag to move · pinch or Ctrl/⌘ + scroll to zoom';
  const svg = svgNode('svg', { viewBox: `0 0 ${map.width} ${map.height}`, class: 'exam-map-svg', role: 'group', 'aria-label': 'Semester map of exam-relevant ideas' });
  // Arrowheads keep one size at every line width and take the colour of their line: the line
  // stops where the head begins, and the last stretch runs straight into it.
  const head = 9, stub = 10, defs = svgNode('defs');
  for (const [id, className] of [['exam-arrow', 'exam-arrow-head'], ['exam-arrow-related', 'exam-arrow-head related']]) {
    const marker = svgNode('marker', { id, viewBox: '0 0 10 10', refX: 0, refY: 5, markerWidth: head, markerHeight: head, markerUnits: 'userSpaceOnUse', orient: 'auto' });
    marker.append(svgNode('path', { d: 'M0 0L10 5L0 10z', class: className })); defs.append(marker);
  }
  svg.append(defs);
  for (const column of map.columns) {
    const label = svgNode('text', { x: column.x, y: 24, class: 'exam-map-column' }); label.textContent = plainText(column.title);
    svg.append(label);
  }
  const position = new Map(map.nodes.map(item => [item.key, item]));
  const width = map.node_width, height = map.node_height;
  // A line never crosses a card other than its own two. It takes the simplest route that stays
  // clear: one smooth curve, else two rounded corners through a gap between card columns, else
  // four corners through the gap beside the target's row.
  const cards = map.nodes.map(item => [item.x, item.y, item.x + width, item.y + height, item.key]);
  const ys = [...new Set(map.nodes.map(item => item.y))].sort((p, q) => p - q);
  const rowGap = Math.max(16, Math.min(48, ...ys.slice(1).map((y, i) => y - ys[i] - height).filter(gap => gap > 0)));
  const crosses = (points, own) => points.some(([x, y]) => cards.some(([l, t, r, low, key]) => !own.includes(key) && x > l - 4 && x < r + 4 && y > t - 4 && y < low + 4));
  const lefts = [...new Set(map.nodes.map(item => item.x))].sort((p, q) => p - q);
  const channels = lefts.slice(1).map((x, i) => [lefts[i] + width, x]).filter(([l, r]) => r - l > 12).map(([l, r]) => (l + r) / 2);
  const along = points => points.slice(1).flatMap(([x, y], i) => {
    const [px, py] = points[i], steps = Math.max(1, Math.ceil(Math.hypot(x - px, y - py) / 6));
    return Array.from({ length: steps }, (_, k) => [px + (x - px) * (k + 1) / steps, py + (y - py) * (k + 1) / steps]);
  });
  const sampled = (p0, p1, p2, p3) => Array.from({ length: 24 }, (_, i) => {
    const t = (i + 1) / 25, u = 1 - t;
    return [0, 1].map(k => u * u * u * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t * t * t * p3[k]);
  });
  const rounded = (points, radius = 10) => points.map(([x, y], i) => {
    if (i === 0) return `M${x} ${y}`;
    if (i === points.length - 1) return `L${x} ${y}`;
    const [px, py] = points[i - 1], [nx, ny] = points[i + 1];
    const before = Math.hypot(x - px, y - py) || 1, after = Math.hypot(nx - x, ny - y) || 1;
    const k1 = Math.min(radius, before / 2), k2 = Math.min(radius, after / 2);
    return `L${x - (x - px) / before * k1} ${y - (y - py) / before * k1}Q${x} ${y} ${x + (nx - x) / after * k2} ${y + (ny - y) / after * k2}`;
  }).join('');
  for (const edge of map.edges) {
    const a = position.get(edge.start), b = position.get(edge.end), own = [edge.start, edge.end];
    // Within a column, a link that would pass behind another card runs beside the column instead:
    // out of its source's free side, along the column, into the same side of its target.
    const lane = arrow => {
      const members = map.nodes.filter(item => item.column === a.column);
      const free = side => [a, b].every(end => !members.some(item => item.y === end.y && (item.x - end.x) * side > 0));
      const side = free(-1) ? -1 : free(1) ? 1 : 0;
      if (!side) return null;
      const x = side < 0 ? Math.min(...members.map(item => item.x)) - 16 : Math.max(...members.map(item => item.x)) + width + 16;
      const out = side < 0 ? a.x : a.x + width, into = (side < 0 ? b.x : b.x + width) + side * (arrow ? head : 0);
      return rounded([[out, a.y + height / 2], [x, a.y + height / 2], [x, b.y + height / 2], [into, b.y + height / 2]]);
    };
    let path;
    if (edge.kind === 'contrasts') {
      const straight = [[a.x + width / 2, a.y + height / 2], [b.x + width / 2, b.y + height / 2]];
      path = (a.column === b.column && a.y !== b.y && crosses(along(straight), own) && lane(false))
        || `M${straight[0][0]} ${straight[0][1]}L${straight[1][0]} ${straight[1][1]}`;
    } else if (a.column !== b.column) {
      const forward = b.column > a.column, side = forward ? 1 : -1, x1 = forward ? a.x + width : a.x;
      const x2 = (forward ? b.x : b.x + width) - side * head, y1 = a.y + height / 2, y2 = b.y + height / 2;
      const x3 = x2 - side * stub, bend = (x3 - x1) / 2;
      if (!crosses(sampled([x1, y1], [x1 + bend, y1], [x3 - bend, y2], [x3, y2]), [edge.start, edge.end])) {
        path = `M${x1} ${y1}C${x1 + bend} ${y1} ${x3 - bend} ${y2} ${x3} ${y2}L${x2} ${y2}`;
      } else {
        const out = x1 + side * 14, into = x3 - side * 14;
        // Two corners: across at the source's height, along a column gap, then into the target.
        const turns = [...channels.filter(x => (x - out) * side > 0 && (into - x) * side > 0)
          .sort((p, q) => Math.abs(p - (x1 + x3) / 2) - Math.abs(q - (x1 + x3) / 2)), into, out]
          .map(x => [[x1, y1], [x, y1], [x, y2], [x2, y2]]).find(points => !crosses(along(points), own));
        const gap = y2 < y1 ? b.y + height + rowGap / 2 : y2 > y1 ? b.y - rowGap / 2 : a.y + height + rowGap / 2;
        path = rounded(turns || [[x1, y1], [out, y1], [out, gap], [into, gap], [into, y2], [x2, y2]]);
      }
    } else if (b.y > a.y + height) {
      const x1 = a.x + width / 2, y1 = a.y + height, x2 = b.x + width / 2, y2 = b.y - head, y3 = y2 - stub, middle = (y1 + y3) / 2;
      path = (crosses(sampled([x1, y1], [x1, middle], [x2, middle], [x2, y3]), own) && lane(true))
        || `M${x1} ${y1}C${x1} ${middle} ${x2} ${middle} ${x2} ${y3}L${x2} ${y2}`;
    } else {
      const x1 = a.x + width, y1 = a.y + height / 2, x2 = b.x, y2 = b.y + height / 2, length = Math.hypot(x2 - x1, y2 - y1) || 1;
      path = `M${x1} ${y1}L${x2 - (x2 - x1) * head / length} ${y2 - (y2 - y1) * head / length}`;
    }
    const line = svgNode('path', { d: path, class: `exam-edge ${edge.kind}`, 'data-edge': '', 'data-start': edge.start, 'data-end': edge.end, 'aria-hidden': 'true' });
    if (edge.kind !== 'contrasts') line.setAttribute('marker-end', 'url(#exam-arrow)');
    svg.append(line);
  }
  for (const item of ordered) {
    const concept = concepts.get(item.key);
    const group = svgNode('g', { class: `exam-node ${concept.tier}`, transform: `translate(${item.x} ${item.y})`, tabindex: 0, role: 'button', 'aria-pressed': 'false', 'aria-label': describe(item.key), 'data-concept': item.key, 'data-topic': concept.topic });
    group.append(svgNode('rect', { width, height, rx: 8 }));
    const text = svgNode('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle' });
    const rows = lines(plainTitle(item.key));
    rows.forEach((row, index) => { const span = svgNode('tspan', { x: width / 2, dy: index === 0 ? `${(1 - rows.length) * 0.6 + 0.35}em` : '1.2em' }); span.textContent = row; text.append(span); });
    group.append(text);
    group.addEventListener('click', () => select(item.key));
    group.addEventListener('focus', () => reveal(item));
    group.addEventListener('keydown', event => {
      const index = ordered.findIndex(entry => entry.key === item.key);
      const next = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); const details = card.querySelector('.exam-entry-details');
        if (selected === item.key && details) { details.open = !details.open; } else select(item.key); }
      else if (next) { event.preventDefault(); elements.get(ordered[(index + next + ordered.length) % ordered.length].key).focus(); }
    });
    elements.set(item.key, group); svg.append(group);
  }
  // The canvas: a viewBox over the build-time layout that the student moves and zooms.
  const view = { x: 0, y: 0, scale: 1 };
  const clamp = value => Math.min(3, Math.max(0.2, value));
  let fitted = false;
  function apply() {
    const width = scroller.clientWidth, height = scroller.clientHeight;
    if (width && height) svg.setAttribute('viewBox', `${view.x} ${view.y} ${width / view.scale} ${height / view.scale}`);
  }
  // Fit shows the whole map. Opening it, a map too wide to read whole starts at a readable size
  // on its first topics, and the student drags along the semester.
  function fit(whole = true) {
    const width = scroller.clientWidth, height = scroller.clientHeight;
    if (!width || !height) return;
    const all = Math.min((width - 32) / map.width, (height - 32) / map.height, 1.25);
    view.scale = clamp(whole ? all : Math.max(all, READABLE));
    const centre = (size, room) => size * view.scale <= room - 32 ? (size - room / view.scale) / 2 : -16 / view.scale;
    view.x = centre(map.width, width); view.y = centre(map.height, height);
    fitted = true; apply();
  }
  function zoomAt(factor, cx = scroller.clientWidth / 2, cy = scroller.clientHeight / 2) {
    const wx = view.x + cx / view.scale, wy = view.y + cy / view.scale;
    view.scale = clamp(view.scale * factor); view.x = wx - cx / view.scale; view.y = wy - cy / view.scale; apply();
  }
  function pan(dx, dy) { view.x -= dx / view.scale; view.y -= dy / view.scale; apply(); }
  function reveal(item) {
    const width = scroller.clientWidth / view.scale, height = scroller.clientHeight / view.scale;
    const inside = item.x >= view.x && item.y >= view.y && item.x + map.node_width <= view.x + width && item.y + map.node_height <= view.y + height;
    if (!inside) { view.x = item.x + map.node_width / 2 - width / 2; view.y = item.y + map.node_height / 2 - height / 2; apply(); }
  }
  const pointers = new Map();
  let travelled = 0, spread = 0, suppressClick = false;
  const local = event => { const box = scroller.getBoundingClientRect(); return [event.clientX - box.left, event.clientY - box.top]; };
  scroller.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    pointers.set(event.pointerId, [event.clientX, event.clientY]); travelled = 0;
    if (pointers.size === 2) { const [[ax, ay], [bx, by]] = pointers.values(); spread = Math.hypot(ax - bx, ay - by); }
  });
  scroller.addEventListener('pointermove', event => {
    const last = pointers.get(event.pointerId);
    if (!last) return;
    pointers.set(event.pointerId, [event.clientX, event.clientY]);
    if (pointers.size === 2) {
      const [[ax, ay], [bx, by]] = pointers.values(), distance = Math.hypot(ax - bx, ay - by);
      const box = scroller.getBoundingClientRect();
      if (spread) zoomAt(distance / spread, (ax + bx) / 2 - box.left, (ay + by) / 2 - box.top);
      spread = distance; travelled = Infinity; return;
    }
    const dx = event.clientX - last[0], dy = event.clientY - last[1];
    travelled += Math.abs(dx) + Math.abs(dy);
    if (travelled > 4) {
      if (!scroller.hasPointerCapture(event.pointerId)) { scroller.setPointerCapture(event.pointerId); scroller.classList.add('panning'); }
      pan(dx, dy);
    }
  });
  const release = event => {
    if (!pointers.delete(event.pointerId)) return;
    if (travelled > 4) suppressClick = true;
    if (!pointers.size) scroller.classList.remove('panning');
    spread = 0;
  };
  scroller.addEventListener('pointerup', release); scroller.addEventListener('pointercancel', release);
  // A drag ends with a click on whatever is under the pointer; it must not select a node.
  scroller.addEventListener('click', event => { if (suppressClick) { suppressClick = false; event.stopPropagation(); event.preventDefault(); } }, true);
  scroller.addEventListener('wheel', event => {
    const full = root.classList.contains('expanded');
    if (!(event.ctrlKey || event.metaKey) && !full) return;
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) zoomAt(Math.exp(-event.deltaY * 0.0025), ...local(event)); else pan(-event.deltaX, -event.deltaY);
  }, { passive: false });
  scroller.addEventListener('keydown', event => {
    if (event.target !== scroller) return;
    const step = 48, moves = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    if (moves[event.key]) pan(...moves[event.key]);
    else if (event.key === '+' || event.key === '=') zoomAt(1.25);
    else if (event.key === '-') zoomAt(0.8);
    else if (event.key === '0') fit();
    else return;
    event.preventDefault();
  });
  const full = tool('Full screen', ICONS.enter, () => toggleFull(), 'exam-map-full');
  function toggleFull() {
    if (document.fullscreenElement === root) { document.exitFullscreen(); return; }
    if (root.classList.contains('expanded')) { setExpanded(false); return; }
    if (root.requestFullscreen) root.requestFullscreen().catch(() => setExpanded(true)); else setExpanded(true);
  }
  function setExpanded(on) {
    root.classList.toggle('expanded', on);
    const name = on ? 'Exit full screen' : 'Full screen';
    full.setAttribute('aria-label', name); full.title = name; full.querySelector('path').setAttribute('d', on ? ICONS.exit : ICONS.enter);
    requestAnimationFrame(() => fit(false));
  }
  const onFullscreen = () => {
    if (!root.isConnected) { document.removeEventListener('fullscreenchange', onFullscreen); return; }
    setExpanded(document.fullscreenElement === root);
  };
  document.addEventListener('fullscreenchange', onFullscreen);
  root.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    // Escape closes the details first, then leaves full screen.
    if (!card.hidden) { event.preventDefault(); deselect(); return; }
    if (root.classList.contains('expanded') && !document.fullscreenElement) { setExpanded(false); full.focus(); }
  });
  heading.append(full);
  const tools = append(node('div', 'exam-map-tools'), tool('Zoom out', ICONS.out, () => zoomAt(0.8)), tool('Zoom in', ICONS.in, () => zoomAt(1.25)), tool('Fit', ICONS.fit, () => fit()));
  const legend = append(node('div', 'exam-map-legend'), legendItem(false, 'builds on'), legendItem(true, 'easy to confuse'));
  new ResizeObserver((entries, observer) => {
    if (!scroller.isConnected) { observer.disconnect(); return; }
    if (fitted) apply(); else fit(false);
  }).observe(scroller);
  scroller.append(svg);
  // Phones show topics first; a topic opens its concepts as a list.
  const overview = node('div', 'exam-map-overview');
  for (const topic of topics) {
    const members = ordered.filter(item => concepts.get(item.key).topic === topic.key);
    if (!members.length) continue;
    const group = node('details', 'exam-map-topic');
    const crossing = exam.map.overview.links.filter(link => link.start === topic.key || link.end === topic.key).reduce((sum, link) => sum + link.count, 0);
    group.append(append(node('summary'), studyText('span', 'exam-map-topic-title', topic.title), node('span', 'small', `${members.length} idea${members.length === 1 ? '' : 's'}${crossing ? ` · ${crossing} link${crossing === 1 ? '' : 's'} to other topics` : ''}`)));
    const items = node('ul', 'exam-map-topic-list');
    for (const item of members) {
      const control = button('', () => select(item.key), 'quiet exam-map-item');
      control.append(studyText('span', '', concepts.get(item.key).title), node('span', 'small', conceptBadge(concepts.get(item.key))));
      control.setAttribute('aria-label', describe(item.key));
      items.append(append(node('li'), control));
    }
    group.append(items); overview.append(group);
  }
  root.append(append(node('div', 'exam-map-frame'), scroller, tools, legend), overview, card, status);
  return root;
}
