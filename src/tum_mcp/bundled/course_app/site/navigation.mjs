import data from './data.mjs';
import { node, studyText, button, append, focusHeading, scrollReadingTo } from './dom.mjs';

const paths = {
  book: 'M12 5C8 3 5 3 3 4v15c3-1 6-1 9 1m0-15c4-2 7-2 9-1v15c-3-1-6-1-9 1V5',
  lecture: 'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
  pencil: 'm5 15 10-10 4 4L9 19H5v-4m8-8 4 4',
  updown: 'm8 9 4-4 4 4m-8 6 4 4 4-4',
  left: 'm15 18-6-6 6-6', right: 'm9 6 6 6-6 6',
  forward: 'M5 12h14m-6-6 6 6-6 6',
  menu: 'M4 7h16M4 12h16M4 17h16',
  undo: 'M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
  contents: 'M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01',
  play: 'M8 5v14l11-7z',
  comment: 'M4 4h16v12H8l-4 4z',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  close: 'm6 6 12 12M18 6 6 18',
  check: 'm5 12 4 4L19 6',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  sun: 'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  moon: 'M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14',
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
let contentsSession = null;
// Outlines the headings the reading column currently shows, in every workspace, and marks the one being read.
// The Contents button shows or hides it: wide screens dock it beside the text and remember the choice;
// narrower screens open it over the page until a heading is chosen.
export function contentsOutline(reading) {
  contentsSession?.abort(); contentsSession = new AbortController();
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
      if (heading.matches('h2, h3')) focusHeading(heading); else heading.focus({ preventScroll: true });
      pinned = link; pinnedTop = scroller()?.scrollTop ?? 0; mark(link);
      if (!wide.matches) { overlay = false; apply(); }
    });
    links.push([link, heading]); return append(node('li'), link);
  }
  function refresh() {
    if (signal.aborted) return;
    // Headings, plus sections a renderer marks with data-contents-entry (such as exercise disclosures).
    const found = [...reading.querySelectorAll('h2, h3, [data-contents-entry]')].filter(heading => heading.getClientRects().length && heading.innerText.trim()
      && !heading.closest('.feedback, .citation-panel, .visually-hidden, [data-comment-ui], dialog'));
    if (found.length === headings.length && found.every((heading, index) => heading === headings[index])) return;
    headings = found; links = []; pinned = null;
    const list = node('ol'); let parent = null;
    for (const heading of found) {
      if (heading.tagName === 'H3' && parent) { parent.lastElementChild?.tagName === 'OL' || parent.append(node('ol')); parent.lastElementChild.append(entry(heading)); }
      else { const item = entry(heading); list.append(item); parent = heading.tagName === 'H2' ? item : null; }
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
  const name = value => ({ study: 'Study', exercises: 'Exercises', lectures: 'Lecture Notes' })[value];
  const label = node('span', 'workspace-name', name(context.workspace));
  const badge = node('span', 'workspace-badge'); badge.append(iconGlyph(({ study: 'book', exercises: 'pencil', lectures: 'lecture' })[context.workspace]));
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
    link.append(iconGlyph(({ study: 'book', exercises: 'pencil', lectures: 'lecture' })[value]), node('span', '', name(value)));
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

function outline(currentIndex) {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Course units');
  const folders = new Map();
  data.units.forEach((unit, index) => {
    let parent = nav;
    const ancestry = unit.path || [];
    ancestry.forEach((label, depth) => {
      const key = JSON.stringify(ancestry.slice(0, depth + 1));
      if (!folders.has(key)) {
        const group = node('details', 'unit-group');
        group.append(node('summary', '', label));
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
    if (!ancestry.length) link.append(node('span', '', unit.label));
    link.append(studyText('span', 'unit-title', unit.title));
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
  top.append(title, toggle, where);
  const body = node('div', 'sidebar-body'); body.id = 'outline-body';
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
