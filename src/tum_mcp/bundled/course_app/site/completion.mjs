import data from './data.mjs';
import { node, svgNode, button } from './dom.mjs';

// Entries a student marked as completed, by link, in every workspace's sidebar.
const storageKey = `course-app:${data.course.identity}:completed:v1`;
const completed = (() => {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch { return {}; }
})();
const save = () => { try { localStorage.setItem(storageKey, JSON.stringify(completed)); } catch { /* storage blocked: marks last for this visit */ } };
const target = link => link.getAttribute('href');
const isDone = link => completed[target(link)] === true;
let menu = null;

function paint(link) {
  const done = isDone(link);
  link.classList.toggle('completed', done);
  link.querySelector(':scope .done-mark')?.remove();
  if (!done) return;
  const mark = node('span', 'done-mark');
  const icon = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
  icon.append(svgNode('path', { d: 'M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm3.1 4.9-3.6 4a.75.75 0 0 1-1.1 0L4.9 8.8a.75.75 0 1 1 1.1-1l1 1.1 3-3.4a.75.75 0 0 1 1.1 1Z', 'fill-rule': 'evenodd' }));
  mark.append(icon, node('span', 'visually-hidden', ' (completed)'));
  (link.querySelector('.unit-title') || link).append(mark);
}

function close(restore = null) {
  menu?.remove(); menu = null;
  restore?.focus({ preventScroll: true });
}

export function enableCompletion(root) {
  const selector = 'a.unit-link:not(.revision-link)';
  const links = () => root.querySelectorAll(selector);
  links().forEach(paint);
  root.addEventListener('contextmenu', event => {
    const link = event.target.closest(selector);
    if (!link || !root.contains(link)) return;
    event.preventDefault(); open(link, event.clientX, event.clientY);
  });
  // The menu key and Shift+F10 do not raise a context menu event in every browser.
  root.addEventListener('keydown', event => {
    const link = event.target.closest?.(selector);
    if (!link || !(event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey))) return;
    event.preventDefault(); open(link, 0, 0);
  });
  function open(link, clientX, clientY) {
    close();
    const done = isDone(link);
    menu = node('div', 'context-menu'); menu.setAttribute('role', 'menu');
    const item = button(done ? 'Mark as not completed' : 'Mark as completed', () => {
      if (done) delete completed[target(link)]; else completed[target(link)] = true;
      save(); links().forEach(other => { if (target(other) === target(link)) paint(other); }); close(link);
    }, 'context-menu-item');
    item.setAttribute('role', 'menuitem');
    menu.append(item); document.body.append(menu);
    // A keyboard-opened menu has no pointer position, so it opens below the entry.
    const box = link.getBoundingClientRect();
    const x = clientX || box.left + 16, y = clientY || box.bottom;
    menu.style.left = `${Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8))}px`;
    item.focus();
    menu.addEventListener('keydown', key => { if (key.key === 'Escape' || key.key === 'Tab') { key.preventDefault(); close(link); } });
  }
}

document.addEventListener('pointerdown', event => { if (menu && !menu.contains(event.target)) close(); });
addEventListener('hashchange', () => close());
addEventListener('resize', () => close());
