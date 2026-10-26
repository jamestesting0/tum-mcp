import { node, studyText, append, svgNode } from './dom.mjs';

export const plotNumber = value => value && (Math.abs(value) >= 10000 || Math.abs(value) < .001) ? value.toExponential(2).replace(/\.?0+e/, 'e') : Number(value.toPrecision(5)).toString();
const marks = ['none', '8 5', '2 4', '12 4 2 4', '4 3'];

export function renderPlot(block) {
  const root = node('div', 'plot'), graph = svgNode('svg', { viewBox: '0 0 600 360', role: 'img', 'aria-label': block.description });
  const area = { left: 72, right: 576, top: 24, bottom: 292 };
  const x = value => area.left + (value - block.x_min) / (block.x_max - block.x_min) * (area.right - area.left);
  const y = value => area.bottom - (value - block.y_min) / (block.y_max - block.y_min) * (area.bottom - area.top);
  function label(text, attributes) { const result = svgNode('text', attributes); result.textContent = text; graph.append(result); }
  graph.append(svgNode('rect', { x: area.left, y: area.top, width: area.right-area.left, height: area.bottom-area.top, class: 'plot-area' }));
  for (let i = 0; i <= 4; i++) {
    const xv = block.x_min + (block.x_max - block.x_min) * i / 4, yv = block.y_min + (block.y_max - block.y_min) * i / 4;
    graph.append(svgNode('line', { x1: x(xv), y1: area.top, x2: x(xv), y2: area.bottom, class: 'plot-grid' }), svgNode('line', { x1: area.left, y1: y(yv), x2: area.right, y2: y(yv), class: 'plot-grid' }));
    label(plotNumber(xv), { x: x(xv), y: area.bottom + 26, 'text-anchor': 'middle' });
    label(plotNumber(yv), { x: area.left - 12, y: y(yv) + 5, 'text-anchor': 'end' });
  }
  if (block.x_min < 0 && block.x_max > 0) graph.append(svgNode('line', { x1: x(0), y1: area.top, x2: x(0), y2: area.bottom, class: 'plot-axis' }));
  if (block.y_min < 0 && block.y_max > 0) graph.append(svgNode('line', { x1: area.left, y1: y(0), x2: area.right, y2: y(0), class: 'plot-axis' }));
  label(studyText('span', '', block.x_label).textContent, { x: (area.left + area.right) / 2, y: 352, 'text-anchor': 'middle' });
  const ylabel = svgNode('text', { transform: 'translate(18 158) rotate(-90)', 'text-anchor': 'middle' }); ylabel.textContent = studyText('span', '', block.y_label).textContent; graph.append(ylabel);
  const series = svgNode('g'); graph.append(series);
  for (const [index, line] of block.series.entries()) {
    const path = svgNode('polyline', { points: line.points.map(p => `${x(p.x)},${y(p.y)}`).join(' '), class: 'plot-line', 'stroke-dasharray': marks[index] });
    series.append(path);
  }
  root.append(graph);
  if (block.series.length > 1) {
    const legend = node('ul', 'plot-legend');
    block.series.forEach((line, i) => {
      const sample = svgNode('svg', {viewBox: '0 0 32 12', 'aria-hidden': 'true'});
      sample.append(svgNode('line', {x1:0, x2:32, y1:6, y2:6, class:'plot-line', 'stroke-dasharray':marks[i]}));
      legend.append(append(node('li'), sample, studyText('span', '', line.label)));
    }); root.append(legend);
  }
  root.append(studyText('p', 'small', block.description));
  if (block.series.length) {
    const details = node('details', 'plot-data'), table = node('table'), head = node('tr');
    details.append(node('summary', '', 'Data'));
    for (const title of ['Series', block.x_label, block.y_label]) { const th = studyText('th', '', title); th.scope = 'col'; head.append(th); }
    table.append(append(node('thead'), head)); const body = node('tbody');
    for (const line of block.series) for (const point of line.points) body.append(append(node('tr'), studyText('th', '', line.label), node('td', '', plotNumber(point.x)), node('td', '', plotNumber(point.y))));
    table.append(body); const region = node('div', 'table-region'); region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Graph data'); region.append(table); details.append(region); root.append(details);
  }
  return { root, graph, series, x, y, area };
}
