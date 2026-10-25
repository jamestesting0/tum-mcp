export function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}
export function button(label, handler, className = '') {
  const element = node('button', className, label);
  element.type = 'button';
  element.addEventListener('click', handler);
  return element;
}
export function append(parent, ...children) { parent.append(...children); return parent; }
export function focusHeading(heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
export function sourcesNote(ids, sources, synthetic) {
  const detail = node('details', 'source-note');
  detail.append(node('summary', '', `${ids.length === 1 ? 'Source' : 'Sources'} · ${synthetic ? 'synthetic notes' : 'reference'}`));
  const list = node('ul');
  for (const id of ids) {
    const source = sources[id];
    if (!source) continue;
    const item = node('li');
    const label = `${source.title}${source.locator ? ` · ${source.locator}` : ''}`;
    if (synthetic) item.append(node('span', '', label));
    else {
      const url = new URL(source.url);
      if (!['http:', 'https:'].includes(url.protocol)) continue;
      const link = node('a', '', label);
      link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
      item.append(link);
    }
    list.append(item);
  }
  detail.append(list);
  return detail;
}
