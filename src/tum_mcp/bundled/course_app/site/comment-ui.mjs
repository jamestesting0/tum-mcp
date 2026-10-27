import { node, button } from './dom.mjs';
import { iconButton, iconGlyph } from './navigation.mjs';

export function commentComposer(root, save, currentDocument, closed = () => {}) {
  const dialog = node('dialog', 'comment-dialog'); dialog.dataset.commentUi = '';
  const title = node('h2', '', 'Comment'); title.id = `comment-title-${crypto.randomUUID()}`; dialog.setAttribute('aria-labelledby', title.id);
  const quote = node('blockquote', 'comment-quote');
  quote.tabIndex = 0; quote.setAttribute('role', 'region'); quote.setAttribute('aria-label', 'Selected passage');
  const input = node('textarea'); input.id = `comment-text-${crypto.randomUUID()}`; input.setAttribute('aria-label', 'Comment'); input.maxLength = 4000; input.required = true; input.rows = 5;
  const error = node('p', 'comment-error small'); error.setAttribute('role', 'alert');
  const latest = node('p', 'small comment-text');
  const choices = node('div', 'cluster'); choices.hidden = true;
  choices.append(button('Use latest', () => accept(true), 'quiet'), button('Keep mine', () => accept(false), 'quiet'));
  const form = node('form'); const actions = node('div', 'cluster comment-actions');
  const cancel = button('Cancel', () => dialog.close(), 'quiet');
  const submit = node('button', 'primary', 'Save'); submit.type = 'submit';
  actions.append(cancel, submit); form.append(input, error, latest, choices, actions); dialog.append(title, quote, form); root.append(dialog);
  let draft, returnFocus, changed = null, busy = false;
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  function sync(document) {
    if (!dialog.open || busy || !draft.baseline || !document) return;
    const current = document.comments.find(item => item.id === draft.id);
    if (same(current, draft.baseline)) return;
    if ((changed && same(current, changed)) || (!current && error.textContent === 'Removed elsewhere.')) return;
    changed = current || null; submit.disabled = true;
    error.textContent = current ? 'Changed elsewhere.' : 'Removed elsewhere.';
    latest.textContent = current ? `${current.status === 'resolved' ? 'Resolved · ' : ''}${current.text}` : '';
    choices.hidden = !current;
  }
  function accept(useLatest) {
    if (!changed) return;
    draft.baseline = changed; if (useLatest) input.value = changed.text;
    changed = null; error.textContent = ''; latest.textContent = ''; choices.hidden = true; submit.disabled = false;
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!input.value.trim()) { error.textContent = 'Add a note.'; input.focus(); return; }
    busy = true; submit.disabled = true; cancel.disabled = true; submit.textContent = 'Saving…'; error.textContent = '';
    try { await save(draft, input.value.trim()); dialog.close(); }
    catch (failure) { busy = false; error.textContent = failure.message || 'Save failed. Retry.'; sync(currentDocument()); }
    finally { busy = false; if (!changed && !error.textContent.startsWith('Removed')) submit.disabled = false; cancel.disabled = false; submit.textContent = 'Save'; }
  });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    const target = returnFocus?.isConnected ? returnFocus : root.querySelector('.comment-marker') || root.querySelector('.reading-material h2, .flashcard, legend');
    if (target?.isConnected) target.focus({ preventScroll: true });
    closed();
  });
  return {
    get open() { return dialog.open; },
    sync,
    show(value, trigger) {
      draft = { ...value, baseline: value.text !== undefined ? value : null }; changed = null;
      returnFocus = trigger; quote.textContent = value.anchor.quote; input.value = value.text || '';
      error.textContent = ''; latest.textContent = ''; choices.hidden = true; submit.disabled = false; dialog.showModal(); input.focus(); sync(currentDocument());
    },
  };
}

