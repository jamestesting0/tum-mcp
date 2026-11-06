import data from '../../data.mjs';
import { node, append, scrollReadingTo } from './dom.mjs';

// One search over the whole course: lesson passages, exercises, the cheatsheet, exam patterns
// and lecture notes. Results rank title hits above text hits and show where the words occur;
// choosing one opens its page at that passage and marks the words there.

const SKIP = new Set(['kind', 'key', 'keys', 'sources', 'pages', 'level', 'svg', 'mathml', 'pieces', 'image', 'asset', 'sha256', 'url', 'thumbnail', 'evidence', 'interval', 'revision', 'correct', 'objective', 'unit', 'block', 'at', 'shape', 'row', 'col', 'start', 'end', 'state_labels', 'language', 'line_numbers', 'width', 'height', 'nodes', 'edges', 'active', 'frontier', 'visited', 'cells', 'shown', 'series', 'layers', 'state', 'x', 'y', 'latex', 'topic', 'basis', 'status', 'role', 'relevance', 'category', 'path', 'week', 'workflow_from', 'plain', 'tier']);
const SYMBOLS = { to: '→', rightarrow: '→', leftarrow: '←', gets: '←', cdot: '·', times: '×', le: '≤', leq: '≤', ge: '≥', geq: '≥', ne: '≠', neq: '≠', approx: '≈', in: '∈', infty: '∞', sum: 'Σ', bmod: 'mod', pmod: 'mod', ldots: '…', dots: '…', quad: ' ', qquad: ' ' };
// Inline math as a reader would say it in a snippet: commands become their symbol or name,
// fractions read a/b and grouping braces go.
const mathText = latex => latex
  .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '$1/$2')
  .replace(/\\([A-Za-z]+)/g, (_, name) => Object.hasOwn(SYMBOLS, name) ? SYMBOLS[name] : /^(math|text|operatorname|bold|it$|rm$)/.test(name) ? '' : name)
  .replace(/[{}]/g, '').replace(/\\./g, ' ');
// Text as a reader sees it: math read out, no term braces or code ticks.
const plain = text => String(text)
  .replace(/\\\((.*?)\\\)/gs, (_, latex) => mathText(latex))
  .replace(/\{\{|\}\}|`/g, '').replace(/\s+/g, ' ').trim();
// Folds case and accents one character at a time, so match offsets stay valid in the original
// text ("…" would otherwise expand to three characters).
const fold = text => Array.from(text, char => {
  const folded = char.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  return folded.length === char.length ? folded : char.toLowerCase();
}).join('');
function strings(value, out = []) {
  if (typeof value === 'string') { if (!/^\d+(-\d+)?$/.test(value)) out.push(plain(value)); }
  else if (Array.isArray(value)) value.forEach(item => strings(item, out));
  else if (value && typeof value === 'object') for (const [key, item] of Object.entries(value)) if (!SKIP.has(key)) strings(item, out);
  return out;
}
const titleOf = item => plain(item.title || item.term || item.label || '');

let index = null;
// `own` says whether the title belongs to this entry; a passage shown under its section's or
// page's title matches by its own text only, so one title hit lists the page once.
function entry(where, crumb, title, text, href, target = '', own = true) {
  const body = text.filter(Boolean).join(' · ');
  return { where, crumb, title, text: body, href, target, foldedTitle: own ? fold(title) : '', foldedText: fold(body), anchor: fold(title) };
}
function build() {
  const entries = [];
  for (const unit of data.units || []) {
    let heading = plain(unit.title);
    entries.push(entry('Study', '', plain(unit.title), [plain(unit.summary || '')], `#${unit.key}/content`));
    unit.blocks.forEach((block, position) => {
      const titled = Boolean(block.title && block.kind !== 'definition');
      if (titled) heading = plain(block.title);
      const title = block.kind === 'definition' ? plain(block.term) : heading;
      entries.push(entry('Study', plain(unit.title), title, strings({ ...block, title: undefined, term: undefined }), `#${unit.key}/content`, `[data-block-index="${position}"]`, titled || block.kind === 'definition'));
    });
  }
  for (const group of data.exercises?.sets || []) {
    for (const exercise of group.exercises) {
      const href = `#exercises/${group.key}/${exercise.key}`, title = `${exercise.label} · ${plain(exercise.title)}`;
      entries.push(entry('Exercises', plain(group.title), title, [], href));
      exercise.statement.forEach((block, position) => entries.push(entry('Exercises', plain(group.title), title, strings(block), href, `#exercise-question [data-block-index="${position}"]`, false)));
    }
  }
  const exam = data.exam;
  for (const concept of exam?.concepts || []) entries.push(entry('Exam', 'Cheatsheet', titleOf(concept), strings({ ...concept, title: undefined }), '#exam/sheet'));
  for (const pattern of exam?.patterns || []) {
    entries.push(entry('Exam', 'Exam pattern', plain(pattern.title), strings({ cues: pattern.cues, workflow: pattern.workflow, pitfalls: pattern.pitfalls }), `#exam/patterns/${pattern.key}`));
  }
  for (const lecture of data.lectures?.lectures || []) {
    for (const item of [...lecture.notes, ...lecture.highlights]) {
      entries.push(entry('Lecture', plain(lecture.title), plain(item.title), strings({ context: item.context, text: item.text, teaches: item.teaches, points: item.points, steps: item.steps }), `#lectures/${encodeURIComponent(lecture.key)}/${encodeURIComponent(item.key)}`));
    }
  }
  return entries;
}

