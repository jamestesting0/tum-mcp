// Measures what the course app painted for every visual on the open page. Each visual gets the
// findings an author must fix (a line through a node, labels that clash or sit on a foreign line,
// text under 12 px, clipped text) and, when its authored block is given, whether the drawing
// shows exactly the authored nodes, edges and labels.
({ step = '', expected = {} } = {}) => {
  const results = [];
  const rect = element => element.getBoundingClientRect();
  const area = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const shrink = (r, by) => ({ left: r.left + by, right: r.right - by, top: r.top + by, bottom: r.bottom - by });
  const inside = (p, r) => p[0] > r.left && p[0] < r.right && p[1] > r.top && p[1] < r.bottom;
  const say = element => (element.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  const textSize = text => {
    const size = parseFloat(getComputedStyle(text).fontSize) || 0, ctm = text.getScreenCTM?.();
    return ctm ? size * Math.hypot(ctm.a, ctm.b) : size;
  };
  // Points along a stroke in screen pixels, leaving out a few pixels at each end.
  const samples = (path, trim = 8) => {
    const ctm = path.getScreenCTM(), length = path.getTotalLength?.() || 0, points = [];
    if (!ctm || !length) return points;
    const scale = Math.hypot(ctm.a, ctm.b) || 1, step = Math.max(1.5, length / 240);
    for (let at = trim / scale; at <= length - trim / scale; at += step) {
      const p = path.getPointAtLength(at);
      points.push([ctm.a * p.x + ctm.c * p.y + ctm.e, ctm.b * p.x + ctm.d * p.y + ctm.f]);
    }
    return points;
  };
  // The authored block a visual comes from: a lesson block, an exercise statement or step
  // block, the step's answer graph, or a block drawn in place by the check itself.
  const idOf = root => {
    const injected = root.closest('[data-visual-id]');
    if (injected) return injected.dataset.visualId;
    const section = root.closest('[data-block-index]'), index = section?.dataset.blockIndex ?? '0';
    const optional = root.closest('[data-explore-key]');
    if (optional) return `explore:${optional.dataset.exploreKey}:${index}`;
    if (root.closest('#exercise-question')) return `statement:${index}`;
    const body = root.closest('.step-body');
    if (body) return section && body.contains(section) ? `step:${step}:${index}` : `step:${step}:check`;
    return `block:${index}`;
  };
  const roots = [...document.querySelectorAll('main svg.graph, main .uml-region, main .plot-drawing > svg, main figure.figure > svg, main figure.figure > img, main .table-region')]
    .filter(root => root.getClientRects().length && !root.closest('details:not([open])'));
  for (const root of roots) {
    const kind = root.matches('.uml-region') ? 'uml' : root.matches('svg.graph') ? 'diagram' : root.closest('.plot') ? 'plot' : root.matches('.table-region') ? 'table' : 'figure';
    const id = idOf(root), container = root.closest('[data-visual-id], .reading-material, [data-block-index]') || root.parentElement;
    container.dataset.visualShot = id;
    const heading = container.querySelector('h2, h3, legend') || root.closest('.step-body')?.querySelector('h2');
    const entry = { id, kind, title: heading ? say(heading) : '', findings: [], facts: {} };
    const add = (code, detail) => { if (!entry.findings.some(item => item.code === code && item.detail === detail)) entry.findings.push({ code, detail }); };
    results.push(entry);
    const region = kind === 'uml' ? root : root.closest('.graph-region, .table-region, .plot-drawing, figure') || root;
    const bounds = rect(root);
    Object.assign(entry.facts, { width: Math.round(bounds.width), height: Math.round(bounds.height), scrolls: region.scrollWidth > region.clientWidth + 2 });
    if (bounds.height > 1.5 * innerHeight) add('tall_visual', `${Math.round(bounds.height)} px tall, more than one and a half screens`);
    if (entry.facts.scrolls && kind !== 'table') add('scrolls', `${region.scrollWidth} px wide in a ${region.clientWidth} px column; it scrolls sideways`);
    for (const caption of container.querySelectorAll('figcaption, caption, .diagram-caption, .frame-caption')) {
      if (caption.scrollWidth > caption.clientWidth + 1 && getComputedStyle(caption).overflowX !== 'visible') add('clipped_text', `the caption "${say(caption)}" is cut off`);
    }
    if (kind === 'uml' && root.dataset.layout === 'failed') { add('render_error', say(root)); continue; }
    if (kind === 'table') {
      const cells = [...root.querySelectorAll('td, th')];
      const tall = cells.filter(cell => rect(cell).height > 4.5 * (parseFloat(getComputedStyle(cell).lineHeight) || 24));
      if (tall.length) add('tall_cell', `${tall.length} cells wrap to more than four lines`);
      if (entry.facts.scrolls && innerWidth < 500) add('table_scrolls', 'the table is wider than a phone screen');
      continue;
    }
    const svg = kind === 'uml' ? root.querySelector('svg') : root.matches('svg') ? root : null;
    if (!svg) continue;
    const frame = rect(svg), texts = [...svg.querySelectorAll('text')].filter(text => text.textContent.trim());
    const sizes = texts.map(textSize).filter(Boolean);
    entry.facts.minTextPx = sizes.length ? Math.round(Math.min(...sizes) * 10) / 10 : null;
    if (sizes.length && Math.min(...sizes) < 11.9) add('tiny_text', `smallest text ${entry.facts.minTextPx} px`);
    // Text boxes overlapping each other; the lines inside one node or message belong together.
    const boxes = texts.map(rect), owner = text => text.closest('[data-node], [data-node-key], .uml-participant, .uml-message');
    for (let i = 0; i < texts.length; i++) {
      if (boxes[i].left < frame.left - 1 || boxes[i].right > frame.right + 1 || boxes[i].top < frame.top - 1 || boxes[i].bottom > frame.bottom + 1) add('clipped_text', `"${say(texts[i])}" runs past the drawing's edge`);
      for (let j = i + 1; j < texts.length; j++) {
        if (owner(texts[i]) && owner(texts[i]) === owner(texts[j])) continue;
        if (area(boxes[i], boxes[j]) > 6) add('label_overlap', `"${say(texts[i])}" overlaps "${say(texts[j])}"`);
      }
    }
    if (kind === 'plot') {
      // Labels the plot places itself (notes, shaded-area values, direct labels) must not sit on a curve.
      const strokes = [...svg.querySelectorAll('polyline.plot-line, line.plot-stem, line.plot-axis')].map(line => samples(line, 0));
      for (const label of svg.querySelectorAll('text.plot-strong, text.plot-value')) {
        if (label.previousElementSibling?.matches('rect.plot-knockout')) continue;
        const r = shrink(rect(label), 1);
        if (strokes.some(points => points.some(p => inside(p, r)))) add('label_on_line', `"${say(label)}" sits on a curve`);
      }
      const block = expected[id];
      if (block && (block.notes || []).length !== svg.querySelectorAll('circle.plot-mark').length) add('fidelity', 'a marked point is missing');
      continue;
    }
    if (kind === 'figure') continue;
    const nodes = kind === 'diagram'
      ? [...svg.querySelectorAll('g[data-node-key]')].map(group => ({ key: group.dataset.nodeKey, rect: rect(group.firstElementChild) }))
      : [...svg.querySelectorAll('g[data-node]')].map(group => ({ key: group.dataset.node, rect: rect(group.firstElementChild) }));
    const edges = kind === 'diagram'
      ? [...svg.querySelectorAll('path.edge')].map(path => ({ key: path.dataset.edgeKey, ends: path.dataset.edgeKey.split('--'), points: samples(path) }))
      : [...svg.querySelectorAll('.uml-edge path.uml-line')].map(path => ({ key: path.closest('[data-edge]').dataset.edge, ends: [], points: samples(path, 14) }));
    // An edge that runs through a node it does not connect.
    for (const edge of edges) for (const n of nodes) {
      if (edge.ends.includes(n.key)) continue;
      const hits = edge.points.filter(p => inside(p, shrink(n.rect, 4))).length;
      if (hits > 2 && (kind === 'diagram' || !edge.points.slice(0, 3).concat(edge.points.slice(-3)).some(p => inside(p, shrink(n.rect, -6))))) add('edge_through_node', `an edge crosses ${n.key}`);
    }
    // Two edges drawn on top of each other for a stretch read as one.
    if (kind === 'diagram') for (let i = 0; i < edges.length; i++) for (let j = i + 1; j < edges.length; j++) {
      const shared = edges[i].points.filter(p => edges[j].points.some(q => Math.hypot(p[0] - q[0], p[1] - q[1]) < 2.5)).length;
      if (shared > 12) add('coincident_edges', `${edges[i].key} runs along ${edges[j].key}`);
    }
    // Every arrowhead has a size; a zero-length one leaves a relation without its direction.
    const heads = kind === 'diagram' ? [...svg.querySelectorAll('path.arrow')] : [...svg.querySelectorAll('.uml-edge path:not(.uml-line)')];
    if (heads.some(head => { const r = rect(head); return r.width < 2 && r.height < 2; })) add('fidelity', 'an arrowhead is drawn without size, so its direction is lost');
    // A label printed on a line, unless a knockout behind it opens the line (inline UML labels).
    const labels = kind === 'diagram' ? [...svg.querySelectorAll('text.edge-label')] : texts.filter(text => !text.closest('g[data-node], .uml-participant, .uml-message') && !text.previousElementSibling?.matches?.('rect.uml-knockout'));
    for (const label of labels) {
      const r = shrink(rect(label), 1);
      if (edges.some(edge => edge.points.some(p => inside(p, r)))) add('label_on_line', `"${say(label)}" sits on a line`);
      if (nodes.some(n => area(r, n.rect) > 4)) add('label_on_node', `"${say(label)}" covers a node`);
    }
    // The picture shows what was authored: every node, edge, arrow and label, nothing more.
    const block = expected[id];
    if (!block) continue;
    const differ = (what, painted, authored) => {
      const a = [...painted].sort().join('|'), b = [...authored].sort().join('|');
      if (a !== b) add('fidelity', `${what} drawn differ from the block`);
    };
    if (kind === 'diagram') {
      differ('nodes', nodes.map(n => n.key), block.nodes.map(n => n.key));
      differ('node labels', [...svg.querySelectorAll('g[data-node-key] text')].map(text => [...text.querySelectorAll('tspan')].map(span => span.textContent).join(' ') || text.textContent), block.nodes.map(n => n.label.replace(/\s+/g, ' ')));
      differ('edges', edges.map(edge => edge.key), block.edges.map(edge => `${edge.start}--${edge.end}`));
      differ('arrows', [...svg.querySelectorAll('path.arrow')].map(arrow => arrow.dataset.arrowKey), block.edges.filter(edge => edge.directed).map(edge => `${edge.start}--${edge.end}`));
      differ('edge labels', [...svg.querySelectorAll('text.edge-label')].map(text => text.textContent), block.edges.filter(edge => edge.label).map(edge => edge.label));
    } else if (block.diagram === 'sequence') {
      differ('participants', [...svg.querySelectorAll('[data-participant]')].map(group => group.dataset.participant), block.participants.map(item => item.key));
      if (svg.querySelectorAll('.uml-message').length !== block.messages.length) add('fidelity', 'messages drawn differ from the block');
    } else {
      const [items, links] = { class: [block.classes, block.relations], state: [block.states, block.transitions], flowchart: [block.steps, block.flows] }[block.diagram] || [[], []];
      differ('elements', nodes.map(n => n.key), items.map(item => item.key));
      if (svg.querySelectorAll('g[data-edge]').length !== links.length) add('fidelity', 'relations drawn differ from the block');
    }
  }
  return results;
}