function commentRow(initial, actions) {
  let item = initial;
  const article = node('article', 'comment-note'); article.id = `comment-${item.id}`; article.tabIndex = -1;
  const main = node('div', 'comment-main');
  const jump = button('', event => {
    const selection = getSelection();
    if (event.detail && selection && !selection.isCollapsed && jump.contains(selection.anchorNode)) return;
    actions.show(item);
  }, 'comment-body'); jump.setAttribute('aria-label', 'Show passage');
  const text = node('span', 'comment-text'), quote = node('span', 'comment-excerpt');
  text.id = `note-text-${item.id}`; quote.id = `note-quote-${item.id}`;
  jump.setAttribute('aria-describedby', `${text.id} ${quote.id}`); jump.append(text, quote);
  const status = node('p', 'small comment-state'), resolution = node('p', 'small comment-resolution');
  main.append(jump, status, resolution);
  const controls = node('div', 'comment-controls');
  const done = iconButton('Resolve', 'check', () => actions.status(item));
  const more = node('details', 'comment-more'), summary = node('summary', 'icon-button quiet');
  summary.setAttribute('aria-label', 'More actions'); summary.title = 'More'; summary.append(iconGlyph('more'));
  const menu = node('div', 'comment-menu');
  menu.append(button('Edit', () => { more.open = false; actions.edit(item, summary); }, 'quiet'), button('Delete', () => { more.open = false; actions.remove(item, summary); }, 'quiet'));
  more.append(summary, menu); controls.append(done, more); article.append(main, controls);
  more.addEventListener('toggle', () => {
    if (!more.open) return;
    for (const other of article.parentElement?.querySelectorAll('.comment-more[open]') || []) if (other !== more) other.open = false;
    menu.scrollIntoView({ block: 'nearest' });
  });
  more.addEventListener('focusout', event => { if (!more.contains(event.relatedTarget)) more.open = false; });
  function update(value) {
    item = value;
    if (text.textContent !== item.text) text.textContent = item.text;
    const label = actions.label(item), excerpt = `${label ? label + ' · ' : ''}“${item.anchor.quote}”`;
    if (quote.textContent !== excerpt) quote.textContent = excerpt;
    const location = actions.locate(item);
    quote.hidden = Boolean(location); jump.title = location ? '' : item.anchor.quote;
    jump.setAttribute('aria-describedby', location ? text.id : `${text.id} ${quote.id}`);
    jump.disabled = !location;
    status.textContent = !location ? 'Passage unavailable.' : (item.anchor.semantic_revision || item.anchor.exercise_revision || item.anchor.unit_revision) !== actions.revision(item) ? 'Content changed.' : '';
    status.hidden = !status.textContent;
    resolution.textContent = item.status === 'resolved' ? item.resolution ? `Resolved · ${item.resolution}` : 'Resolved' : '';
    resolution.hidden = !resolution.textContent;
    const name = item.status === 'open' ? 'Resolve' : 'Reopen'; done.setAttribute('aria-label', name); done.title = name;
    if (done.dataset.status !== item.status) { done.replaceChildren(iconGlyph(item.status === 'open' ? 'check' : 'undo')); done.dataset.status = item.status; }
  }
  update(initial); return { element: article, update };
}

export function createCommentsList(actions) {
  const element = node('div', 'comment-list'), rows = node('div', 'comment-rows');
  const empty = node('p', 'small', 'Select text to comment.'); element.append(empty, rows);
  const existing = new Map();
  return { element, update(items) {
    const focus = document.activeElement, ids = new Set(items.map(item => item.id));
    for (const [id, row] of existing) if (!ids.has(id)) { row.element.remove(); existing.delete(id); }
    items.forEach((item, index) => {
      if (!existing.has(item.id)) existing.set(item.id, commentRow(item, actions));
      const row = existing.get(item.id); row.update(item);
      if (rows.children[index] !== row.element) rows.insertBefore(row.element, rows.children[index] || null);
    });
    empty.hidden = items.length > 0;
    return focus !== document.body && !focus.isConnected;
  } };
}
