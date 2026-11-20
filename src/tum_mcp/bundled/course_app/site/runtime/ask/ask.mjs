// Ask agent: a chat beside the page, run by the student's own Claude Code or Codex through the
// local preview. It shares the Recall panel's slot, keeps past chats, and reloads the page in
// place after the agent edits it. Absent on hosted sites, like comments.
import data from '../../data.mjs';
import { node, button, append, confirmAction } from '../shell/dom.mjs';
import { iconButton, iconGlyph } from '../shell/navigation.mjs';
import { texElement } from '../reading/mathml.mjs';
import { renderCode, codeHead, languageName } from '../reading/code.mjs';
import { MARKS } from './marks.mjs';

const API = '/_study/agent/';
const restoreKey = `course-app:${data.course.identity}:ask-restore`;
const chatKey = `course-app:${data.course.identity}:ask-chat`;
const narrow = matchMedia('(max-width: 799px)');
// A 400px chat leaves the same 360px minimum as the coding exercise's editor.
const dockMin = 760;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const EFFORTS = { none: 'None', minimal: 'Minimal', low: 'Low', medium: 'Medium', high: 'High', xhigh: 'Extra high', max: 'Max' };
let token = null, panel = null, view = null, status = null, chat = null, pending = null, running = null, watch = null, lexer = null;
// The context sent with the next message: the pinned selection, else the section in view.
// `dropped` hides it until the student selects other text.
const live = { source: null, selection: null, section: null, dropped: false };

async function call(path, body) {
  if (!token && path.startsWith('status')) {
    // The status reply carries the token, so the first status request is the only one.
    const value = await (await fetch(API + path, { cache: 'no-store' })).json();
    token = value.token; return value;
  }
  if (!token) token = (await (await fetch(API + 'status', { cache: 'no-store' })).json()).token;
  const options = { cache: 'no-store', headers: { 'X-Ask-Token': token } };
  if (body !== undefined) Object.assign(options, { method: 'POST', body: JSON.stringify(body), headers: { ...options.headers, 'Content-Type': 'application/json' } });
  const response = await fetch(API + path, options);
  if (path === 'send') return response;
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Request failed.');
  return value;
}

