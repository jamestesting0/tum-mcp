import { openSearch } from './search.mjs';
import data from '../../data.mjs';
import { enableCompletion } from './completion.mjs';
import { node, studyText, button, append, focusHeading, scrollReadingTo } from './dom.mjs';

const paths = {
  search: 'M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14m5 12 4.5 4.5',
  book: 'M12 5C8 3 5 3 3 4v15c3-1 6-1 9 1m0-15c4-2 7-2 9-1v15c-3-1-6-1-9 1V5',
  lecture: 'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
  pencil: 'm5 15 10-10 4 4L9 19H5v-4m8-8 4 4',
  target: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18m0 4a5 5 0 1 0 0 10a5 5 0 1 0 0-10m0 4a1 1 0 1 0 0 2a1 1 0 1 0 0-2',
  updown: 'm8 9 4-4 4 4m-8 6 4 4 4-4',
  left: 'm15 18-6-6 6-6', right: 'm9 6 6 6-6 6',
  forward: 'M5 12h14m-6-6 6 6-6 6',
  menu: 'M4 7h16M4 12h16M4 17h16',
  undo: 'M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
  reset: 'M3 12a9 9 0 1 0 2.64-6.36L3 8.3M3 3v5.3h5.3',
  contents: 'M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01',
  play: 'M8 5v14l11-7z',
  comment: 'M4 4h16v12H8l-4 4z',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  close: 'm6 6 12 12M18 6 6 18',
  check: 'm5 12 4 4L19 6',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  sun: 'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  moon: 'M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14',
  pause: 'M7 5h3v14H7zm7 0h3v14h-3z',
  volume: 'M4 9v6h4l5 4V5L8 9zm12.5-.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12',
  muted: 'M4 9v6h4l5 4V5L8 9zm13 0 5 6m0-6-5 6',
  captions: 'M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2m6 5.3a2.5 2.5 0 1 0 0 3.4m6.5-3.4a2.5 2.5 0 1 0 0 3.4',
  expand: 'M4 9V4h5m6 0h5v5m0 6v5h-5m-6 0H4v-5',
  shrink: 'M9 4v5H4m16 0h-5V4m0 16v-5h5M4 15h5v5',
  headphones: 'M4 16v-4a8 8 0 0 1 16 0v4M4 15h3v6H5a1 1 0 0 1-1-1zm16 0h-3v6h2a1 1 0 0 0 1-1z',
  download: 'M12 4v11m-5-5 5 5 5-5M5 20h14',
  back: 'M4 12a8 8 0 1 0 2.34-5.66L4 8.7M4 4v4.7h4.7',
  ahead: 'M20 12a8 8 0 1 1-2.34-5.66L20 8.7M20 4v4.7h-4.7',
  chapterBack: 'M6 5v14M18 6l-8 6 8 6z',
  chapterNext: 'M18 5v14M6 6l8 6-8 6z',
};
export function iconGlyph(icon) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', paths[icon]); svg.append(path); return svg;
}
export function iconButton(label, icon, handler) {
  const control = button('', handler, 'icon-button quiet');
  control.setAttribute('aria-label', label); control.title = label; control.append(iconGlyph(icon));
  return control;
}
const contentsKey = 'study-space:contents', wide = matchMedia('(min-width: 1200px)'), phone = matchMedia('(max-width: 799px)');
const headingSelector = 'h2, h3, h4, h5, h6';
let contentsSession = null;
// Outlines the headings the reading column currently shows, in every workspace, and marks the one being read.
// The Contents button shows or hides it: wide screens dock it beside the text and remember the choice;
// narrower screens open it over the page until a heading is chosen. A workspace home lists its
// items already, so it has no outline.
export function contentsOutline(reading, enabled = true) {
  contentsSession?.abort(); contentsSession = new AbortController();
  if (!enabled) { document.documentElement.dataset.contents = 'closed'; return; }
  const { signal } = contentsSession, layout = reading.parentElement;
  const nav = node('nav', 'page-outline'), label = node('p', 'small page-outline-title', 'On this page');
  nav.id = 'page-outline'; label.id = 'page-outline-title'; nav.setAttribute('aria-labelledby', label.id);
  const toggle = iconButton('Show contents', 'contents', () => {
    if (wide.matches) { docked = !docked; try { localStorage.setItem(contentsKey, JSON.stringify(docked ? 'open' : 'closed')); } catch { /* the choice lasts for this page */ } }
    else overlay = !overlay;
    apply();
  });
  toggle.classList.add('contents-toggle'); toggle.setAttribute('aria-controls', nav.id);
  let docked = true, overlay = false, headings = [], links = [], frame = 0, pinned = null, pinnedTop = 0;
  try { docked = JSON.parse(localStorage.getItem(contentsKey)) !== 'closed'; } catch { /* default to docked */ }
  const scroller = () => phone.matches ? document.scrollingElement : layout.closest('main');
  function apply() {
    const available = links.length > 1, open = available && (wide.matches ? docked : overlay);
    toggle.hidden = !available; layout.classList.toggle('has-contents', available);
    document.documentElement.dataset.contents = open ? 'open' : 'closed';
    toggle.setAttribute('aria-expanded', String(open));
    const name = open ? 'Hide contents' : 'Show contents'; toggle.setAttribute('aria-label', name); toggle.title = name;
  }
  function mark(active) {
    for (const [link] of links) if (link === active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current');
  }
  function update() {
    frame = 0;
    if (!nav.isConnected) return;
    const box = scroller(); if (!box || !links.length) return;
    // A chosen entry stays marked until the reader scrolls; the end of the page marks the last heading.
    if (pinned && Math.abs(box.scrollTop - pinnedTop) < 2) return mark(pinned);
    pinned = null;
    const line = innerHeight / 3;
    let active = null;
    if (box.scrollTop > 0 && box.scrollTop + box.clientHeight >= box.scrollHeight - 2) active = links[links.length - 1][0];
    else for (const [link, target] of links) { if (target.getBoundingClientRect().top > line) break; active = link; }
    mark(active);
  }
  function entry(heading) {
    const link = node('a', '', heading.innerText.trim()); link.href = location.hash || '#';
    link.addEventListener('click', event => {
      if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); scrollReadingTo(heading);
      if (heading.matches(headingSelector)) focusHeading(heading); else heading.focus({ preventScroll: true });
      pinned = link; pinnedTop = scroller()?.scrollTop ?? 0; mark(link);
      if (!wide.matches) { overlay = false; apply(); }
    });
    links.push([link, heading]); return append(node('li'), link);
  }
  function refresh() {
    if (signal.aborted) return;
    // Headings, plus sections a renderer marks with data-contents-entry (such as exercise disclosures).
    const found = [...reading.querySelectorAll(`${headingSelector}, [data-contents-entry]`)].filter(heading => heading.getClientRects().length && heading.innerText.trim()
      && !heading.closest('.feedback, .citation-panel, .visually-hidden, [data-comment-ui], dialog, .exam-map-card, .exam-entry-body, .pill-content'));
    if (found.length === headings.length && found.every((heading, index) => heading === headings[index])) return;
    headings = found; links = []; pinned = null;
    const list = node('ol'), parents = [];
    for (const heading of found) {
      const level = heading.matches(headingSelector) ? Number(heading.tagName.slice(1)) : Number(heading.dataset.contentsLevel || 2);
      while (parents.length && parents.at(-1).level >= level) parents.pop();
      const item = entry(heading), parent = parents.at(-1)?.item;
      if (parent) {
        parent.lastElementChild?.tagName === 'OL' || parent.append(node('ol'));
        parent.lastElementChild.append(item);
      } else list.append(item);
      parents.push({ level, item });
    }
    nav.replaceChildren(label, list); apply(); update();
  }
  const observer = new MutationObserver(() => requestAnimationFrame(refresh));
  observer.observe(reading, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'open'] });
  signal.addEventListener('abort', () => observer.disconnect());
  const schedule = () => { frame ||= requestAnimationFrame(update); };
  addEventListener('scroll', schedule, { passive: true, signal });
  layout.closest('main')?.addEventListener('scroll', schedule, { passive: true, signal });
  wide.addEventListener('change', () => { overlay = false; apply(); }, { signal });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && overlay && !wide.matches) { overlay = false; apply(); toggle.focus(); }
  }, { signal });
  document.addEventListener('pointerdown', event => {
    if (overlay && !wide.matches && !nav.contains(event.target) && !toggle.contains(event.target)) { overlay = false; apply(); }
  }, { signal });
  layout.append(nav, toggle); refresh();
}