const terms = query => fold(query).split(/[^\p{L}\p{N}]+/u).filter(Boolean);
const startsWord = (text, term) => new RegExp(`(^|[^\\p{L}\\p{N}])${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'u').test(text);
// Every word must occur; a word at the start of a title word counts most, then anywhere in the
// title, then the start of a word in the text. The whole query as a phrase adds a bonus.
export function search(query, limit = 30) {
  index ||= build();
  const words = terms(query), phrase = fold(query.trim());
  if (!words.length) return [];
  const scored = [];
  for (const item of index) {
    let score = 0;
    for (const word of words) {
      const inTitle = item.foldedTitle.includes(word), inText = item.foldedText.includes(word);
      if (!inTitle && !inText) { score = 0; break; }
      score += inTitle ? (startsWord(item.foldedTitle, word) ? 10 : 6) : startsWord(item.foldedText, word) ? 3 : 1;
    }
    if (!score) continue;
    if (phrase.includes(' ') && (item.foldedTitle.includes(phrase) || item.foldedText.includes(phrase))) score += 5;
    scored.push({ item, score });
  }
  scored.sort((a, b) => b.score - a.score);
  const seen = new Set(), results = [];
  for (const { item } of scored) {
    const id = `${item.href}|${item.target}|${item.title}`;
    if (seen.has(id)) continue;
    seen.add(id); results.push({ ...item, words });
    if (results.length === limit) break;
  }
  return results;
}

// A short window of text around the first match, cut at word boundaries, with every
// query word marked.
function marked(text, words) {
  const element = node('span');
  const pattern = new RegExp(words.map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'giu');
  const folded = fold(text);
  let start = 0;
  for (const match of folded.matchAll(pattern)) {
    element.append(text.slice(start, match.index), node('mark', '', text.slice(match.index, match.index + match[0].length)));
    start = match.index + match[0].length;
  }
  element.append(text.slice(start));
  return element;
}
function snippet(text, words) {
  if (!text) return '';
  const folded = fold(text);
  // Centre on the longest query word, the one that says most about the match.
  const longest = [...words].sort((a, b) => b.length - a.length).find(word => folded.includes(word));
  const first = longest ? folded.indexOf(longest) : Infinity;
  if (!Number.isFinite(first)) return text.length > 140 ? `${text.slice(0, 140).replace(/\s+\S*$/, '')} …` : text;
  let from = Math.max(0, first - 50), to = Math.min(text.length, first + 110);
  if (from > 0) from = text.indexOf(' ', from) + 1;
  if (to < text.length) to = text.lastIndexOf(' ', to);
  return `${from > 0 ? '… ' : ''}${text.slice(from, to)}${to < text.length ? ' …' : ''}`;
}

// After the page for a result renders: open any closed disclosure holding the words, scroll
// to the passage and mark the words there until the student moves on.
let pending = null;
function arrive() {
  if (!pending) return;
  const { target, words, anchor } = pending; pending = null;
  const main = document.querySelector('main');
  if (!main) return;
  // Without a passage address, the entry is found by its own title (a cheatsheet entry, a page).
  const titled = !target && [...main.querySelectorAll('.exam-entry-title, h1, h2, h3, h4, summary')]
    .find(element => fold(element.textContent.trim()) === anchor);
  const scope = (target && main.querySelector(target)) || titled?.closest('details, li, section') || main;
  for (const walk of scope.querySelectorAll('.walk')) if (walk.showMatch?.(words)) break;
  const pattern = new RegExp(words.map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'giu');
  const ranges = [];
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, { acceptNode: text =>
    text.parentElement.closest('.katex-mathml, script, style, [aria-hidden="true"]') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
  for (let text = walker.nextNode(); text; text = walker.nextNode()) {
    // Folding keeps the length for Latin text, so offsets map back to the node.
    const folded = fold(text.data);
    if (folded.length !== text.data.length) continue;
    for (const match of folded.matchAll(pattern)) {
      const range = document.createRange(); range.setStart(text, match.index); range.setEnd(text, match.index + match[0].length);
      ranges.push(range);
    }
  }
  const first = ranges[0]?.startContainer.parentElement;
  for (let details = first?.closest('details'); details; details = details.parentElement?.closest('details')) details.open = true;
  const passage = scope === main ? first?.closest('section, li, .block-body, p') || first : scope;
  if (passage) {
    scrollReadingTo(passage);
    passage.classList.remove('search-arrival'); void passage.offsetWidth; passage.classList.add('search-arrival');
  }
  if (globalThis.CSS?.highlights && ranges.length) {
    CSS.highlights.set('search-hit', new Highlight(...ranges));
    const clear = () => { CSS.highlights.delete('search-hit'); removeEventListener('hashchange', clear); };
    addEventListener('hashchange', clear);
  }
}
addEventListener('hashchange', () => requestAnimationFrame(() => requestAnimationFrame(arrive)));

function go(result) {
  pending = { target: result.target, words: result.words, anchor: result.anchor };
  if (location.hash === result.href) { requestAnimationFrame(arrive); return; }
  location.hash = result.href;
}

// The dialog: a field and a list of results, keyboard first (arrows move, Enter opens,
// Escape closes), opened from the sidebar or with "/".
let dialog = null;
export function openSearch(trigger = document.activeElement) {
  if (!dialog) dialog = searchDialog();
  dialog.returnFocus = trigger;
  if (!dialog.element.open) dialog.element.showModal();
  dialog.input.select();
}
function searchDialog() {
  const element = node('dialog', 'search-dialog'); element.setAttribute('aria-label', 'Search the course');
  const input = node('input', 'search-input'); input.type = 'search'; input.placeholder = 'Search the course';
  input.setAttribute('aria-label', 'Search the course'); input.setAttribute('role', 'combobox');
  input.setAttribute('aria-expanded', 'false'); input.setAttribute('aria-controls', 'search-results'); input.autocomplete = 'off';
  const list = node('ul', 'search-results'); list.id = 'search-results'; list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', 'Results');
  const status = node('p', 'small search-status'); status.setAttribute('aria-live', 'polite');
  let results = [], active = -1;
  function select(position) {
    active = position;
    [...list.children].forEach((item, index) => item.setAttribute('aria-selected', String(index === active)));
    const current = list.children[active];
    if (current) { input.setAttribute('aria-activedescendant', current.id); current.scrollIntoView({ block: 'nearest' }); }
    else input.removeAttribute('aria-activedescendant');
  }
  function render() {
    const query = input.value;
    results = search(query);
    list.replaceChildren(...results.map((result, index) => {
      const item = node('li', 'search-result'); item.id = `search-result-${index}`; item.setAttribute('role', 'option');
      const where = append(node('span', 'small search-where'), result.where, ...(result.crumb ? [' · ', result.crumb] : []));
      item.append(where, append(node('span', 'search-title'), marked(result.title, result.words)));
      const text = snippet(result.text, result.words);
      if (text) item.append(append(node('span', 'small search-snippet'), marked(text, result.words)));
      item.addEventListener('click', () => choose(index));
      item.addEventListener('pointermove', () => { if (active !== index) select(index); });
      return item;
    }));
    input.setAttribute('aria-expanded', String(results.length > 0));
    status.textContent = query.trim() && !results.length ? `No matches for “${query.trim()}”` : '';
    select(results.length ? 0 : -1);
  }
  function choose(position) {
    const result = results[position];
    if (!result) return;
    element.close(); go(result);
  }
  input.addEventListener('input', render);
  input.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (results.length) select((active + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length);
    } else if (event.key === 'Enter') { event.preventDefault(); choose(active); }
  });
  element.addEventListener('click', event => { if (event.target === element) element.close(); });
  element.addEventListener('close', () => { if (!pending) dialog.returnFocus?.focus?.({ preventScroll: true }); });
  element.append(append(node('div', 'search-box'), input, status, list));
  document.body.append(element);
  return { element, input };
}
addEventListener('keydown', event => {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
  if (event.target.closest?.('input, textarea, select, [contenteditable=""], [contenteditable="true"]')) return;
  event.preventDefault(); openSearch();
});