// Answers are GitHub Markdown with LaTeX. The vendored marked lexer gives tokens, and they become
// DOM nodes here, so no agent text reaches innerHTML. Math is set aside before lexing, because
// Markdown would eat its backslashes, and is drawn by the app's own math renderer.
const loadMarked = () => lexer ? Promise.resolve() : import('../../assets/marked/marked.esm.js').then(module => { lexer = module.lexer; });
const MATH = /(```[\s\S]*?(?:```|$)|`[^`\n]*`)|\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<![\\$\w])\$(?=[^\s$])([^$\n]*?[^\s$\\])\$(?![\w$])/g;
const MARK = /([\uE000\uE002])(\d+)\uE001/g;

function markdown(text) {
  const root = node('div', 'ask-answer');
  if (!lexer) {
    for (const part of text.split(/\n{2,}/)) if (part.trim()) root.append(node('p', '', part));
    return root;
  }
  const math = [];
  const source = text.replace(MATH, (whole, code, block, bracket, paren, dollar) => {
    if (code !== undefined) return whole;
    math.push({ tex: block ?? bracket ?? paren ?? dollar, raw: whole });
    return `${block ?? bracket ? '\uE002' : '\uE000'}${math.length - 1}\uE001`;
  });
  const words = (parent, value) => {
    let start = 0;
    for (const match of value.matchAll(MARK)) {
      parent.append(value.slice(start, match.index));
      const item = math[Number(match[2])], display = match[1] === '\uE002';
      const rendered = item && texElement(item.tex.trim(), display ? { display: true } : undefined);
      parent.append(rendered ? append(node('span', display ? 'ask-display' : 'inline-math'), rendered) : item?.raw ?? match[0]);
      start = match.index + match[0].length;
    }
    parent.append(value.slice(start));
    return parent;
  };
  const inlines = (parent, tokens = []) => { for (const token of tokens) parent.append(inline(token)); return parent; };
  const inline = token => {
    switch (token.type) {
      case 'strong': return inlines(node('strong'), token.tokens);
      case 'em': return inlines(node('em'), token.tokens);
      case 'del': return inlines(node('del'), token.tokens);
      case 'codespan': return node('code', 'inline-code', token.text);
      case 'br': return node('br');
      case 'link': {
        if (!/^(https?:|mailto:)/i.test(token.href)) return inlines(node('span'), token.tokens);
        const link = inlines(node('a'), token.tokens);
        Object.assign(link, { href: token.href, target: '_blank', rel: 'noopener noreferrer' });
        return link;
      }
      case 'text': return token.tokens ? inlines(document.createDocumentFragment(), token.tokens) : words(document.createDocumentFragment(), token.text);
      case 'image': return document.createTextNode(token.text || '');
      default: return document.createTextNode(token.type === 'escape' ? token.text : token.raw || '');
    }
  };
  const cell = (tag, value, align) => {
    const element = inlines(node(tag), value.tokens);
    if (tag === 'th') element.scope = 'col';
    if (align) element.style.textAlign = align;
    return element;
  };
  const block = token => {
    switch (token.type) {
      case 'paragraph': {
        if (/^\uE002\d+\uE001$/.test(token.text.trim())) return words(node('div', 'ask-display'), token.text.trim());
        const paragraph = inlines(node('p'), token.tokens);
        if (/^Sources?:/.test(token.text)) paragraph.className = 'ask-source';
        return paragraph;
      }
      case 'heading': return inlines(node(`h${Math.min(token.depth + 2, 5)}`, 'ask-heading'), token.tokens);
      case 'code': {
        const language = token.lang || 'text', region = node('div', 'code-region');
        region.append(codeHead(region, languageName(language) || 'Code'), renderCode(token.text, language));
        return region;
      }
      case 'blockquote': return blocks(node('blockquote'), token.tokens);
      case 'hr': return node('hr');
      case 'list': {
        const list = node(token.ordered ? 'ol' : 'ul');
        if (token.ordered && Number(token.start) > 1) list.start = Number(token.start);
        for (const item of token.items) {
          const entry = node('li', item.task ? 'ask-task' : '');
          for (const child of item.tokens) {
            if (child.type === 'checkbox') {
              const box = node('input'); Object.assign(box, { type: 'checkbox', checked: item.checked, disabled: true }); entry.append(box);
            } else if (child.type === 'text') inlines(entry, child.tokens || [{ type: 'text', text: child.text }]);
            else { const element = block(child); if (element) entry.append(element); }
          }
          list.append(entry);
        }
        return list;
      }
      case 'table': {
        const head = node('tr'), body = node('tbody');
        token.header.forEach((value, index) => head.append(cell('th', value, token.align[index])));
        for (const row of token.rows) body.append(append(node('tr'), ...row.map((value, index) => cell('td', value, token.align[index]))));
        return append(node('div', 'ask-table'), append(node('table'), append(node('thead'), head), body));
      }
      case 'text': return token.tokens ? inlines(node('p'), token.tokens) : words(node('p'), token.text);
      case 'space': case 'def': return null;
      default: return token.raw?.trim() ? node('p', '', token.raw) : null;
    }
  };
  const blocks = (parent, tokens) => { for (const token of tokens) { const element = block(token); if (element) parent.append(element); } return parent; };
  return blocks(root, lexer(source, { gfm: true }));
}

function current() {
  if (live.dropped) return null;
  if (live.selection) return { kind: 'selection', ...live.selection };
  return live.section && { kind: 'section', ...live.section };
}
const placeOf = item => [item.title !== item.unit ? item.title : '', item.unit].filter(Boolean).join(' · ');

// One card for a context: a selection shows its quote clamped to two lines over its section; the
// section in view shows one line. Sent messages keep a smaller copy without the remove button.
function contextCard(item, removable) {
  const card = node('div', `ask-context is-${item.kind}${removable ? '' : ' is-sent'}`);
  const icon = node('span', 'ask-context-icon'); icon.append(iconGlyph(item.kind));
  const body = node('div', 'ask-context-body');
  if (item.kind === 'selection') {
    const quote = item.quote.replace(/\s+/g, ' ').trim();
    append(body, node('p', 'ask-context-quote', quote), node('p', 'ask-context-place', item.place));
    card.title = quote;
  } else {
    const line = node('p', 'ask-context-line');
    append(line, node('span', 'ask-context-title', item.title), item.unit && item.unit !== item.title ? node('span', 'ask-context-place', item.unit) : '');
    body.append(line);
    card.title = placeOf(item);
  }
  append(card, icon, body);
  if (removable) card.append(iconButton('Remove context', 'close', () => { live.dropped = true; paintContext(); panel?.querySelector('.ask-input textarea')?.focus({ preventScroll: true }); }));
  return card;
}

function contextKey(item) {
  return item ? `${item.kind}:${item.quote || ''}:${JSON.stringify(item.anchor)}` : '';
}

function paintContext() {
  const slot = panel?.querySelector('.ask-context-slot'); if (!slot) return;
  const item = current(), key = contextKey(item);
  if (slot.dataset.key === key) return;
  slot.dataset.key = key;
  slot.replaceChildren(item ? contextCard({ ...item, quote: item.quote || item.anchor.quote, place: placeOf(item) }, true) : '');
}

function sentContext(message) {
  if (message.quote) return contextCard({ kind: 'selection', quote: message.quote, place: message.section }, false);
  return message.section ? contextCard({ kind: 'section', title: message.section, unit: '' }, false) : null;
}

// While the panel is open, the context follows the page: a new selection pins itself, a click
// elsewhere on the page clears it, and scrolling updates the section in view.
function watchPage() {
  if (watch) return;
  watch = new AbortController();
  const { signal } = watch;
  let timer, frame;
  document.addEventListener('selectionchange', () => { clearTimeout(timer); timer = setTimeout(selectionChanged, 120); }, { signal });
  document.addEventListener('scroll', event => {
    if (frame || panel?.contains(event.target)) return;
    frame = requestAnimationFrame(() => { frame = null; sectionChanged(); });
  }, { signal, capture: true });
}

function selectionChanged() {
  if (!panel || !live.source || panel.contains(document.activeElement)) return;
  const found = live.source.selection();
  if (found) { Object.assign(live, { selection: found, dropped: false }); paintContext(); return; }
  const selection = getSelection();
  if (live.selection && selection?.isCollapsed && !panel.contains(selection.anchorNode)) { live.selection = null; sectionChanged(); }
}

function sectionChanged() {
  if (!panel || live.selection) return;
  live.section = live.source?.section() || null;
  paintContext();
}

// The reading view in front registers how to find its selection and its section in view.
export function trackAsk(source, signal) {
  Object.assign(live, { source, selection: null });
  signal.addEventListener('abort', () => { if (live.source === source) live.source = null; });
  if (panel) requestAnimationFrame(sectionChanged);
}

function messageNode(message) {
  if (message.role === 'student') return node('div', 'ask-user', message.text);
  const change = message.change;
  // The change line says what changed, so the agent's own "Updated …" line is not repeated.
  const text = change ? message.text.split('\n').filter(line => !line.startsWith('Updated')).join('\n') : message.text;
  const wrap = node('div', 'ask-reply');
  const trail = savedTrail(message); if (trail) wrap.append(trail);
  if (text.trim()) wrap.append(markdown(text));
  if (change) {
    const line = node('div', 'ask-change');
    line.append(node('p', '', change.undone ? `Undone: ${change.sections.join(', ')}` : change.summary || `Updated ${change.sections.join(', ')}`));
    if (!change.undone && change.undoable !== false) line.append(button('Undo', () => undo(change), 'quiet'));
    if (change.undone && change.redoable) line.append(button('Redo', () => undo(change, true), 'quiet'));
    wrap.append(line);
  }
  return wrap;
}

function header(title, back) {
  const head = node('div', 'ask-head');
  const name = node('div', 'ask-title');
  if (back) name.append(iconButton('Back to chat', 'left', back));
  name.append(node('h2', '', title));
  const actions = node('div', 'ask-actions');
  if (!back && view === 'chat') actions.append(iconButton('Chats', 'history', showChats), iconButton('New chat', 'plus', () => { chat = null; sessionStorage.removeItem(chatKey); showChat(); }));
  if (view !== 'connect' && status?.profiles?.length) actions.append(accounts());
  actions.append(iconButton('Close', 'close', close));
  append(head, name, actions);
  return head;
}

function mount(...children) {
  panel.replaceChildren(...children);
}

// A quiet menu in the style of the workspace switcher: the chosen value and a chevron, opening
// upward into a list where each choice can carry a short description.
function picker(label, choices, value, onChange) {
  const box = node('details', 'ask-pick');
  const trigger = node('summary', 'ask-pick-trigger');
  const chosen = choices.find(([id]) => id === value) || choices[0];
  trigger.setAttribute('aria-label', `${label}: ${chosen[1]}`); trigger.setAttribute('aria-haspopup', 'menu'); trigger.title = label;
  append(trigger, node('span', '', chosen[1]), iconGlyph('down'));
  const menu = node('div', 'ask-pick-menu'); menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', label);
  const items = choices.map(([id, text, detail]) => {
    const item = node('button', 'ask-pick-item'); item.type = 'button'; item.tabIndex = -1;
    item.setAttribute('role', 'menuitemradio'); item.setAttribute('aria-checked', String(id === chosen[0]));
    append(item, append(node('span', 'ask-pick-text'), node('span', 'ask-pick-label', text), detail ? node('span', 'ask-pick-detail', detail) : ''), id === chosen[0] ? iconGlyph('check') : '');
    item.addEventListener('click', () => { box.open = false; trigger.focus(); if (id !== chosen[0]) onChange(id); });
    return item;
  });
  menu.append(...items); append(box, trigger, menu);
  box.addEventListener('toggle', () => {
    trigger.setAttribute('aria-expanded', String(box.open));
    if (box.open) items[Math.max(0, choices.indexOf(chosen))].focus();
  });
  box.addEventListener('keydown', event => {
    if (event.key === 'Escape' && box.open) { event.preventDefault(); event.stopPropagation(); box.open = false; trigger.focus(); return; }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    if (!box.open) { box.open = true; return; }
    const index = items.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
    items[next].focus();
  });
  box.addEventListener('focusout', event => { if (!box.contains(event.relatedTarget)) box.open = false; });
  return box;
}

function menus() {
  const wrap = node('div', 'ask-menus');
  const options = status?.options; if (!options) return wrap;
  const model = options.models.find(item => item.id === options.model) || options.models[0];
  wrap.append(picker('Model', options.models.map(item => [item.id, item.label, item.description]), model.id, value => choose(value)));
  // Models with no effort levels, such as Cursor's Auto, get no effort menu.
  if (model.efforts.length) wrap.append(picker('Reasoning effort', model.efforts.map(effort => [effort, EFFORTS[effort] || effort]), options.effort, value => choose(model.id, value)));
  return wrap;
}

async function choose(model, effort) {
  const options = status.options, chosen = options.models.find(item => item.id === model);
  const next = effort || (chosen.efforts.includes(options.effort) ? options.effort : chosen.effort);
  try { status.options = (await call('settings', { provider: status.provider, model, effort: next })).options; }
  catch (error) { panel?.querySelector('.ask-thread')?.append(node('p', 'ask-error', error.message)); }
  panel?.querySelector('.ask-menus')?.replaceWith(menus());
}

function composer() {
  const form = node('form', 'ask-composer');
  const slot = node('div', 'ask-context-slot');
  const box = node('div', 'ask-input');
  const input = node('textarea'); input.rows = 1; input.placeholder = 'Ask, or say what to improve'; input.setAttribute('aria-label', 'Message');
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 200)}px`; });
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); } });
  const send = node('button', 'ask-send'); send.type = 'submit';
  const setRunning = on => { send.replaceChildren(iconGlyph(on ? 'stop' : 'send')); send.setAttribute('aria-label', on ? 'Stop' : 'Send'); send.title = on ? 'Stop' : 'Send'; };
  setRunning(Boolean(running));
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (running) { if (chat) call(`chats/${chat.id}/interrupt`, {}); return; }
    const text = input.value.trim(); if (!text) return;
    input.value = ''; input.style.height = 'auto'; ask(text, setRunning);
  });
  append(box, slot, input, append(node('div', 'ask-tools'), menus(), send));
  form.append(box);
  box.addEventListener('click', event => { if (event.target === box) input.focus(); });
  queueMicrotask(() => { paintContext(); input.focus({ preventScroll: true }); });
  return form;
}