let openPicker;
function closePicker(focus = false) {
  if (!openPicker) return;
  const picker = openPicker; openPicker = null;
  picker.open = false;
  if (focus) picker.querySelector('summary').focus();
}
document.addEventListener('pointerdown', event => {
  if (openPicker && !openPicker.contains(event.target)) closePicker();
});
function workspacePicker(context) {
  closePicker();
  const name = value => ({ study: 'Study', exercises: 'Exercises', lectures: 'Lecture', exam: 'Exam', audio: 'Audio' })[value];
  const label = node('span', 'workspace-name', name(context.workspace));
  const badge = node('span', 'workspace-badge'); badge.append(iconGlyph(({ study: 'book', exercises: 'pencil', lectures: 'lecture', exam: 'target', audio: 'headphones' })[context.workspace]));
  if ((context.workspaces || ['study']).length < 2) {
    const passive = node('div', 'workspace-current'); passive.append(badge, label); return passive;
  }
  const picker = node('details', 'workspace-picker');
  const trigger = node('summary', 'workspace-trigger');
  trigger.setAttribute('aria-label', `Switch workspace, ${name(context.workspace)}`);
  trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false');
  trigger.append(badge, label, iconGlyph('updown'));
  const menu = node('nav', 'workspace-menu'); menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Choose workspace');
  const links = context.workspaces.map(value => {
    const link = node('a', 'workspace-item'); link.href = context.workspaceHref(value);
    link.setAttribute('role', 'menuitemradio'); link.setAttribute('aria-label', name(value)); link.setAttribute('aria-checked', String(value === context.workspace)); link.tabIndex = -1;
    link.append(iconGlyph(({ study: 'book', exercises: 'pencil', lectures: 'lecture', exam: 'target', audio: 'headphones' })[value]), node('span', '', name(value)));
    if (value === context.workspace) link.append(iconGlyph('check'));
    link.addEventListener('click', event => { if (value === context.workspace) event.preventDefault(); closePicker(true); });
    menu.append(link); return link;
  });
  picker.append(trigger, menu);
  picker.addEventListener('toggle', () => {
    trigger.setAttribute('aria-expanded', String(picker.open));
    if (picker.open) { openPicker = picker; if (!menu.contains(document.activeElement)) links.find(link => link.getAttribute('aria-checked') === 'true').focus(); }
    else if (openPicker === picker) openPicker = null;
  });
  picker.addEventListener('keydown', event => {
    if (event.key === 'Escape' && picker.open) { event.preventDefault(); event.stopPropagation(); openPicker = picker; closePicker(true); }
    const index = links.indexOf(document.activeElement);
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault(); picker.open = true;
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? links.length - 1 : (index + (event.key === 'ArrowUp' ? -1 : 1) + links.length) % links.length;
      links[next].focus();
    }
  });
  picker.addEventListener('focusout', event => { if (!picker.contains(event.relatedTarget)) closePicker(); });
  return picker;
}

