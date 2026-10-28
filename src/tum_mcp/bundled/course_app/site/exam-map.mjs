import { node, svgNode, studyText, button, append } from './dom.mjs';
import { exam, concepts, topics, conceptBadge, quietLink } from './exam-state.mjs';

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

// The semester map: build-time positions, focusable nodes and a compact card for the selection.
export function renderMap(onOpen) {
  const map = exam.map;
  const root = node('section', 'exam-map'); root.setAttribute('aria-labelledby', 'exam-map-title');
  const title = node('h2', '', 'Semester map'); title.id = 'exam-map-title';
  root.append(append(node('div', 'section-heading'), title));
  if (!map?.nodes?.length) { root.hidden = true; return root; }
  root.append(node('p', 'small', 'Arrows run from a foundation to what builds on it; dashed lines join ideas that are easy to confuse.'));
  const links = new Map(map.nodes.map(item => [item.key, []]));
  for (const edge of map.edges) { links.get(edge.start).push({ ...edge, other: edge.end, out: true }); links.get(edge.end).push({ ...edge, other: edge.start, out: false }); }
  const card = node('div', 'exam-map-card'); card.setAttribute('role', 'status'); card.hidden = true;
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
    card.replaceChildren(
      append(node('p', 'exam-map-card-title'), studyText('strong', '', concept.title), node('span', 'small', ` · ${conceptBadge(concept)}`)),
      studyText('p', '', concept.line),
    );
    if (concept.trigger) card.append(append(node('p', 'small'), node('span', 'exam-label', 'When you see: '), studyText('span', '', concept.trigger)));
    card.append(quietLink('Open in the cheatsheet', `#exam/sheet/${concept.key}`));
    card.hidden = false;
    if (focus) elements.get(key).focus();
  }
  const scroller = node('div', 'exam-map-scroll'); scroller.tabIndex = -1;
  const svg = svgNode('svg', { viewBox: `0 0 ${map.width} ${map.height}`, width: map.width, height: map.height, class: 'exam-map-svg', role: 'group', 'aria-label': 'Semester map of exam-relevant ideas' });
  const defs = svgNode('defs'), marker = svgNode('marker', { id: 'exam-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
  marker.append(svgNode('path', { d: 'M0 0L10 5L0 10z', class: 'exam-arrow-head' })); defs.append(marker); svg.append(defs);
  for (const column of map.columns) {
    const label = svgNode('text', { x: column.x, y: 24, class: 'exam-map-column' }); label.textContent = studyText('span', '', column.title).textContent;
    svg.append(label);
  }
  const position = new Map(map.nodes.map(item => [item.key, item]));
  const width = map.node_width, height = map.node_height;
  for (const edge of map.edges) {
    const a = position.get(edge.start), b = position.get(edge.end);
    let path;
    if (edge.kind === 'contrasts') path = `M${a.x + width / 2} ${a.y + height / 2}L${b.x + width / 2} ${b.y + height / 2}`;
    else if (a.column !== b.column) {
      const forward = b.column > a.column, x1 = forward ? a.x + width : a.x, x2 = forward ? b.x : b.x + width;
      const y1 = a.y + height / 2, y2 = b.y + height / 2, bend = (x2 - x1) / 2;
      path = `M${x1} ${y1}C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`;
    } else {
      const x1 = a.x + width / 2, y1 = a.y + height, x2 = b.x + width / 2, y2 = b.y, middle = (y1 + y2) / 2;
      path = y2 > y1 ? `M${x1} ${y1}C${x1} ${middle} ${x2} ${middle} ${x2} ${y2}` : `M${a.x + width} ${a.y + height / 2}L${b.x} ${b.y + height / 2}`;
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
    group.addEventListener('keydown', event => {
      const index = ordered.findIndex(entry => entry.key === item.key);
      const next = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (selected === item.key) onOpen(item.key); else select(item.key); }
      else if (next) { event.preventDefault(); elements.get(ordered[(index + next + ordered.length) % ordered.length].key).focus(); }
    });
    elements.set(item.key, group); svg.append(group);
  }
  let scale = 1;
  const zoom = factor => () => {
    scale = factor === 0 ? 1 : Math.min(2, Math.max(0.5, scale * factor));
    svg.setAttribute('width', String(Math.round(map.width * scale))); svg.setAttribute('height', String(Math.round(map.height * scale)));
  };
  const controls = append(node('div', 'cluster exam-map-controls'), button('Zoom out', zoom(0.8), 'quiet'), button('Reset zoom', zoom(0), 'quiet'), button('Zoom in', zoom(1.25), 'quiet'));
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
  root.append(controls, scroller, overview, card);
  // Start fitted to the frame when the map is wider than the reading column.
  requestAnimationFrame(() => {
    const available = scroller.clientWidth - 2;
    if (available > 0 && map.width > available) { scale = Math.max(0.8, available / map.width); zoom(1)(); }
  });
  return root;
}