function markSvg(provider) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const shape = document.createElementNS(svg.namespaceURI, 'path');
  shape.setAttribute('d', MARKS[provider]?.path || ''); shape.setAttribute('fill-rule', 'evenodd');
  svg.append(shape);
  return svg;
}

// An empty chat shows the connected provider's mark as an outlined silhouette, as Claude Code
// and Codex do.
function mark() {
  const wrap = node('div', 'ask-mark'); wrap.setAttribute('aria-hidden', 'true');
  if (status?.provider) wrap.append(markSvg(status.provider));
  return wrap;
}

const PROVIDERS = { claude: 'Claude', codex: 'ChatGPT', cursor: 'Cursor' };
// What each provider needs, as one short line with its install command.
const INSTALL = {
  claude: ['Needs Claude Code', 'npm install -g @anthropic-ai/claude-code'],
  codex: ['Needs Codex', 'npm install -g @openai/codex'],
  cursor: ['Needs the Cursor CLI', 'curl https://cursor.com/install -fsS | bash'],
};

// Switching accounts shows at once: the avatar, logo and model menus repaint from what the panel
// already knows, and the reply only fills in an account's menus the first time.
const known = {};
async function switchTo(profile) {
  const before = status;
  known[status.profile] = status.options;
  const options = known[profile.id] ?? (profile.provider === status.provider ? status.options : null);
  status = { ...status, profile: profile.id, provider: profile.provider, options };
  repaintAccount();
  try { status = await call('profile', { profile: profile.id }); known[status.profile] = status.options; }
  catch (error) {
    status = before;
    repaintAccount();
    panel?.querySelector('.ask-thread')?.append(node('p', 'ask-note ask-error', error.message || 'The account did not switch.'));
    return;
  }
  repaintAccount();
}