const expanded = new Map();
const narrow = matchMedia('(max-width: 799px)');
let refresh = () => {};
narrow.addEventListener('change', () => refresh());

// Every outline entry is a muted label over its title; a folder named "Lecture 3 · Uninformed
// search" reads as "Lecture 3" over "Uninformed search", like a unit's label over its title.
const entry = (eyebrow, title) => append(node('span', 'unit-entry'),
  ...(eyebrow ? [node('span', 'unit-label', eyebrow)] : []), studyText('span', 'unit-title', title));
const parts = label => { const at = label.indexOf(' · '); return at < 0 ? ['', label] : [label.slice(0, at), label.slice(at + 3)]; };

function outline(currentIndex) {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Course units');
  const folders = new Map(), sizes = new Map();
  for (const unit of data.units) {
    const top = unit.path?.[0];
    if (top) sizes.set(top, (sizes.get(top) || 0) + 1);
  }
  data.units.forEach((unit, index) => {
    let parent = nav;
    // A lecture with one unit is that unit's own entry, so no folder holds a single row.
    const ancestry = unit.path?.length === 1 && sizes.get(unit.path[0]) === 1 ? [] : unit.path || [];
    ancestry.forEach((label, depth) => {
      const key = JSON.stringify(ancestry.slice(0, depth + 1));
      if (!folders.has(key)) {
        const group = node('details', 'unit-group');
        group.append(append(node('summary'), entry(...parts(label))));
        const children = node('div', 'group-children'); group.append(children);
        const activePath = data.units[currentIndex]?.path || [];
        group.open = ancestry.slice(0, depth + 1).every((part, i) => part === activePath[i]) || expanded.get(key) === true;
        group.addEventListener('toggle', () => expanded.set(key, group.open));
        folders.set(key, children); parent.append(group);
      }
      parent = folders.get(key);
    });
    const link = node('a', 'unit-link study-unit-link'); link.href = `#${unit.key}/content`;
    if (index === currentIndex) link.setAttribute('aria-current', 'page');
    link.append(entry(ancestry.length ? '' : unit.label || parts(unit.path?.[0] || '')[0], unit.title));
    if (unit.provisional) link.append(node('span', 'small', unit.provisional));
    const status = node('span', 'small'); status.dataset.studyProgress = unit.key;
    link.append(status); parent.append(link);
  });
  return nav;
}

