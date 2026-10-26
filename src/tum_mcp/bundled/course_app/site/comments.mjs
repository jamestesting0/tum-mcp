import { node, button, focusHeading } from './dom.mjs';
import data from './data.mjs';
import { iconGlyph } from './navigation.mjs';
import { selectedPassage, locatePassage, highlightPassages } from './anchors.mjs';
import { commentStore } from './comment-store.mjs';
import { commentComposer, createCommentsList } from './comment-ui.mjs';
import { commentPopover } from './comment-popover.mjs';

let active;
export function stopComments() { active?.abort(); highlightPassages([]); }

export function renderCommentedView(unit, view, activity, activate) {
  if (data.hosted) return { root: activity };
  active = new AbortController(); const { signal } = active;
  const root = node('div', 'commented-reading'), reading = node('div'), store = commentStore(); reading.append(activity);
  const isExercise = view === 'exercises', isLecture = view === 'lectures';
  const owners = new Set(view === 'content' || isExercise || isLecture ? [unit.key] : unit[view === 'flashcards' ? 'flashcards' : 'questions'].map(item => item.origin?.key || unit.key));
  const relevant = item => (isLecture ? item.anchor.lecture_key === unit.key : isExercise ? item.anchor.exercise_key === unit.key && item.anchor.set_key === unit.setKey : owners.has(item.anchor.unit_key)) && (item.anchor.view || 'content') === view;
  const message = node('p', 'comment-message small'); message.setAttribute('role', 'status');
  const failure = node('p', 'comment-error small'); failure.setAttribute('role', 'status');
  let showResolved = false, locations = new Map(), groups = new Map(), activeHost, selectedId, savedId;
  let signature, selectionTimer, syncTimer;
  const resolved = button('Resolved', () => { showResolved = !showResolved; paintList(); }, 'quiet'); resolved.hidden = true;
  const list = createCommentsList({
    revision: item => isLecture || isExercise ? unit.revision : data.units.find(owner => owner.key === item.anchor.unit_key)?.revision, locate, show,
    label: item => unit.revision ? '' : data.units.find(owner => owner.key === item.anchor.unit_key)?.title,
    edit: (item, trigger) => openComposer(item, trigger),
    status: item => mutate({ op: 'status', id: item.id, status: item.status === 'open' ? 'resolved' : 'open' }, item),
    remove: item => { if (confirm('Delete comment?')) mutate({ op: 'delete', id: item.id }, item); },
  });
  const content = node('div'); content.append(message, list.element);
  const popup = commentPopover(root, content, resolved, signal, opened => { if (!opened) highlightPassages(openRanges()); schedule(); });
  const bubble = button('Comment', () => {
    const chosen = selectedPassage(reading, unit);
    if (chosen) openComposer({ anchor: chosen.anchor, id: crypto.randomUUID() }, passageFocus(chosen.anchor)); hide();
  }, 'selection-comment');
  bubble.hidden = true; bubble.dataset.commentUi = ''; bubble.addEventListener('pointerdown', event => event.preventDefault());
  const composer = commentComposer(root, async (draft, text) => {
    await store.change(draft.text !== undefined ? { op: 'edit', id: draft.id, text } : { op: 'create', id: draft.id, anchor: draft.anchor, text }, draft.baseline);
    getSelection()?.removeAllRanges(); savedId = draft.id; paint(); message.textContent = '';
  }, () => store.value, () => {
    const item = store.value?.comments.find(item => item.id === (savedId || selectedId)); savedId = null;
    if (item && !signal.aborted) show(item);
  });
  root.prepend(failure, reading, bubble);
  function passageFocus(anchor) {
    return locatePassage(reading, unit, anchor)?.focus || reading.querySelector('h2, .flashcard, legend');
  }
  function openComposer(value, trigger) { if (value.text === undefined) selectedId = null; popup.hide(); composer.show(value, trigger); schedule(1000); }
  function hide() { bubble.hidden = true; }
  function selection() {
    if (!root.isConnected || root.closest('[hidden]') || composer.open) return;
    const passage = selectedPassage(reading, unit);
    if (!passage) { hide(); return; }
    const { rect } = passage;
    bubble.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - 136))}px`;
    bubble.style.top = `${Math.max(8, Math.min(rect.top > 60 ? rect.top - 52 : rect.bottom + 8, innerHeight - 52))}px`;
    bubble.hidden = false;
  }
  document.addEventListener('selectionchange', () => { clearTimeout(selectionTimer); selectionTimer = setTimeout(selection, 100); }, { signal });
  document.addEventListener('scroll', hide, { signal, capture: true });
  reading.addEventListener('pointerup', selection, { signal });
  reading.addEventListener('study-activity-change', () => { hide(); popup.hide(); paint(); }, { signal });
  reading.addEventListener('click', event => {
    if (event.target.closest('[data-comment-ui],a,input,textarea,select,summary') || !getSelection()?.isCollapsed) return;
    const item = (store.value?.comments || []).find(item => relevant(item) && item.status === 'open' && [...(locate(item)?.range?.getClientRects() || [])].some(rect => event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom));
    if (item) { event.preventDefault(); event.stopPropagation(); show(item); }
  }, { signal, capture: true });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !composer.open && popup.open) {
      event.preventDefault();
      const menu = popup.element.querySelector('.comment-more[open]');
      if (menu) { menu.open = false; menu.querySelector('summary').focus(); } else popup.hide(true);
    }
    if (event.key.toLowerCase() !== 'm' || !event.altKey || !(event.ctrlKey || event.metaKey) || composer.open) return;
    const chosen = selectedPassage(reading, unit);
    if (!chosen || root.closest('[hidden]')) return;
    event.preventDefault(); openComposer({ anchor: chosen.anchor, id: crypto.randomUUID() }, passageFocus(chosen.anchor)); hide();
  }, { signal });
  document.addEventListener('pointerdown', event => {
    for (const menu of popup.element.querySelectorAll('.comment-more[open]')) if (!menu.contains(event.target)) menu.open = false;
  }, { signal });
  signal.addEventListener('abort', () => { clearTimeout(selectionTimer); clearTimeout(syncTimer); }, { once: true });
  window.addEventListener('focus', () => load(), { signal });
  document.addEventListener('visibilitychange', () => { clearTimeout(syncTimer); if (!document.hidden) load(); }, { signal });
  function schedule(delay = popup.open || composer.open ? 1000 : 4000) {
    clearTimeout(syncTimer); if (!signal.aborted && !document.hidden) syncTimer = setTimeout(load, delay);
  }
  function locate(item) { return locations.get(item.id); }
  function show(item) {
    if (locate(item)?.pending && activate && view !== 'content') { const replacement = activate(item.anchor); if (replacement) reading.replaceChildren(replacement); paint(); }
    const state = [...groups.values()].find(group => group.items.some(value => value.id === item.id)); if (!state) return;
    activeHost = state.host; selectedId = item.id; showResolved = item.status === 'resolved' || !state.items.some(value => value.status === 'open');
    const found = locate(item);
    message.textContent = found?.pending && view === 'practice' ? 'Check an answer first.' : '';
    if (found?.range) {
      const rect = found.range.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > innerHeight) found.range.startContainer.parentElement.scrollIntoView({ block: 'center', behavior: 'instant' });
    }
    paintList();
    popup.show(state.marker, () => locations.get(selectedId)?.range?.getBoundingClientRect() || state.marker.getBoundingClientRect());
    highlightPassages(openRanges(), found?.range ? [found.range] : []);
  }
  function openRanges() {
    return (store.value?.comments || []).filter(item => relevant(item) && item.status === 'open').map(locate).filter(item => item?.range).map(item => item.range);
  }
  async function mutate(operation, baseline) {
    try { await store.change(operation, baseline); message.textContent = ''; paint(); }
    catch (error) { if (!signal.aborted) { paint(); message.textContent = error.message || 'Save failed. Retry.'; } }
  }
  function paintList() {
    const items = groups.get(activeHost)?.items || [];
    if (!items.length) { popup.hide(); return; }
    if (!items.some(item => item.status === 'open')) showResolved = true;
    resolved.hidden = !items.some(item => item.status === 'resolved'); resolved.setAttribute('aria-pressed', String(showResolved));
    if (list.update(items.filter(item => showResolved || item.status === 'open')) && popup.open) popup.element.focus({ preventScroll: true });
    popup.position();
  }
  function hostFor(item) {
    if (isLecture) return [...reading.querySelectorAll('[data-lecture-section]')].find(section => section.dataset.lectureSection === item.anchor.section_key)?.querySelector('h2');
    if (isExercise) return reading.querySelector('h1');
    if (view !== 'content') {
      const current = reading.querySelector('[data-comment-target]');
      return current?.dataset.unitKey === item.anchor.unit_key && current.dataset.itemKey === item.anchor.item_key ? reading.querySelector('.recall-meta > div') : null;
    }
    const sections = [...reading.querySelectorAll('[data-block-index]')];
    const matching = sections.filter(section => unit.blocks[Number(section.dataset.blockIndex)].title === item.anchor.block_title);
    const section = locate(item)?.section || (matching.length === 1 ? matching[0] : null);
    return section?.querySelector('.reading-material h2');
  }
  function paint() {
    if (signal.aborted) return;
    const items = (store.value?.comments || []).filter(relevant); signature = JSON.stringify(items);
    const indexes = new Map(); locations = new Map(items.map(item => [item.id, locatePassage(reading, unit, item.anchor, indexes)]));
    const next = new Map();
    for (const item of items) {
      const host = hostFor(item); if (!host) continue;
      if (!next.has(host)) next.set(host, { host, items: [] }); next.get(host).items.push(item);
    }
    for (const [host, state] of next) {
      const previous = groups.get(host); state.marker = previous?.marker;
      if (!state.marker) {
        state.marker = button('', () => {
          const current = groups.get(host), item = current?.items.find(item => item.status === 'open' && locate(item)?.range) || current?.items.find(item => item.status === 'open') || current?.items[0];
          if (item) show(item);
        }, 'comment-marker');
        state.marker.dataset.commentUi = ''; state.marker.setAttribute('aria-haspopup', 'dialog');
        state.marker.setAttribute('aria-controls', popup.element.id); state.marker.setAttribute('aria-expanded', 'false');
        const face = node('span', 'comment-marker-face'); face.append(iconGlyph('comment'), node('span', 'comment-count')); state.marker.append(face);
        if (view === 'content' || isExercise || isLecture) host.append(state.marker);
        else { host.classList.add('comment-position'); host.firstElementChild.after(state.marker); }
      }
      const count = state.items.filter(item => item.status === 'open').length;
      state.marker.dataset.openCount = String(count); state.marker.dataset.count = String(count || state.items.length);
      const label = `${count || state.items.length} ${count ? '' : 'resolved '}${(count || state.items.length) === 1 ? 'comment' : 'comments'} on ${isLecture ? 'this section' : view === 'content' ? state.items[0].anchor.block_title : view === 'flashcards' ? 'this card' : 'this question'}`;
      state.marker.setAttribute('aria-label', label); state.marker.title = label;
      const number = state.marker.querySelector('.comment-count'); if (number.textContent !== state.marker.dataset.count) number.textContent = state.marker.dataset.count;
    }
    for (const [host, state] of groups) if (!next.has(host)) { if (state.marker.contains(document.activeElement)) focusHeading(host); state.marker.remove(); }
    groups = next; paintList();
    const selected = locations.get(selectedId)?.range;
    highlightPassages(openRanges(), popup.open && selected ? [selected] : []);
  }
  async function load() {
    if (signal.aborted || document.hidden) return;
    try {
      const value = await store.load(); if (signal.aborted) return;
      composer.sync(value); if (signature !== JSON.stringify(value.comments.filter(relevant))) paint(); failure.textContent = '';
    } catch (error) { if (!signal.aborted) failure.textContent = error.message || 'Comments unavailable.'; }
    finally { schedule(); }
  }
  load(); return { root };
}