function repaintAccount() {
  if (!panel) return;
  const focused = panel.querySelector('.ask-account')?.contains(document.activeElement);
  panel.querySelector('.ask-account')?.replaceWith(accounts());
  panel.querySelector('.ask-menus')?.replaceWith(menus());
  panel.querySelector('.ask-mark')?.replaceWith(mark());
  if (focused) panel.querySelector('.ask-account summary')?.focus({ preventScroll: true });
}

// The account switcher, like Discord's: every signed-in account, the active one checked, a
// sign-out button per account, and Add account.
function accounts() {
  const box = node('details', 'ask-account');
  const active = status.profiles.find(item => item.id === status.profile) || status.profiles[0];
  const trigger = node('summary', 'ask-avatar'); trigger.append(markSvg(active.provider));
  trigger.setAttribute('aria-label', `Account: ${PROVIDERS[active.provider]}, ${active.method}`); trigger.title = 'Account';
  const menu = node('div', 'ask-account-menu'); menu.setAttribute('role', 'menu');
  for (const profile of status.profiles) {
    const row = node('div', 'ask-account-row');
    const pick = node('button', 'ask-account-pick'); pick.type = 'button';
    pick.setAttribute('role', 'menuitemradio'); pick.setAttribute('aria-checked', String(profile.id === active.id));
    const badge = node('span', 'ask-avatar'); badge.append(markSvg(profile.provider));
    append(pick, badge, append(node('span', 'ask-pick-text'), node('span', 'ask-pick-label', PROVIDERS[profile.provider]), node('span', 'ask-pick-detail', profile.method || 'Signed in')), profile.id === active.id ? iconGlyph('check') : '');
    pick.addEventListener('click', async () => {
      box.open = false;
      if (profile.id === active.id) return;
      switchTo(profile);
    });
    const name = `${PROVIDERS[profile.provider]} (${profile.method || 'Signed in'})`;
    const out = iconButton(`Sign out of ${name}`, 'logout', () => {
      box.open = false;
      confirmAction({
        title: `Sign out of ${name}?`, trigger: trigger,
        message: profile.id.endsWith('-key') ? 'The saved key is deleted from this computer.' : 'You can sign in again from Add account.',
        action: 'Sign out',
        onConfirm: async () => {
          await call('disconnect', { profile: profile.id }); status = await call('status');
          if (status.provider) showChat(); else showConnect();
        },
      });
    });
    append(row, pick, out); menu.append(row);
  }
  const add = node('button', 'ask-account-add'); add.type = 'button';
  append(add, iconGlyph('plus'), node('span', '', 'Add account'));
  add.addEventListener('click', () => { box.open = false; showConnect(); });
  menu.append(add);
  append(box, trigger, menu);
  box.addEventListener('keydown', event => { if (event.key === 'Escape' && box.open) { event.preventDefault(); event.stopPropagation(); box.open = false; trigger.focus(); } });
  box.addEventListener('focusout', event => { if (!box.contains(event.relatedTarget)) box.open = false; });
  return box;
}

function showChat() {
  view = 'chat';
  const thread = node('div', 'ask-thread');
  if (!chat?.messages?.length) thread.append(mark());
  for (const message of chat?.messages || []) {
    if (message.role === 'student') { const card = sentContext(message); if (card) thread.append(card); }
    thread.append(messageNode(message));
  }
  mount(header('Ask agent'), thread, composer());
  thread.scrollTop = thread.scrollHeight;
}

async function showChats() {
  view = 'chats';
  const list = node('ul', 'ask-list');
  mount(header('Chats', showChat), list);
  const { chats } = await call('chats');
  for (const entry of chats) {
    const row = node('li'); if (entry.id === chat?.id) row.setAttribute('aria-current', 'true');
    const open = node('button', 'ask-row');
    append(open, node('span', 'ask-row-title', entry.title), node('span', 'ask-row-meta', [entry.place, new Date(entry.updated).toLocaleDateString()].filter(Boolean).join(' · ')));
    open.addEventListener('click', async () => { chat = await call(`chats/${entry.id}`); sessionStorage.setItem(chatKey, chat.id); showChat(); });
    const remove = iconButton('Delete chat', 'trash', async () => { await call(`chats/${entry.id}/delete`, {}); if (entry.id === chat?.id) { chat = null; sessionStorage.removeItem(chatKey); } row.remove(); });
    append(row, open, remove); list.append(row);
  }
  if (!chats.length) list.append(node('li', 'ask-empty', 'No chats yet.'));
}

