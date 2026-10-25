import data from './data.mjs';
import { parseMath } from './mathml.mjs';

export function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}
export function studyText(tag, className = '', text = '') {
  const element = node(tag, className);
  let start = 0;
  for (const match of text.matchAll(/\\\((.*?)\\\)/gs)) {
    element.append(text.slice(start, match.index));
    const markup = Object.hasOwn(data.inlineMath || {}, match[1]) && data.inlineMath[match[1]], math = markup && parseMath(markup);
    if (math) { math.setAttribute('display', 'inline'); math.classList.add('inline-math'); element.append(math); }
    else element.append(match[0]);
    start = match.index + match[0].length;
  }
  element.append(text.slice(start)); return element;
}
export function button(label, handler, className = '') {
  const element = node('button', className, label);
  element.type = 'button';
  element.addEventListener('click', handler);
  return element;
}
export function append(parent, ...children) { parent.append(...children); return parent; }
export function focusHeading(heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
let announcer;
// Announces a change whose visible element is replaced, such as advancing to the next card.
export function announce(message) {
  if (!announcer?.isConnected) {
    announcer = node('p', 'visually-hidden'); announcer.setAttribute('aria-live', 'polite'); document.body.append(announcer);
  }
  announcer.textContent = '';
  requestAnimationFrame(() => { announcer.textContent = message; });
}
export function sourcesNote(ids, sources, synthetic) {
  const note = node('p', 'source-note');
  const items = [];
  for (const id of ids) {
    const source = sources[id];
    if (!source) continue;
    const label = `${source.title}${source.locator ? ` · ${source.locator}` : ''}`;
    if (synthetic) { items.push(document.createTextNode(label)); continue; }
    const url = new URL(source.url);
    if (!['http:', 'https:'].includes(url.protocol)) continue;
    const link = node('a', '', label);
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    items.push(link);
  }
  note.append(`${synthetic ? 'Synthetic source' : 'Source'}${items.length === 1 ? '' : 's'}: `);
  items.forEach((item, index) => { if (index) note.append('; '); note.append(item); });
  return note;
}
