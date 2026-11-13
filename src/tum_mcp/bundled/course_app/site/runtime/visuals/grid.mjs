import { svgNode, plainText } from '../shell/dom.mjs';

// Grids side by side in one drawing, so a move can run from a cell of one grid to a cell of
// another. Cells are addressed "row:column" from 1; the drawn labels are the author's.
const CELL = 52, GAP = 56, TITLE = 30, INDEX = 24, PAD = 4, CAPTION = 28;
let drawings = 0;

export function drawGrids(block, { captions = (block.arrows || []).some(arrow => arrow.label) } = {}) {
  const id = `grid-${++drawings}`;
  const boxes = new Map();
  let x = PAD;
  const titled = block.grids.some(grid => grid.label);
  const indexTop = block.grids.some(grid => grid.col_labels?.length);
  const top = PAD + (titled ? TITLE : 0) + (indexTop ? INDEX : 0);
  for (const grid of block.grids) {
    const left = x + (grid.row_labels?.length ? INDEX : 0);
    const columns = grid.cells[0].length;
    boxes.set(grid.key, { grid, left, top });
    x = left + columns * CELL + GAP;
  }
  const width = x - GAP + PAD;
  const bottom = top + Math.max(...block.grids.map(grid => grid.cells.length)) * CELL;
  const captionY = bottom + CAPTION / 2 + PAD;
  const height = bottom + (captions ? CAPTION + PAD : 0) + PAD;
  const svg = svgNode('svg', { class: 'grid-figure', viewBox: `0 0 ${width} ${height}`, width, role: 'img', 'aria-label': plainText(block.description) });
  const defs = svgNode('defs');
  const head = svgNode('marker', { id: `${id}-head`, viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
  head.append(svgNode('path', { d: 'M0 1L9 5L0 9z', class: 'grid-arrow-head' }));
  defs.append(head);
  svg.append(defs);

  // Arrows run between the cell fills and the values, so a value is never hidden.
  const fills = svgNode('g'), arrows = svgNode('g', { class: 'grid-arrows' }), labels = svgNode('g');
  const cells = new Map(), texts = new Map();
  for (const { grid, left } of boxes.values()) {
    const columns = grid.cells[0].length;
    if (grid.label) svg.append(text(left + columns * CELL / 2, PAD + TITLE / 2, grid.label, 'grid-title'));
    (grid.col_labels || []).forEach((label, column) => svg.append(text(left + (column + .5) * CELL, top - INDEX / 2, label, 'grid-index')));
    (grid.row_labels || []).forEach((label, row) => svg.append(text(left - INDEX / 2, top + (row + .5) * CELL, label, 'grid-index')));
    const shaded = new Set(grid.shaded || []);
    grid.cells.forEach((values, row) => values.forEach((value, column) => {
      const ref = `${row + 1}:${column + 1}`, key = `${grid.key}:${ref}`;
      const kind = `grid-cell${shaded.has(ref) ? ' shaded' : ''}`;
      const group = svgNode('g', { class: kind, 'data-cell': key }), front = svgNode('g', { class: kind });
      group.append(svgNode('rect', { x: left + column * CELL, y: top + row * CELL, width: CELL, height: CELL }));
      const label = text(left + (column + .5) * CELL, top + (row + .5) * CELL, value, 'grid-value');
      front.append(label);
      fills.append(group); labels.append(front);
      cells.set(key, [group, front]); texts.set(key, label);
    }));
  }
  const notes = svgNode('g');
  svg.append(fills, arrows, labels, notes);

  const place = point => {
    const box = boxes.get(point.grid), [row, column] = point.cell.split(':').map(Number);
    const x = box.left + (column - 1) * CELL, y = box.top + (row - 1) * CELL;
    return { box, x, y, cx: x + CELL / 2, cy: y + CELL / 2 };
  };
  // Arrows run along the cell edges, never through a cell's middle where its value sits.
  // They leave the start cell from its edge facing the target, run along the row edge, then
  // along the target column's near edge, and end at the middle of the target's side.
  function drawArrow(arrow) {
    const from = place(arrow.start), to = place(arrow.end);
    let points;
    if (from.cx === to.cx) {
      points = [[from.x, from.cy], [from.x, to.cy]];
    } else if (from.cy === to.cy) {
      points = [[from.cx, from.y], [to.cx, from.y]];
    } else {
      const lane = to.cy > from.cy ? from.y + CELL : from.y;
      const side = to.cx > from.cx ? to.x : to.x + CELL;
      points = [[from.cx, lane], [side, lane], [side, to.cy]];
    }
    const d = points.map(([x, y], index) => `${index ? 'L' : 'M'}${x} ${y}`).join('');
    arrows.append(svgNode('path', { d, class: 'grid-arrow-casing' }), svgNode('path', { d, class: 'grid-arrow', 'marker-end': `url(#${id}-head)` }));
  }
  // Labels go in the caption row under the grid the move starts in, clear of every cell.
  function drawLabels(moves) {
    const byGrid = new Map();
    for (const arrow of moves.filter(item => item.label)) {
      byGrid.set(arrow.start.grid, [...(byGrid.get(arrow.start.grid) || []), plainText(arrow.label)]);
    }
    for (const [key, texts] of byGrid) {
      const { grid, left } = boxes.get(key);
      notes.append(text(left + grid.cells[0].length * CELL / 2, captionY, texts.join('  ·  '), 'grid-arrow-label'));
    }
  }

  function show({ marks = [], arrows: moves = [], values = new Map() } = {}) {
    for (const [key, parts] of cells) {
      for (const part of parts) part.classList.remove('active', 'frontier', 'visited', 'path');
      const authored = block.grids.find(grid => key.startsWith(`${grid.key}:`));
      const [row, column] = key.slice(authored.key.length + 1).split(':').map(Number);
      texts.get(key).textContent = values.has(key) ? values.get(key) : authored.cells[row - 1][column - 1];
    }
    for (const mark of marks) for (const part of cells.get(`${mark.grid}:${mark.cell}`) || []) part.classList.add(mark.mark || 'active');
    arrows.replaceChildren(); notes.replaceChildren();
    moves.forEach(drawArrow);
    drawLabels(moves);
  }
  show({ marks: block.marks || [], arrows: block.arrows || [] });
  return { svg, show };
}

function text(x, y, value, className) {
  const label = svgNode('text', { x, y, class: className });
  label.textContent = plainText(value);
  return label;
}