function showConnect(message = '') {
  view = 'connect';
  const rows = node('div', 'ask-rows');
  for (const [provider, name] of Object.entries(PROVIDERS)) {
    const info = status?.providers?.[provider] || {};
    const row = node('div', 'ask-row-provider');
    row.append(node('h3', '', name));
    if (!info.installed) {
      const [need, command] = INSTALL[provider];
      row.append(append(node('p', 'ask-note ask-install'), node('span', '', need), node('code', 'inline-code', command)));
      rows.append(row); continue;
    }
    const actions = node('div', 'cluster');
    const key = node('form', 'ask-key'); key.hidden = true;
    const field = node('input'); field.type = 'password'; field.autocomplete = 'off'; field.placeholder = `${{ claude: 'Anthropic', codex: 'OpenAI', cursor: 'Cursor' }[provider]} API key`; field.setAttribute('aria-label', field.placeholder);
    const save = node('button', 'primary', 'Save'); save.type = 'submit';
    append(key, field, save);
    key.addEventListener('submit', async event => {
      event.preventDefault();
      try { await call('connect', { provider, key: field.value }); field.value = ''; await refresh(); }
      catch (error) { showConnect(error.message); }
    });
    // Add account marks the ways already connected instead of offering them again.
    const has = method => status?.profiles?.some(item => item.id === `${provider}-${method}`);
    const signIn = has('subscription')
      ? append(node('span', 'ask-connected'), iconGlyph('check'), node('span', '', 'Signed in'))
      : button('Sign in', async () => {
        try {
          signIn.disabled = true; signIn.textContent = 'Waiting for sign-in …';
          await call('connect', { provider }); waitForSignIn(provider, signIn);
        } catch (error) { showConnect(error.message); }
      }, 'primary');
    if (!has('subscription')) signIn.setAttribute('aria-label', `Sign in with ${name}`);
    actions.append(signIn, has('key')
      ? append(node('span', 'ask-connected'), iconGlyph('check'), node('span', '', 'API key saved'))
      : button('Use API key', () => { key.hidden = false; field.focus(); }, 'quiet'));
    append(row, actions, key); rows.append(row);
  }
  const children = [header(status?.profiles?.length ? 'Add account' : 'Ask agent', status?.profiles?.length ? showChat : null), rows];
  if (message) children.push(node('p', 'ask-note ask-error', message));
  mount(...children);
}

async function refresh() {
  status = await call('status');
  if (status.provider) showChat(); else showConnect();
}

// What the panel needs to open, fetched once while the page is idle so opening is instant: the
// accounts, the chat this tab had open, and the Markdown lexer.
let warming = null;
function warm() {
  const saved = !chat && sessionStorage.getItem(chatKey);
  warming ||= Promise.all([
    loadMarked().catch(() => {}),
    call('status').then(value => { status = value; }),
    saved ? call(`chats/${saved}`).then(value => { chat = value; }).catch(() => {}) : null,
  ]).catch(error => { warming = null; throw error; });
  return warming;
}

// After opening from the preloaded state, a background check catches accounts that changed
// elsewhere; the panel redraws only then.
function recheck() {
  const before = status;
  call('status').then(value => {
    status = value;
    const same = value.profile === before?.profile && value.profiles?.length === before?.profiles?.length;
    if (!same && panel && !running && view !== 'chats') { if (value.provider) showChat(); else showConnect(); }
  }).catch(() => {});
}

// Waits for the browser sign-in to finish, then makes the new account active and returns to the
// chat. Earlier accounts are ignored: only an account that was not there before ends the wait.
function waitForSignIn(provider, trigger) {
  const id = `${provider}-subscription`;
  const note = node('p', 'ask-note', 'Finish signing in in your browser.');
  panel.append(note);
  let tries = 0;
  const timer = setInterval(async () => {
    if (!panel?.open || view !== 'connect' || ++tries > 90) {
      clearInterval(timer); note.remove();
      if (trigger?.isConnected) { trigger.disabled = false; trigger.textContent = 'Sign in'; }
      return;
    }
    const value = await call('status?fresh=1').catch(() => null);
    if (!value?.profiles?.some(item => item.id === id)) return;
    clearInterval(timer);
    await call('profile', { profile: id });
    status = await call('status');
    showChat();
  }, 2000);
}

function viewState(item) {
  const state = { route: location.hash.slice(1) };
  const chosen = item?.material?.closest('fieldset')?.querySelector('input:checked');
  if (chosen) state.chosen = chosen.closest('label')?.textContent.trim().slice(0, 200) || '';
  return state;
}

