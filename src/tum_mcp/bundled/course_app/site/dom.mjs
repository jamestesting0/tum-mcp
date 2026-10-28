import data from './data.mjs';
import { parseMath } from './mathml.mjs';

export function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}
export function svgNode(tag, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
  return element;
}
export function studyText(tag, className = '', text = '') {
  const element = node(tag, className);
  let start = 0;
  // Inline math \( ... \) and inline code `...`; text inside backticks stays literal.
  for (const match of text.matchAll(/`([^`\n]+)`|\\\((.*?)\\\)/gs)) {
    element.append(text.slice(start, match.index));
    if (match[1] !== undefined) element.append(node('code', 'inline-code', match[1]));
    else {
      const markup = Object.hasOwn(data.inlineMath || {}, match[2]) && data.inlineMath[match[2]], math = markup && parseMath(markup);
      if (math) { math.setAttribute('display', 'inline'); math.classList.add('inline-math'); element.append(math); }
      else element.append(match[0]);
    }
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
// Destructive choices use one app dialog; Cancel has focus so Enter never confirms by accident.
export function confirmAction({ title, message, action, onConfirm, trigger }) {
  const dialog = node('dialog', 'confirm-dialog'), heading = node('h2', '', title);
  heading.id = `confirm-${crypto.randomUUID()}`; dialog.setAttribute('aria-labelledby', heading.id);
  const cancel = button('Cancel', () => dialog.close(), 'quiet');
  const confirm = button(action, () => { dialog.close(); onConfirm(); }, 'danger');
  dialog.append(heading, node('p', '', message), append(node('div', 'cluster dialog-actions'), cancel, confirm));
  dialog.addEventListener('close', () => { dialog.remove(); if (trigger?.isConnected) trigger.focus(); });
  document.body.append(dialog); dialog.showModal(); cancel.focus();
}
export function focusHeading(heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
export function scrollReadingTo(element) {
  const main = element.closest('main');
  if (!main || matchMedia('(max-width: 799px)').matches) element.scrollIntoView({ block: 'start' });
  else main.scrollTo({ top: main.scrollTop + element.getBoundingClientRect().top - main.getBoundingClientRect().top - (parseFloat(getComputedStyle(element).scrollMarginTop) || 0), behavior: 'instant' });
}
let announcer;
// Announces a change whose visible element is replaced, such as advancing to the next card.
export function announce(message) {
  if (!announcer?.isConnected) {
    announcer = node('p', 'visually-hidden'); announcer.setAttribute('aria-live', 'polite'); document.body.append(announcer);
  }
  announcer.textContent = '';
  requestAnimationFrame(() => { announcer.textContent = message; });
}
// `locators` maps a source id to nodes, such as measured recording times, that replace its general locator.
export function sourcesNote(ids, sources, synthetic, title = '', locators = {}) {
  const note = node('details', 'source-note citation');
  const trigger = node('summary'); trigger.setAttribute('aria-label', title ? `Sources for ${studyText('span', '', title).textContent}` : 'Sources'); trigger.title = 'Sources';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', 'M12 5C8 3 5 3 3 4v15c3-1 6-1 9 1m0-15c4-2 7-2 9-1v15c-3-1-6-1-9 1V5'); svg.append(path); trigger.append(svg);
  const panel = node('div', 'citation-panel');
  panel.append(node('div', 'eyebrow', synthetic ? 'Template sources' : 'Sources'));
  const list = node('ul');
  for (const id of ids) {
    const source = sources[id]; if (!source) continue;
    const item = node('li'), label = source.title;
    if (synthetic || !source.url) item.append(node('span', '', label));
    else {
      const url = new URL(source.url); if (!['http:', 'https:'].includes(url.protocol)) continue;
      const link = node('a', '', label); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; item.append(link);
    }
    if (locators[id]?.length) item.append(append(node('span', 'citation-locator citation-times'), ...locators[id]));
    else if (source.locator) item.append(node('span', 'citation-locator', source.locator));
    list.append(item);
  }
  panel.append(list); note.append(trigger, panel); note.hidden = !list.children.length;
  // Notes with time locators are specific to their place and never merge into a page citation.
  note.dataset.sources = Object.keys(locators).length ? '' : ids.filter(id => sources[id]).sort().join(' ');
  note.addEventListener('keydown', event => {
    if (event.key === 'Escape' && note.open) { event.preventDefault(); event.stopPropagation(); note.open = false; trigger.focus(); }
  });
  note.addEventListener('focusout', event => { if (!note.contains(event.relatedTarget)) note.open = false; });
  return note;
}
// When every citation on a page names the same sources, the page cites them once, beside its
// eyebrow, and the repeated section citations are hidden. Later renders (another exercise step)
// call this again to hide their repeats too.
export function shareCitations(root, eyebrow) {
  const notes = () => [...root.querySelectorAll('.source-note:not(.page-citation)')].filter(note => !note.hidden);
  if (root.dataset.citations === undefined) {
    const found = notes(), keys = new Set(found.map(note => note.dataset.sources));
    root.dataset.citations = found.length > 1 && keys.size === 1 && !keys.has('') ? [...keys][0] : '';
    if (root.dataset.citations) pageCitation(found[0], eyebrow);
  }
  if (!root.dataset.citations) return;
  for (const note of notes()) if (note.dataset.sources === root.dataset.citations) note.hidden = true;
}
export function pageCitation(note, eyebrow) {
  let row = eyebrow.parentElement;
  if (!row?.classList.contains('page-eyebrow')) { row = node('div', 'page-eyebrow'); eyebrow.replaceWith(row); row.append(eyebrow); }
  row.querySelector('.page-citation')?.remove();
  note.classList.add('page-citation'); note.hidden = false;
  note.querySelector('summary').setAttribute('aria-label', 'Sources for this page');
  row.append(note);
}
document.addEventListener('pointerdown', event => {
  for (const note of document.querySelectorAll('.citation[open]')) if (!note.contains(event.target)) note.open = false;
});
