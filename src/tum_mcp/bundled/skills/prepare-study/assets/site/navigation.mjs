import data from './data.mjs';
import { node, studyText, button } from './dom.mjs';

const paths = {
  left: 'm15 18-6-6 6-6', right: 'm9 6 6 6-6 6',
  forward: 'M5 12h14m-6-6 6 6-6 6',
  menu: 'M4 7h16M4 12h16M4 17h16',
  reset: 'M3 10a9 9 0 1 1 2.5 8M3 4v6h6',
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
    const link = node('a', 'unit-link'); link.href = `#${unit.key}/content`;
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
  const title = node('a', 'course-title', data.course.title); title.href = '#home';
  if (context.location === 'home') title.setAttribute('aria-current', 'page');
  const where = node('p', 'outline-context', context.context); where.setAttribute('aria-hidden', 'true');
  const toggle = iconButton('Collapse course outline', 'left', () => {
    context.collapsed = !context.collapsed; update();
  });
  toggle.className = 'icon-button outline-toggle';
  toggle.setAttribute('aria-controls', 'outline-body');
  top.append(title, toggle, where);
  const body = node('div', 'sidebar-body'); body.id = 'outline-body';
  const semester = node('p', 'small', data.course.semester);
  const footer = node('div', 'sidebar-footer cluster');
  function themeControl() {
    const dark = document.documentElement.dataset.theme === 'dark';
    const label = dark ? 'Use light theme' : 'Use dark theme';
    return iconButton(label, dark ? 'sun' : 'moon', () => {
      context.theme(dark ? 'light' : 'dark');
      const replacement = themeControl(); theme.replaceWith(replacement); theme = replacement; theme.focus();
    });
  }
  let theme = themeControl(); footer.append(theme);
  const sections = node('nav'); sections.setAttribute('aria-label', 'Study sections');
  const revision = node('a', 'unit-link revision-link', 'Revision'); revision.href = '#revision?view=flashcards';
  if (context.location === 'revision') revision.setAttribute('aria-current', 'page');
  sections.append(revision);
  body.append(semester, outline(typeof context.location === 'number' ? context.location : -1), sections, footer);
  const boundary = node('div', 'outline-boundary'); boundary.setAttribute('aria-hidden', 'true');
  sidebar.append(boundary, top, body);
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
    body.hidden = context.collapsed;
    toggle.setAttribute('aria-expanded', String(!context.collapsed));
    const label = context.collapsed ? 'Expand course outline' : 'Collapse course outline';
    toggle.setAttribute('aria-label', label); toggle.title = label;
    const icon = narrow.matches ? (context.collapsed ? 'menu' : 'close') : (context.collapsed ? 'right' : 'left');
    toggle.querySelector('path').setAttribute('d', paths[icon]);
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