export function renderSidebar(context) {
  const sidebar = node('aside', 'sidebar'); sidebar.id = 'course-outline';
  const top = node('div', 'sidebar-top');
  // The semester belongs to the course name, so it sits inside the title block, not the page list.
  const title = node('a', 'course-title'); title.href = context.homeHref || '#home';
  title.append(node('span', 'course-name', data.course.title));
  if (data.course.semester) title.append(node('span', 'course-semester', data.course.semester));
  if (context.location === 'home') title.setAttribute('aria-current', 'page');
  const where = node('p', 'outline-context', context.context); where.setAttribute('aria-hidden', 'true');
  const toggle = iconButton('Collapse course outline', 'left', () => {
    context.collapsed = !context.collapsed; update();
  });
  toggle.className = 'icon-button outline-toggle';
  toggle.setAttribute('aria-controls', 'outline-body');
  // Search sits under the course name on every page; "/" opens it from anywhere.
  const find = node('button', 'sidebar-search'); find.type = 'button';
  find.append(iconGlyph('search'), node('span', '', 'Search'), node('kbd', '', '/'));
  find.setAttribute('aria-keyshortcuts', '/'); find.setAttribute('aria-label', 'Search'); find.title = 'Search (/)';
  find.addEventListener('click', () => openSearch(find));
  top.append(title, toggle, where, find);
  const body = node('div', 'sidebar-body'); body.id = 'outline-body';
  // Every route rebuilds the outline; each workspace's list keeps the place the student scrolled to.
  const tops = context.outlineTops ||= {};
  body.addEventListener('scroll', () => { if (!body.hidden) tops[context.workspace] = body.scrollTop; }, { passive: true });
  function restoreOutline() {
    if (body.hidden || !body.isConnected) return;
    body.scrollTop = tops[context.workspace] || 0;
    const current = body.querySelector('[aria-current="page"]');
    if (!current) return;
    const box = body.getBoundingClientRect(), item = current.getBoundingClientRect();
    if (item.top < box.top) body.scrollTop += item.top - box.top;
    else if (item.bottom > box.bottom) body.scrollTop += item.bottom - box.bottom;
  }
  sidebar.restoreOutline = restoreOutline;
  const footer = node('div', 'sidebar-footer cluster');
  function themeControl() {
    const dark = document.documentElement.dataset.theme === 'dark';
    const label = dark ? 'Use light theme' : 'Use dark theme';
    return iconButton(label, dark ? 'sun' : 'moon', () => {
      context.theme(dark ? 'light' : 'dark');
      const replacement = themeControl(); theme.replaceWith(replacement); theme = replacement; theme.focus();
    });
  }
  let theme = themeControl(); footer.append(workspacePicker(context), theme);
  const sections = node('nav'); sections.setAttribute('aria-label', 'Study sections');
  const revision = node('a', 'unit-link revision-link', 'Revision'); revision.href = '#revision?view=flashcards';
  if (context.location === 'revision') revision.setAttribute('aria-current', 'page');
  sections.append(revision);
  sections.hidden = context.showRevision === false;
  body.append(context.outline ? context.outline() : outline(typeof context.location === 'number' ? context.location : -1), sections);
  enableCompletion(body);
  const boundary = node('div', 'outline-boundary'); boundary.setAttribute('aria-hidden', 'true');
  sidebar.append(boundary, top, body, footer);
  sidebar.addEventListener('keydown', event => {
    if (!narrow.matches || context.collapsed) return;
    if (event.key === 'Escape') { event.preventDefault(); context.collapsed = true; update(); toggle.focus({ preventScroll: true }); }
    if (event.key !== 'Tab') return;
    const controls = [...sidebar.querySelectorAll('a[href],button:not(:disabled),summary')].filter(element => element.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  function update() {
    const modal = narrow.matches && !context.collapsed;
    document.documentElement.dataset.outline = context.collapsed ? 'collapsed' : 'expanded';
    document.querySelector('main')?.toggleAttribute('inert', modal);
    if (modal) { sidebar.setAttribute('role', 'dialog'); sidebar.setAttribute('aria-modal', 'true'); sidebar.setAttribute('aria-label', 'Course outline'); }
    else { sidebar.removeAttribute('role'); sidebar.removeAttribute('aria-modal'); sidebar.removeAttribute('aria-label'); }
    body.hidden = context.collapsed; footer.hidden = context.collapsed;
    if (context.collapsed) closePicker();
    toggle.setAttribute('aria-expanded', String(!context.collapsed));
    const label = context.collapsed ? 'Expand course outline' : 'Collapse course outline';
    toggle.setAttribute('aria-label', label); toggle.title = label;
    const icon = narrow.matches ? (context.collapsed ? 'menu' : 'close') : (context.collapsed ? 'right' : 'left');
    toggle.querySelector('path').setAttribute('d', paths[icon]);
    if (modal && sidebar.isConnected && !sidebar.contains(document.activeElement)) toggle.focus({ preventScroll: true });
    restoreOutline();
  }
  refresh = update; update(); return sidebar;
}

export function nextStep({ href, title, detail, activate }) {
  const nav = node('nav', 'next-step'); nav.setAttribute('aria-label', 'Up next');
  const link = node('a'); link.href = href;
  const text = node('span', 'next-step-text');
  text.append(node('span', 'eyebrow', 'Next'), studyText('span', 'next-step-title', title));
  if (detail) text.append(node('span', 'small', detail));
  link.append(text, iconGlyph('forward'));
  if (activate) link.addEventListener('click', event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); activate();
  });
  nav.append(link); return nav;
}

// Left and right arrows page practice questions and guide steps. The pager holding focus
// pages; with focus on the page itself or a tab, the practice or guide the student last
// opened or used does, so no click is needed first. Fields keep their arrows; on a radio
// button Up and Down still choose the option while Left and Right page.
const pagers = new Map();
let activePager = null;
function pagerFor(target) {
  for (const region of pagers.keys()) if (!region.isConnected) pagers.delete(region);
  const holding = [...pagers.keys()].find(region => region.contains(target));
  if (holding) return holding;
  const shown = activePager?.isConnected && activePager.getClientRects().length && (activePager.localName !== 'details' || activePager.open);
  // Focus on the page, a tab, or a heading or region the app focused (tabindex -1) is no
  // control of its own, so the arrows go to the pager last used.
  // A Guide | Solution segment opened the guide, so its arrows page that guide.
  return (target === document.body || target.matches('[role="tab"], [tabindex="-1"], .pill-panel .segment')) && shown ? activePager : null;
}
document.addEventListener('keydown', event => {
  const target = event.target;
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key) || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (target.closest('textarea, select, [contenteditable], [role="slider"]') || (target.matches('input') && target.type !== 'radio')) return;
  const region = pagerFor(target);
  if (!region) return;
  const { previous, next } = pagers.get(region), move = event.key === 'ArrowLeft' ? previous : next;
  event.preventDefault();
  const before = document.activeElement;
  if (!move.disabled) move.click();
  // Paging by key leaves focus where it was, so neither step button looks pressed.
  if ([previous, next].includes(document.activeElement) && before !== document.activeElement) {
    if (before?.isConnected && before !== document.body) before.focus({ preventScroll: true });
    else document.activeElement.blur();
  }
});
// The pager the arrows go to when focus rests on the page, such as a guide just opened.
export function usePager(region) { activePager = region; }
export const cycleIndex = (index, length) => (index + length) % length;
export function arrowPaging(region, previous, next, { active = false } = {}) {
  pagers.set(region, { previous, next });
  const use = () => { activePager = region; };
  if (active) use();
  region.addEventListener('focusin', use); region.addEventListener('pointerdown', use);
  if (region.localName === 'details') region.addEventListener('toggle', () => { if (region.open) use(); });
}
