import data from './data.mjs';
import { node, button, append, focusHeading } from './dom.mjs';
import { renderReading } from './reading.mjs';
import { renderPractice } from './learning.mjs';
import { renderFlashcards, flashcardShortcut } from './flashcards.mjs';
import { renderSidebar, bottomViews } from './navigation.mjs';

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
const states = new Map(), views = ['content', 'flashcards', 'practice'];
const navigationState = { collapsed: matchMedia('(max-width: 799px)').matches };
let currentIndex = 0, currentView = 'content', main, unitHeading, footer;
const tabButtons = new Map(), panels = new Map();
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
function stateFor(unit) {
  if (!states.has(unit.key)) states.set(unit.key, { card: 0, revealed: false, question: 0, answers: new Map() });
  return states.get(unit.key);
}
function readingStart() { window.scrollTo({ top: 0, behavior: 'instant' }); main.scrollTop = 0; }
function changeView(view, fromBottom = false) {
  currentView = view; history.replaceState(null, '', `#${data.units[currentIndex].key}/${view}`);
  renderPanel();
  if (fromBottom) { readingStart(); tabButtons.get(view).focus({ preventScroll: true }); }
}
function renderPanel() {
  const unit = data.units[currentIndex], ui = stateFor(unit);
  for (const [view, tab] of tabButtons) { tab.setAttribute('aria-selected', String(view === currentView)); tab.tabIndex = view === currentView ? 0 : -1; }
  for (const [view, element] of panels) element.hidden = view !== currentView;
  const panel = panels.get(currentView);
  switch (currentView) {
    case 'content': panel.replaceChildren(renderReading(unit)); break;
    case 'flashcards': panel.replaceChildren(renderFlashcards(unit, ui, progress, persist)); break;
    case 'practice': panel.replaceChildren(renderPractice(unit, ui, progress, persist)); break;
    default: throw new Error('Unknown study view.');
  }
  const replacement = bottomViews(unit, currentView, view => changeView(view, true));
  footer.replaceWith(replacement); footer = replacement;
}
function render() {
  const unit = data.units[currentIndex]; document.title = `${unit.title} · ${data.course.title}`;
  const shell = node('div', 'shell');
  navigationState.currentIndex = currentIndex;
  navigationState.reset = () => {
    if (!confirm('Reset practice answers and card ratings for this course?')) return;
    progress.cards = {}; progress.questions = {}; states.clear(); persist(); renderPanel();
  };
  navigationState.theme = value => {
    document.documentElement.dataset.theme = value;
    try { localStorage.setItem('study-space:theme', JSON.stringify(value)); } catch { memoryOnly = true; persist(); }
  };
  const sidebar = renderSidebar(navigationState);
  main = node('main', 'main'); main.id = 'content'; main.tabIndex = -1;
  const reading = node('div', 'reading'); reading.append(persistenceNote);
  const heading = node('div', 'unit-header'); unitHeading = node('h1', '', unit.title);
  const location = [...(unit.path || []), unit.label].join(' · ');
  heading.append(node('p', 'eyebrow', `${location} · ${unit.minutes} min`), unitHeading, node('p', 'unit-summary', unit.summary));
  const objectives = node('details'); objectives.append(node('summary', 'small', `What you will learn · ${unit.objectives.length} objectives`));
  objectives.append(append(node('ul', 'objectives'), ...unit.objectives.map(item => node('li', '', item.text)))); heading.append(objectives);
  const tabs = node('div', 'tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Study view'); tabButtons.clear();
  for (const view of views) {
    const label = view === 'content' ? 'Content' : view === 'flashcards' ? `Flashcards · ${unit.flashcards.length}` : `Practice · ${unit.questions.length}`;
    const tab = button(label, () => changeView(view)); tab.id = `tab-${view}`;
    tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', `panel-${view}`);
    tab.addEventListener('keydown', event => {
      const index = views.indexOf(view);
      const next = event.key === 'ArrowRight' ? (index + 1) % views.length : event.key === 'ArrowLeft' ? (index + views.length - 1) % views.length : event.key === 'Home' ? 0 : event.key === 'End' ? views.length - 1 : null;
      if (next === null) return; event.preventDefault(); changeView(views[next]); tabButtons.get(currentView).focus();
    });
    tabButtons.set(view, tab); tabs.append(tab);
  }
  panels.clear();
  for (const view of views) {
    const element = node('div'); element.id = `panel-${view}`; element.setAttribute('role', 'tabpanel');
    element.setAttribute('aria-labelledby', `tab-${view}`); element.tabIndex = 0; panels.set(view, element);
  }
  footer = node('nav'); reading.append(heading, tabs, ...panels.values(), footer);
  main.append(reading); shell.append(sidebar, main);
  document.querySelector('#app').replaceChildren(shell); renderPanel(); persist();
}
function route(initial = false) {
  const [key, view] = location.hash.slice(1).split('/'); const index = data.units.findIndex(unit => unit.key === key);
  currentIndex = index < 0 ? 0 : index; currentView = views.includes(view) ? view : 'content'; render();
  if (!initial) { readingStart(); focusHeading(unitHeading); }
}
document.querySelector('.skip').addEventListener('click', event => { event.preventDefault(); main.focus(); });
addEventListener('hashchange', () => route());
addEventListener('keydown', event => { if (currentView === 'flashcards') flashcardShortcut(event); });
route(true);