// The agent's work during a turn, kept apart from the answer: its thinking, the notes it writes
// before tool calls and its steps. While it works the log is open, bounded and follows its end;
// then it folds to "Worked for 12 s · 4 steps" above the answer. Streamed text goes into one
// text node per entry, flushed once a frame, so a long log never slows the panel.
function workTrail() {
  const element = node('details', 'ask-work'), summary = node('summary'), now = node('span', 'ask-work-now', 'Thinking …');
  const count = node('span', 'ask-work-count'), list = node('ol'), started = Date.now();
  append(summary, now, count, iconGlyph('down')); append(element, summary, list);
  element.dataset.running = ''; element.open = true;
  let entry = null, last = '', frame = 0, ticker = 0;
  const pending = new Map();
  const counted = () => { const n = list.children.length; count.textContent = n > 1 ? `${n} steps` : ''; };
  const flush = () => {
    frame = 0;
    const near = list.scrollHeight - list.scrollTop - list.clientHeight < 24;
    for (const [text, more] of pending) text.appendData(more);
    pending.clear();
    if (near) list.scrollTop = list.scrollHeight;
  };
  const stream = (text, more) => { pending.set(text, (pending.get(text) || '') + more); frame ||= requestAnimationFrame(flush); };
  function close() {
    // A finished note shows its math typeset; while it streams it stays plain text.
    if (entry?.kind === 'note') { flush(); entry.item.replaceChildren(...noteContent(entry.body.data)); }
    if (entry?.kind === 'thinking') {
      clearInterval(ticker);
      entry.label.textContent = `Thought for ${Math.max(1, Math.round((Date.now() - entry.since) / 1000))} s`;
    }
    entry = null;
  }
  function open(kind) {
    if (entry?.kind === kind) return entry;
    close();
    const item = node('li', `ask-work-${kind}`), body = document.createTextNode('');
    entry = { kind, item, body, since: Date.now() };
    if (kind === 'thinking') {
      entry.label = node('span', 'ask-work-label', 'Thinking');
      const since = entry.since;
      const tick = () => { const s = Math.round((Date.now() - since) / 1000); now.textContent = s ? `Thinking · ${s} s` : 'Thinking …'; };
      tick(); ticker = setInterval(tick, 1000);
      append(item, entry.label, append(node('div', 'ask-work-text'), body));
    } else item.append(body);
    list.append(item); counted();
    return entry;
  }
  return {
    element,
    thinking(text) { const current = open('thinking'); if (text) stream(current.body, text); },
    note(text) { if (entry?.kind !== 'note') now.textContent = 'Writing …'; stream(open('note').body, text); },
    // "Working" names no step of its own, so it shows only as the current line.
    step(text) {
      close();
      if (text !== last && text !== 'Working') { list.append(node('li', 'ask-work-step', text)); counted(); }
      last = text; now.textContent = `${text} …`;
    },
    finish() {
      if (frame) { cancelAnimationFrame(frame); flush(); }
      close(); clearInterval(ticker);
      delete element.dataset.running; element.open = false;
      now.textContent = `Worked for ${Math.max(1, Math.round((Date.now() - started) / 1000))} s`; counted();
      if (!list.children.length) element.hidden = true;
    },
  };
}

function noteContent(text) {
  const line = /\\\(|\$/.test(text) ? markdown(text).querySelector('p') : null;
  return line ? [...line.childNodes] : [text];
}

// A saved answer's log, folded, as the live one ends.
function savedTrail(message) {
  if (!message.log?.length) return null;
  const element = node('details', 'ask-work'), summary = node('summary'), list = node('ol');
  const steps = message.log.length;
  append(summary, node('span', 'ask-work-now', `Worked for ${Math.max(1, message.worked || 0)} s`), node('span', 'ask-work-count', steps > 1 ? `${steps} steps` : ''), iconGlyph('down'));
  for (const item of message.log) {
    if (item.kind === 'note') { list.append(append(node('li', 'ask-work-note'), ...noteContent(item.text))); continue; }
    if (item.kind !== 'thinking') { list.append(node('li', `ask-work-${item.kind}`, item.text)); continue; }
    const line = append(node('li', 'ask-work-thinking'), node('span', 'ask-work-label', `Thought for ${Math.max(1, item.seconds)} s`));
    if (item.text) line.append(node('div', 'ask-work-text', item.text));
    list.append(line);
  }
  return append(element, summary, list);
}

async function ask(text, setRunning) {
  const thread = panel.querySelector('.ask-thread');
  thread.querySelector('.ask-mark')?.remove();
  const item = current();
  const message = { role: 'student', text, quote: item?.kind === 'selection' ? item.quote || item.anchor.quote : '', section: item ? (item.kind === 'section' ? item.title : placeOf(item)) : '' };
  const card = sentContext(message); if (card) thread.append(card);
  thread.append(node('div', 'ask-user', text));
  const reply = node('div', 'ask-reply'), answer = node('div', 'ask-answer');
  const work = workTrail();
  append(reply, work.element, answer); thread.append(reply);
  thread.scrollTop = thread.scrollHeight;
  // Follow the answer while the student stays at the bottom; scrolling up stops following.
  const follow = change => {
    const near = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 96;
    change();
    if (near) thread.scrollTop = thread.scrollHeight;
  };
  const body = { chat: chat?.id || null, text, anchor: item?.anchor || null, scope: item?.kind || 'selection', quote: message.quote, section: message.section, view: viewState(item), place: item ? placeOf(item) : '' };
  if (item) pending = item;
  Object.assign(live, { selection: null, dropped: false }); sectionChanged();
  running = true; setRunning(true);
  let streamed = '', edited = false, edit = '', frame = 0;
  try {
    const response = await call('send', body);
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).error || 'The preview refused the message.');
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      // One split per chunk keeps a long stream linear; the last piece waits for its line end.
      const lines = (buffer + decoder.decode(value, { stream: true })).split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === 'chat') { chat = { id: event.id, messages: [] }; sessionStorage.setItem(chatKey, event.id); }
        else if (event.type === 'status') work.step(event.text);
        else if (event.type === 'thinking') follow(() => work.thinking(event.text));
        // Until the turn ends, text belongs to the log: before a tool call it is narration, and
        // the answer is known only at the end. Codex marks its answer, which streams below.
        else if (event.type === 'note') follow(() => work.note(event.text));
        else if (event.type === 'delta') {
          streamed += event.text;
          frame ||= requestAnimationFrame(() => { frame = 0; follow(() => answer.replaceChildren(...markdown(streamed).childNodes)); });
        }
        else if (event.type === 'message') { cancelAnimationFrame(frame); work.finish(); edit = event.message.change?.sections?.[0] || ''; follow(() => reply.replaceWith(messageNode(event.message))); }
        else if (event.type === 'error') { work.finish(); answer.replaceChildren(node('p', 'ask-error', event.text)); }
        else if (event.type === 'done') edited = event.edited;
      }
    }
  } catch (error) {
    work.finish(); answer.replaceChildren(node('p', 'ask-error', error.message || 'The preview stopped.'));
  } finally {
    running = null; if (panel?.isConnected) setRunning(false);
  }
  // The page takes the edit while the panel fetches the saved chat.
  const applying = edited ? applyEdit(edit) : null;
  if (chat) chat = await call(`chats/${chat.id}`);
  await applying;
}

