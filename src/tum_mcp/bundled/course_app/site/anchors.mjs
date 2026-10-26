// Quote selectors use literal text and context, never HTML or guessed fuzzy matches.
import data from './data.mjs';
import { studyText } from './dom.mjs';
const excluded = 'button:not(.flashcard),input,textarea,select,svg,.source-note,[data-comment-ui],[hidden],[aria-hidden="true"]';
export function annotate(element, unit, item, view, field) {
  const owner = item.origin || unit;
  Object.assign(element.dataset, { commentTarget: view, unitKey: owner.key, unitRevision: owner.revision, itemKey: item.key, field });
  return element;
}
export function annotateExercise(element, group, exercise, field, step = '') {
  Object.assign(element.dataset, { commentTarget: 'exercises', setKey: group.key,
    exerciseKey: exercise.key, exerciseRevision: exercise.revision, stepKey: step, field });
  return element;
}
function before(text, at) {
  let start = Math.max(0, at - 80);
  if (text.charCodeAt(start) >= 0xDC00 && text.charCodeAt(start) <= 0xDFFF) start++;
  return text.slice(start, at);
}
function after(text, at) {
  let end = Math.min(text.length, at + 80);
  if (text.charCodeAt(end - 1) >= 0xD800 && text.charCodeAt(end - 1) <= 0xDBFF) end--;
  return text.slice(at, end);
}
function textIndex(material) {
  const walker = document.createTreeWalker(material, NodeFilter.SHOW_TEXT);
  const segments = []; let raw = '', current;
  while ((current = walker.nextNode())) {
    if (current.parentElement.closest(excluded)) continue;
    segments.push({ node: current, start: raw.length, end: raw.length + current.length }); raw += current.data;
  }
  let text = ''; const starts = [], ends = [];
  for (let i = 0; i < raw.length;) {
    const start = i, space = /\s/u.test(raw[i]); i++;
    if (space) while (i < raw.length && /\s/u.test(raw[i])) i++;
    text += space ? ' ' : raw[start]; starts.push(start); ends.push(i);
  }
  return { text, starts, ends, segments };
}
export function selectedPassage(root, unit) {
  const selection = getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return null;
  const range = selection.getRangeAt(0);
  const element = range.startContainer.nodeType === Node.ELEMENT_NODE ? range.startContainer : range.startContainer.parentElement;
  const material = element.closest('[data-comment-target]');
  if (!material || !root.contains(material) || !material.contains(range.endContainer)) return null;
  if ([...material.querySelectorAll(excluded)].some(item => range.intersectsNode(item))) return null;
  const index = textIndex(material); let from = null, to = null;
  for (const segment of index.segments) {
    const start = range.startContainer === segment.node ? range.startOffset : range.comparePoint(segment.node, 0) >= 0 ? 0 : segment.node.length;
    const end = range.endContainer === segment.node ? range.endOffset : range.comparePoint(segment.node, segment.node.length) <= 0 ? segment.node.length : 0;
    if (start >= end) continue;
    if (from === null) from = segment.start + start;
    to = segment.start + end;
  }
  if (from === null) return null;
  let first = index.ends.findIndex(end => end > from), last = index.starts.findLastIndex(start => start < to) + 1;
  while (index.text[first] === ' ') first++;
  while (index.text[last - 1] === ' ') last--;
  const quote = index.text.slice(first, last);
  if (!quote || quote.length > 2000) return null;
  const section = material.closest('[data-block-index]'), view = material.dataset.commentTarget;
  if (view === 'exercises') return { anchor: { workspace: 'exercises', view,
    set_key: material.dataset.setKey, exercise_key: material.dataset.exerciseKey,
    exercise_revision: material.dataset.exerciseRevision, step_key: material.dataset.stepKey || null,
    field: material.dataset.field, block_title: unit.title, quote,
    prefix: before(index.text, first), suffix: after(index.text, last) }, rect: range.getBoundingClientRect() };
  const anchor = { view, unit_key: material.dataset.unitKey || unit.key,
    unit_revision: material.dataset.unitRevision || unit.revision, block_index: 0,
    block_title: view === 'content' ? unit.blocks[Number(section.dataset.blockIndex)].title : view === 'flashcards' ? 'Flashcards' : 'Practice',
    quote, prefix: before(index.text, first), suffix: after(index.text, last) };
  if (view === 'content') anchor.block_index = Number(section.dataset.blockIndex);
  else { anchor.item_key = material.dataset.itemKey; anchor.field = material.dataset.field; }
  return {
    anchor,
    rect: range.getBoundingClientRect(),
  };
}
function offsets(text, anchor) {
  const matches = [];
  for (let at = text.indexOf(anchor.quote); at !== -1; at = text.indexOf(anchor.quote, at + 1)) {
    const end = at + anchor.quote.length;
    if (text.slice(Math.max(0, at - anchor.prefix.length), at) === anchor.prefix && text.slice(end, end + anchor.suffix.length) === anchor.suffix) matches.push(at);
  }
  return matches;
}
function sourceText(anchor) {
  const unit = data.units.find(item => item.key === anchor.unit_key);
  if (!unit) return null;
  const item = (anchor.view === 'flashcards' ? unit.flashcards : unit.questions).find(value => value.key === anchor.item_key);
  if (!item) return null;
  if (anchor.view === 'flashcards') return item[anchor.field];
  if (['prompt', 'explanation'].includes(anchor.field)) return item[anchor.field];
  if (anchor.field === 'correct') return item.options.find(option => option.key === item.correct)?.text;
  const [kind, key] = anchor.field.split(':'); const option = item.options.find(value => value.key === key);
  return option?.[kind === 'option' ? 'text' : 'feedback'];
}
export function locatePassage(root, unit, anchor, indexes = new Map()) {
  const view = anchor.view || 'content'; let section, material;
  if (view === 'exercises') {
    material = [...root.querySelectorAll('[data-comment-target="exercises"]')].find(item =>
      item.dataset.exerciseKey === anchor.exercise_key && item.dataset.setKey === anchor.set_key &&
      (item.dataset.stepKey || null) === anchor.step_key && item.dataset.field === anchor.field &&
      !item.closest('[hidden],[aria-hidden="true"],details:not([open])'));
    if (!material) return null;
    section = material;
  } else if (view === 'content') {
    const sections = [...root.querySelectorAll('[data-block-index]')]; section = sections[anchor.block_index];
    if (!section || unit.blocks[Number(section.dataset.blockIndex)].title !== anchor.block_title) {
      const matching = sections.filter(item => unit.blocks[Number(item.dataset.blockIndex)].title === anchor.block_title);
      if (matching.length !== 1) return null;
      [section] = matching;
    }
    material = section.querySelector('.reading-material');
  } else {
    material = [...root.querySelectorAll('[data-comment-target]')].find(item => item.dataset.unitKey === anchor.unit_key && item.dataset.itemKey === anchor.item_key && item.dataset.field === anchor.field && !item.closest('[hidden],[aria-hidden="true"]'));
    const source = sourceText(anchor);
    if (!source || offsets(studyText('span', '', source).textContent.replace(/\s+/g, ' '), anchor).length !== 1) return null;
    if (!material) return { pending: true };
    section = material;
  }
  if (!indexes.has(material)) indexes.set(material, textIndex(material));
  const index = indexes.get(material), matches = offsets(index.text, anchor);
  if (matches.length !== 1) return null;
  const start = index.starts[matches[0]], end = index.ends[matches[0] + anchor.quote.length - 1];
  const a = index.segments.find(item => item.start <= start && start < item.end);
  const b = index.segments.find(item => item.start < end && end <= item.end);
  if (!a || !b) return null;
  const range = document.createRange(); range.setStart(a.node, start - a.start); range.setEnd(b.node, end - b.start);
  const focus = view === 'exercises' ? root.querySelector('h1') : view === 'content' ? section.querySelector('h2') : material.closest('.flashcard') || root.querySelector('.practice-question legend');
  return { range, section, focus };
}
export function highlightPassages(ranges, focused = []) {
  if (!globalThis.CSS?.highlights || !globalThis.Highlight) return;
  CSS.highlights.set('study-comments', new Highlight(...ranges));
  CSS.highlights.set('study-comment-focus', new Highlight(...focused));
}
