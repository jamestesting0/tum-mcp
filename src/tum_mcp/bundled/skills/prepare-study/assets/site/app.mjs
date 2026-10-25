import data from './data.mjs';
import { node, button, append, focusHeading } from './dom.mjs';
import { renderReading } from './reading.mjs';
import { renderFlashcards, renderPractice } from './learning.mjs';

const storageKey = `study-space:${data.course.identity}:progress:v1`;
let memoryOnly = false;
function readStored(key, fallback) {
  try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; }
  catch { memoryOnly = true; return fallback; }
}
const saved = readStored(storageKey, {});
function validRatings(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value).filter(([key, rating]) => key.length < 300 && typeof rating === 'boolean')) : {};
}
const progress = { cards: validRatings(saved?.cards), questions: validRatings(saved?.questions) };
const preferredTheme = readStored('study-space:theme', null);
document.documentElement.dataset.theme = ['light', 'dark'].includes(preferredTheme) ? preferredTheme : matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
const states = new Map();
const views = ['content', 'flashcards', 'practice'];
let currentIndex = 0, currentView = 'content';
let panel, tabs, main, unitHeading;
const tabButtons = new Map();
const panels = new Map();
const persistenceNote = node('p', 'notice'); persistenceNote.setAttribute('role', 'status');
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(progress)); }
  catch { memoryOnly = true; }
  persistenceNote.hidden = !memoryOnly;
  persistenceNote.textContent = memoryOnly ? 'Progress cannot be saved. It stays in memory for this session.' : '';
  for (const label of document.querySelectorAll('[data-study-progress]')) {
    const unit = data.units.find(item => item.key === label.dataset.studyProgress);
    const correct = unit.questions.filter(item => progress.questions[`${unit.key}:${unit.revision}:${item.key}`] === true).length;
    label.hidden = !unit.questions.some(item => typeof progress.questions[`${unit.key}:${unit.revision}:${item.key}`] === 'boolean');
    label.textContent = `Practice: ${correct}/${unit.questions.length} correct`;
  }
}
function go(index, view = currentView) { location.hash = `${data.units[index].key}/${view}`; }
function outline() {
  const list = node('nav', 'unit-list'); list.setAttribute('aria-label', 'Course units');
  data.units.forEach((unit, index) => {
    const link = node('a', 'unit-link'); link.href = `#${unit.key}/content`;
    if (index === currentIndex) link.setAttribute('aria-current', 'page');
    const status = node('span', 'small'); status.dataset.studyProgress = unit.key;
    link.append(node('span', '', unit.label), document.createTextNode(unit.title), status); list.append(link);
  });
  return list;
}
function stateFor(unit) {
  if (!states.has(unit.key)) states.set(unit.key, { card: 0, revealed: false, question: 0, answers: new Map() });
  return states.get(unit.key);
}
function renderPanel() {
  const unit = data.units[currentIndex], ui = stateFor(unit);
  for (const [view, tab] of tabButtons) { tab.setAttribute('aria-selected', String(view === currentView)); tab.tabIndex = view === currentView ? 0 : -1; }
  for (const [view, element] of panels) element.hidden = view !== currentView;
  panel = panels.get(currentView);
  for (const [view, tab] of tabButtons) tab.setAttribute('aria-controls', view === currentView ? panel.id : `panel-${view}`);
  switch (currentView) {
    case 'content': panel.replaceChildren(renderReading(unit)); break;
    case 'flashcards': panel.replaceChildren(renderFlashcards(unit, ui, progress, persist)); break;
    case 'practice': panel.replaceChildren(renderPractice(unit, ui, progress, persist)); break;
    default: throw new Error('Unknown study view.');
  }
}
function render() {
  const unit = data.units[currentIndex];
  document.title = `${unit.title} · ${data.course.title}`;
  const shell = node('div', 'shell');
  const sidebar = node('aside', 'sidebar');
  const course = node('div'); course.append(node('p', 'course-title', data.course.title), node('p', 'small', data.course.semester));
  const about = node('details', 'source-note'); about.append(node('summary', '', 'About this course'), node('p', 'small', data.introduction)); course.append(about);
  if (data.incompleteSources) about.append(node('p', 'small', 'Selected material is included. Some course sources have not been checked.'));
  const units = node('div'); units.append(node('p', 'eyebrow', data.organization), outline());
  const footer = node('details', 'sidebar-footer source-note'); footer.append(node('summary', '', 'Study settings'));
  const reset = button('Reset course progress', () => {
    if (!confirm('Reset practice answers and card ratings for this course?')) return;
    progress.cards = {}; progress.questions = {}; states.clear(); persist(); renderPanel();
  }, 'quiet');
  footer.append(reset);
  sidebar.append(course, units, footer);
  main = node('main', 'main'); main.id = 'content'; main.tabIndex = -1;
  const toolbar = node('header', 'toolbar');
  const focus = button(document.documentElement.dataset.focus === 'true' ? 'Exit focus' : 'Focus mode', () => {
    const active = document.documentElement.dataset.focus !== 'true'; document.documentElement.dataset.focus = String(active);
    focus.textContent = active ? 'Exit focus' : 'Focus mode'; focus.setAttribute('aria-pressed', String(active));
  }, 'quiet');
  focus.setAttribute('aria-pressed', String(document.documentElement.dataset.focus === 'true'));
  const theme = button(document.documentElement.dataset.theme === 'dark' ? 'Light theme' : 'Dark theme', () => {
    const value = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = value; theme.textContent = value === 'dark' ? 'Light theme' : 'Dark theme';
    try { localStorage.setItem('study-space:theme', JSON.stringify(value)); } catch { memoryOnly = true; persist(); }
  }, 'quiet');
  toolbar.append(focus, theme);
  const mobile = node('details', 'mobile-course'); mobile.append(node('summary', '', `${data.course.title} · Course outline`), outline());
  const reading = node('div', 'reading');
  reading.append(persistenceNote);
  const heading = node('div', 'unit-header');
  unitHeading = node('h1', '', unit.title);
  heading.append(node('p', 'eyebrow', `${unit.label} · About ${unit.minutes} min`), unitHeading, node('p', 'unit-summary', unit.summary));
  const objectives = node('details'); objectives.append(node('summary', 'small', `What you will learn · ${unit.objectives.length} objectives`));
  objectives.append(append(node('ul', 'objectives'), ...unit.objectives.map(item => node('li', '', item.text)))); heading.append(objectives);
  tabs = node('div', 'tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Study view'); tabButtons.clear();
  for (const view of views) {
    const label = view === 'content' ? 'Content' : view === 'flashcards' ? `Flashcards · ${unit.flashcards.length}` : `Practice · ${unit.questions.length}`;
    const tab = button(label, () => { currentView = view; history.replaceState(null, '', `#${unit.key}/${view}`); renderPanel(); });
    tab.id = `tab-${view}`; tab.setAttribute('role', 'tab');
    tab.addEventListener('keydown', event => {
      const index = views.indexOf(view);
      const next = event.key === 'ArrowRight' ? (index + 1) % views.length : event.key === 'ArrowLeft' ? (index + views.length - 1) % views.length : event.key === 'Home' ? 0 : event.key === 'End' ? views.length - 1 : null;
      if (next === null) return; event.preventDefault(); currentView = views[next];
      history.replaceState(null, '', `#${unit.key}/${currentView}`); renderPanel(); tabButtons.get(currentView).focus();
    });
    tabButtons.set(view, tab); tabs.append(tab);
  }
  panels.clear();
  for (const view of views) {
    const element = node('div'); element.id = `panel-${view}`; element.setAttribute('role', 'tabpanel'); element.setAttribute('aria-labelledby', `tab-${view}`); element.tabIndex = 0; panels.set(view, element);
  }
  const navigation = node('footer', 'unit-footer');
  const prev = button('Previous unit', () => go(currentIndex - 1, 'content')); prev.disabled = currentIndex === 0;
  const next = button('Next unit', () => go(currentIndex + 1, 'content')); next.disabled = currentIndex === data.units.length - 1;
  navigation.append(prev, node('span', 'small', `${currentIndex + 1} / ${data.units.length}`), next);
  reading.append(heading, tabs, ...panels.values(), navigation); main.append(toolbar, mobile, reading); shell.append(sidebar, main);
  document.querySelector('#app').replaceChildren(shell); renderPanel(); persist();
}
function route(initial = false) {
  const [key, view] = location.hash.slice(1).split('/');
  const index = data.units.findIndex(unit => unit.key === key);
  currentIndex = index < 0 ? 0 : index; currentView = views.includes(view) ? view : 'content';
  render();
  if (!initial) {
    window.scrollTo({ top: 0, behavior: 'instant' }); main.scrollTop = 0;
    focusHeading(unitHeading);
  }
}
document.querySelector('.skip').addEventListener('click', event => { event.preventDefault(); main.focus(); });
addEventListener('hashchange', () => route());
addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.documentElement.dataset.focus === 'true') {
    document.documentElement.dataset.focus = 'false';
    const control = document.querySelector('.toolbar button'); control.textContent = 'Focus mode'; control.setAttribute('aria-pressed', 'false'); control.focus();
  }
});
route(true);