// The preview rebuilt the course after an edit, and the page takes the new content in place, as
// morphing page refreshes do (Turbo 8): nothing reloads and the reader does not move.
// 1. The data module is fetched and replaces the shared data object.
// 2. The app redraws into a hidden layer behind the current page, which stays on screen.
// 3. While diagrams and math lay out there, the section being read is pinned to its place.
// 4. The new layer fades in and the old page goes; the edited section is marked.
// Narrow screens scroll the window, so there the page swaps at once with the same pinning.
async function applyEdit(section) {
  let fresh;
  // data.mjs is `export default <JSON>;`, so it is read as text: no module cache to get past.
  try {
    const text = await (await fetch(`data.mjs?v=${Date.now().toString(36)}`, { cache: 'no-store' })).text();
    fresh = JSON.parse(text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1));
  } catch { reloadAt(section); return; }
  const anchor = anchorAt(section), old = document.querySelector('#app');
  const layered = !narrow.matches && old;
  let next = null;
  if (layered) {
    next = old.cloneNode(false); next.classList.add('app-next');
    old.before(next); old.inert = true; old.setAttribute('aria-hidden', 'true');
  }
  try {
    for (const key of Object.keys(data)) delete data[key];
    Object.assign(data, fresh);
    dispatchEvent(new CustomEvent('course-data'));
    anchor.pin();
    await settled(anchor);
  } catch { reloadAt(section); return; }
  if (next) {
    if (!reduced.matches) { next.classList.add('app-shown'); await new Promise(resolve => setTimeout(resolve, 200)); }
    const kept = scroller().scrollTop;
    old.remove(); next.classList.remove('app-next', 'app-shown');
    scroller().scrollTo({ top: kept, behavior: 'instant' });
  }
  arrive(section);
}

const scroller = () => narrow.matches ? document.scrollingElement : document.querySelector('main');

// The top-level block a section title names in the page shown.
function blockFor(section) {
  const main = document.querySelector('main');
  const heading = section && main && [...main.querySelectorAll('h2, h3')].find(item => item.textContent.trim() === section);
  return heading?.closest('[data-block-index]') || heading || null;
}

// Where the reader is: the edited section when it is on screen, else the first block in view.
// pin() scrolls the redrawn page so that block sits where it sat before.
function anchorAt(section) {
  const main = document.querySelector('main');
  if (!main) return { pin() {} };
  const top = Math.max(0, main.getBoundingClientRect().top);
  const seen = element => { const box = element.getBoundingClientRect(); return box.bottom > top && box.top < innerHeight; };
  const edited = blockFor(section);
  const element = edited && seen(edited) ? edited
    : [...main.querySelectorAll('[data-block-index]')].find(item => !item.parentElement.closest('[data-block-index]') && item.getBoundingClientRect().bottom > top);
  // The page scrolls smoothly for its own links, so pinning scrolls instantly.
  const jump = (box, top) => box.scrollTo({ top, behavior: 'instant' });
  if (!element) { const y = scroller()?.scrollTop || 0; return { pin() { if (scroller()) jump(scroller(), y); return 0; } }; }
  const key = element.dataset.block, index = element.dataset.blockIndex;
  const title = element.querySelector('h2, h3')?.textContent.trim(), offset = element.getBoundingClientRect().top;
  const find = () => {
    const page = document.querySelector('main'); if (!page) return null;
    if (key) return page.querySelector(`[data-block="${CSS.escape(key)}"]`);
    return (title && blockFor(title)) || [...page.querySelectorAll(`[data-block-index="${CSS.escape(index)}"]`)].find(item => !item.parentElement.closest('[data-block-index]'));
  };
  return {
    pin() {
      const now = find(), box = scroller(); if (!now || !box) return 0;
      const moved = now.getBoundingClientRect().top - offset;
      if (moved) jump(box, box.scrollTop + moved);
      return Math.abs(moved);
    },
  };
}

// Waits until the redrawn page stops changing height (diagrams and math lay out on frames),
// pinning the reader each frame; at most half a second.
async function settled(anchor) {
  const end = performance.now() + 500;
  let height = -1, still = 0;
  while (still < 2 && performance.now() < end) {
    await new Promise(requestAnimationFrame);
    const moved = anchor.pin();
    const now = document.querySelector('main')?.scrollHeight || 0;
    still = now === height && moved < 1 ? still + 1 : 0; height = now;
  }
}

// Marks the edited section; one that is off screen glides into view first.
function arrive(section) {
  const target = blockFor(section);
  if (!target) return;
  const box = target.getBoundingClientRect();
  if (box.bottom < 0 || box.top > innerHeight) target.scrollIntoView({ block: 'center', behavior: reduced.matches ? 'auto' : 'smooth' });
  target.classList.remove('search-arrival'); void target.offsetWidth; target.classList.add('search-arrival');
}

