import data from './data.mjs';
import { node, button } from './dom.mjs';

const paths = {
  left: 'm15 18-6-6 6-6', right: 'm9 6 6 6-6 6',
  sidebar: 'M9 3v18 M4 3h16v18H4z',
  sun: 'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  moon: 'M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14',
};
export function iconButton(label, icon, handler) {
  const control = button('', handler, 'icon-button quiet');
  control.setAttribute('aria-label', label); control.title = label;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', paths[icon]); svg.append(path); control.append(svg);
  return control;
}

const expanded = new Map();
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
        const activePath = data.units[currentIndex].path || [];
        group.open = ancestry.slice(0, depth + 1).every((part, i) => part === activePath[i]) || expanded.get(key) === true;
        group.addEventListener('toggle', () => expanded.set(key, group.open));
        folders.set(key, children); parent.append(group);
      }
      parent = folders.get(key);
    });
    const link = node('a', 'unit-link'); link.href = `#${unit.key}/content`;
    if (index === currentIndex) link.setAttribute('aria-current', 'page');
    if (!ancestry.length) link.append(node('span', '', unit.label));
    link.append(node('span', 'unit-title', unit.title));
    const status = node('span', 'small'); status.dataset.studyProgress = unit.key;
    link.append(status); parent.append(link);
  });
  return nav;
}

export function renderSidebar(context) {
  const sidebar = node('aside', 'sidebar'); sidebar.id = 'course-outline';
  const top = node('div', 'sidebar-top');
  const title = node('p', 'course-title', data.course.title);
  const toggle = iconButton('Collapse course outline', 'sidebar', () => {
    context.collapsed = !context.collapsed; update();
  });
  toggle.setAttribute('aria-controls', 'outline-body');
  top.append(title, toggle);
  const body = node('div', 'sidebar-body'); body.id = 'outline-body';
  const semester = node('p', 'small', data.course.semester);
  const about = node('details', 'source-note');
  about.append(node('summary', '', 'About'), node('p', 'small', data.introduction));
  if (data.incompleteSources) about.append(node('p', 'small', 'Some course sources have not been checked.'));
  const footer = node('div', 'sidebar-footer cluster');
  footer.append(button('Reset progress', context.reset, 'quiet'));
  function themeControl() {
    const dark = document.documentElement.dataset.theme === 'dark';
    const label = dark ? 'Use light theme' : 'Use dark theme';
    return iconButton(label, dark ? 'sun' : 'moon', () => {
      context.theme(dark ? 'light' : 'dark');
      const replacement = themeControl(); theme.replaceWith(replacement); theme = replacement; theme.focus();
    });
  }
  let theme = themeControl(); footer.append(theme);
  body.append(semester, about, outline(context.currentIndex), footer);
  sidebar.append(top, body);
  function update() {
    document.documentElement.dataset.outline = context.collapsed ? 'collapsed' : 'expanded';
    body.hidden = context.collapsed;
    title.hidden = context.collapsed;
    toggle.setAttribute('aria-expanded', String(!context.collapsed));
    const label = context.collapsed ? 'Expand course outline' : 'Collapse course outline';
    toggle.setAttribute('aria-label', label); toggle.title = label;
  }
  update(); return sidebar;
}

export function bottomViews(unit, currentView, change) {
  const nav = node('nav', 'view-footer'); nav.setAttribute('aria-label', 'Study views');
  for (const view of ['content', 'flashcards', 'practice']) {
    const link = node('a', '', view[0].toUpperCase() + view.slice(1));
    link.href = `#${unit.key}/${view}`;
    if (view === currentView) link.setAttribute('aria-current', 'page');
    link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); change(view);
    });
    nav.append(link);
  }
  return nav;
}