// After a reload: marks the changed section as search results do, bringing it into view.
function flash(section, block) {
  const target = blockFor(section);
  if (!target) return;
  target.scrollIntoView({ block }); target.classList.remove('search-arrival'); void target.offsetWidth; target.classList.add('search-arrival');
}

function reloadAt(section) {
  sessionStorage.setItem(restoreKey, JSON.stringify({ chat: chat?.id, section, scroll: document.querySelector('main')?.scrollTop || 0 }));
  location.replace(`/_v/${Date.now().toString(36)}/${location.hash}`);
}

// Undo puts the page back as it was before the edit; Redo puts the edit back. Both apply in place.
async function undo(change, redo = false) {
  try { await call(`chats/${chat.id}/${redo ? 'redo' : 'undo'}/${change.id}`, {}); await applyEdit(change.sections[0]); chat = await call(`chats/${chat.id}`); if (view === 'chat') showChat(); }
  catch (error) { panel.querySelector('.ask-thread')?.append(node('p', 'ask-error', error.message)); }
}

function close() {
  if (!panel) return;
  const dialog = panel; panel = null;
  if (launcher) launcher.hidden = false;
  watch?.abort(); watch = null;
  dialog.close(); dialog.remove();
  pending?.focus?.()?.focus({ preventScroll: true });
}

function ensurePanel() {
  if (panel) return;
  document.querySelector('dialog.reference-panel')?.close();
  const dialog = node('dialog', 'reference-panel ask-panel');
  panel = dialog;
  dialog.setAttribute('aria-label', 'Ask agent');
  dialog.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } });
  document.body.append(dialog);

  // The course outline can take focus first when entering the narrow layout.
  let focused;
  dialog.addEventListener('focusin', event => { focused = event.target; });
  const layout = () => {
    if (panel !== dialog) return;
    const isDocked = dialog.open && !dialog.matches(':modal');
    const available = document.querySelector('main').offsetWidth + (isDocked ? dialog.offsetWidth : 0);
    const docked = !narrow.matches && available >= dockMin;
    if (dialog.open && isDocked === docked) return;
    const previous = focused;
    dialog.close();
    if (docked) dialog.show(); else dialog.showModal();
    if (previous && dialog.contains(previous)) previous.focus({ preventScroll: true });
  };
  const observer = new ResizeObserver(layout);
  const observePage = () => {
    observer.disconnect();
    observer.observe(document.querySelector('main'), { box: 'border-box' });
  };
  const lifecycle = new AbortController();
  for (const event of ['hashchange', 'course-data']) {
    addEventListener(event, observePage, { signal: lifecycle.signal });
  }
  dialog.addEventListener('close', () => {
    if (dialog.open) return;
    observer.disconnect();
    lifecycle.abort();
    if (panel === dialog) close();
  });
  layout();
  observePage();
}

// Opens the panel; a passage from the selection toolbar becomes the pinned context.
export async function openAsk(item = null) {
  if (item) { Object.assign(live, { selection: item, dropped: false }); pending = item; }
  const opened = Boolean(panel);
  ensurePanel(); watchPage();
  if (launcher) launcher.hidden = true;
  live.section = live.source?.section() || null;
  if (opened && panel.querySelector('.ask-composer')) { paintContext(); panel.querySelector('.ask-input textarea')?.focus({ preventScroll: true }); return; }
  try {
    const ready = Boolean(status);
    await warm();
    if (status.provider) showChat(); else showConnect();
    if (ready) recheck();
  } catch (error) { mount(header('Ask agent'), node('p', 'ask-note ask-error', error.message || 'Ask agent needs the local preview.')); }
}

async function restore() {
  const saved = sessionStorage.getItem(restoreKey); if (!saved) return;
  sessionStorage.removeItem(restoreKey);
  const { chat: id, section, scroll } = JSON.parse(saved);
  await new Promise(resolve => setTimeout(resolve, 300));
  const main = document.querySelector('main'); if (main) main.scrollTop = scroll;
  flash(section, 'start');
  if (id) { chat = await call(`chats/${id}`).catch(() => null); openAsk(); }
}

// Ask agent buttons exist only in the local desktop preview. They keep the page's text
// selection, which becomes the chat's context.
const askable = !data.hosted && !matchMedia('(pointer: coarse)').matches;
// Ctrl/Command+Alt+K opens the panel on every page, as the button does.
if (askable) addEventListener('keydown', event => {
  if (event.key.toLowerCase() !== 'k' || !event.altKey || !(event.ctrlKey || event.metaKey) || event.defaultPrevented) return;
  event.preventDefault();
  openAsk(live.source?.selection() || null);
});

function asking(button) {
  button.addEventListener('pointerdown', event => event.preventDefault());
  button.addEventListener('click', () => openAsk(live.source?.selection() || null));
  return button;
}

// A labelled Ask agent button for a workspace's own toolbar, such as the coding workspace.
export function askButton(className) {
  if (!askable) return null;
  const control = node('button', className); control.type = 'button';
  append(control, iconGlyph('sparkle'), node('span', '', 'Ask agent'));
  return asking(control);
}

// The corner button sits beside the contents button and hides while the panel is open.
let launcher = null;
if (askable) {
  (window.requestIdleCallback || setTimeout)(() => warm().catch(() => {}));
  launcher = asking(iconButton('Ask agent', 'sparkle', () => {})); launcher.classList.add('ask-launch');
  document.body.append(launcher);
}

if (!data.hosted) restore();
