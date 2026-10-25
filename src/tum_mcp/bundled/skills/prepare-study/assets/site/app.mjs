import data from './data.mjs';
import { node, studyText, button, append, focusHeading } from './dom.mjs';
import { renderCommentedView, stopComments } from './comments.mjs';
import { renderReading } from './reading.mjs';
import { renderPractice } from './learning.mjs';
import { renderFlashcards, flashcardShortcut } from './flashcards.mjs';
import { renderSidebar, nextStep, iconButton } from './navigation.mjs';
import { revisionDeck, topicPicker, itemKey } from './revision.mjs';

const storageKey = `study-space:${data.course.identity}:progress:v1`;
let memoryOnly = false;
function readStored(key, fallback) {
  try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; }
  catch { memoryOnly = true; return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { memoryOnly = true; }
}
const saved = readStored(storageKey, {});
function validRatings(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value).filter(([key, rating]) => key.length < 300 && typeof rating === 'boolean')) : {};
}
const progress = { cards: validRatings(saved?.cards), questions: validRatings(saved?.questions) };
const preferredTheme = readStored('study-space:theme', null);
document.documentElement.dataset.theme = ['light', 'dark'].includes(preferredTheme) ? preferredTheme : matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
const states = new Map(), answers = new Map(), views = ['content', 'flashcards', 'practice'];
const selectionKey = `${storageKey}:revision`, lastKey = `${storageKey}:last`;
const storedSelection = readStored(selectionKey, []);
const selectedTopics = new Set(Array.isArray(storedSelection) ? storedSelection.filter(key => data.units.some(unit => unit.key === key)) : []);
const narrow = matchMedia('(max-width: 799px)');
const navigationState = { collapsed: narrow.matches };
let currentIndex = 0, currentView = 'content', revising = false, home = false, reviewing = false;
let main, unitHeading, step, headerDetails = [], syncMode = () => {};
const tabButtons = new Map(), panels = new Map();
const persistenceNote = node('p', 'notice'); persistenceNote.setAttribute('role', 'status');
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function unitProgress(unit) {
  const result = (items, kind) => items.map(item => progress[kind][itemKey(unit, item)]);
  const questions = result(unit.questions, 'questions'), cards = result(unit.flashcards, 'cards');
  return {
    total: questions.length, answered: questions.filter(value => typeof value === 'boolean').length,
    correct: questions.filter(value => value === true).length,
    cards: cards.length, rated: cards.filter(value => typeof value === 'boolean').length,
    known: cards.filter(value => value === true).length,
  };
}
function practiceLabel(result) {
  return result.answered === result.total ? `${result.correct}/${result.total} correct` : `${result.answered}/${result.total} answered`;
}
// Review mode pools only items the student marked Again or answered incorrectly.
function needsReview(kind, key) { return progress[kind === 'flashcards' ? 'cards' : 'questions'][key] === false; }
function reviewCount(units) {
  return units.reduce((sum, unit) => sum + unit.flashcards.filter(item => needsReview('flashcards', itemKey(unit, item))).length
    + unit.questions.filter(item => needsReview('questions', itemKey(unit, item))).length, 0);
}
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(progress)); }
  catch { memoryOnly = true; }
  persistenceNote.hidden = !memoryOnly;
  persistenceNote.textContent = memoryOnly ? 'Progress cannot be saved. It stays in memory for this session.' : '';
  for (const label of document.querySelectorAll('[data-study-progress]')) {
    const result = unitProgress(data.units.find(item => item.key === label.dataset.studyProgress));
    label.hidden = !result.answered;
    label.textContent = practiceLabel(result);
  }
  syncMode();
}
function stateFor(unit) {
  const key = revising ? '$revision' : unit.key;
  if (!states.has(key)) states.set(key, { card: 0, revealed: false, question: 0, answers });
  return states.get(key);
}
function activeUnit() { return revising ? revisionDeck(selectedTopics, reviewing ? needsReview : undefined) : data.units[currentIndex]; }
function activeViews() { return revising ? views.slice(1) : views; }
function viewHash(view) { return revising ? `#revision?view=${view}${reviewing ? '&mode=review' : ''}` : `#${data.units[currentIndex].key}/${view}`; }
function remember() { if (!home) store(lastKey, revising ? 'revision' : `${data.units[currentIndex].key}/${currentView}`); }
function readingStart() { window.scrollTo({ top: 0, behavior: 'instant' }); main.scrollTop = 0; }
function changeView(view, fromBottom = false) {
  currentView = view; history.replaceState(null, '', viewHash(view)); remember();
  renderPanel();
  if (fromBottom) { readingStart(); tabButtons.get(view).focus({ preventScroll: true }); }
}
// A review pass starts unanswered; saved results stay until the student checks again.
function clearReviewAnswers() {
  for (const unit of data.units) for (const item of unit.questions) {
    const key = itemKey(unit, item);
    if (needsReview('questions', key)) answers.delete(key);
  }
}
function stepTarget(unit) {
  if (revising) {
    return currentView === 'flashcards' && unit.questions.length
      ? { href: viewHash('practice'), title: 'Practice', detail: plural(unit.questions.length, 'question'), activate: () => changeView('practice', true) } : null;
  }
  if (currentView === 'content') return { href: viewHash('flashcards'), title: 'Flashcards', detail: plural(unit.flashcards.length, 'card'), activate: () => changeView('flashcards', true) };
  if (currentView === 'flashcards') return { href: viewHash('practice'), title: 'Practice', detail: plural(unit.questions.length, 'question'), activate: () => changeView('practice', true) };
  const following = data.units[currentIndex + 1];
  return following ? { href: `#${following.key}/content`, title: following.title, detail: `${following.minutes} min` }
    : { href: '#revision?view=flashcards', title: 'Revision', detail: 'Cards and questions across topics' };
}
function emptyMessage() {
  if (!selectedTopics.size) return 'Select topics to start revising.';
  return currentView === 'flashcards' ? 'No cards marked Again in these topics.' : 'No incorrect answers in these topics.';
}
function renderPanel() {
  stopComments();
  const unit = activeUnit(), ui = stateFor(unit);
  ui.card = Math.min(ui.card, Math.max(0, unit.flashcards.length - 1));
  ui.question = Math.min(ui.question, Math.max(0, unit.questions.length - 1));
  for (const [view, tab] of tabButtons) {
    tab.textContent = view === 'content' ? 'Content' : view === 'flashcards' ? `Flashcards · ${unit.flashcards.length}` : `Practice · ${unit.questions.length}`;
    tab.setAttribute('aria-selected', String(view === currentView)); tab.tabIndex = view === currentView ? 0 : -1;
  }
  for (const element of headerDetails) element.hidden = currentView !== 'content';
  for (const [view, element] of panels) element.hidden = view !== currentView;
  const panel = panels.get(currentView);
  if (revising && !unit[currentView === 'flashcards' ? 'flashcards' : 'questions'].length) {
    panel.replaceChildren(node('p', 'empty-state small', emptyMessage()));
  } else {
    const view = currentView;
    function activity() {
      switch (view) {
        case 'content': return renderReading(unit);
        case 'flashcards': return renderFlashcards(unit, ui, progress, persist);
        case 'practice': return renderPractice(unit, ui, progress, persist);
        default: throw new Error('Unknown study view.');
      }
    }
    const comments = renderCommentedView(unit, view, activity(), anchor => {
      const items = unit[view === 'flashcards' ? 'flashcards' : 'questions'];
      const index = items.findIndex(item => item.key === anchor.item_key && (item.origin?.key || unit.key) === anchor.unit_key);
      if (index < 0) return null;
      if (view === 'flashcards') { ui.card = index; ui.revealed = anchor.field === 'back'; } else ui.question = index;
      return activity();
    });
    panel.replaceChildren(comments.root);
  }
  const target = revising && !selectedTopics.size ? null : stepTarget(unit);
  const replacement = target ? nextStep(target) : node('div');
  step.replaceWith(replacement); step = replacement;
  syncMode();
}
function confirmReset(trigger) {
  const dialog = node('dialog', 'confirm-dialog');
  const title = node('h2', '', 'Reset progress?'); title.id = 'reset-title'; dialog.setAttribute('aria-labelledby', title.id);
  const cancel = button('Cancel', () => dialog.close(), 'quiet');
  const reset = button('Reset', () => {
    progress.cards = {}; progress.questions = {}; states.clear(); answers.clear(); persist();
    dialog.close(); render(); document.querySelector('.home-reset')?.focus();
  }, 'primary');
  dialog.append(title, node('p', '', 'This clears practice answers and card ratings for this course. Comments and topic choices stay.'),
    append(node('div', 'cluster comment-actions'), cancel, reset));
  dialog.addEventListener('close', () => { dialog.remove(); if (trigger.isConnected) trigger.focus(); });
  document.body.append(dialog); dialog.showModal(); cancel.focus();
}
function resumeTarget() {
  const last = readStored(lastKey, '');
  if (last === 'revision') return { href: '#revision?view=flashcards', label: 'Continue: Revision' };
  const [key, view] = typeof last === 'string' ? last.split('/') : [];
  const unit = data.units.find(item => item.key === key);
  return unit ? { href: `#${unit.key}/${views.includes(view) ? view : 'content'}`, label: `Continue: ${unit.title}` }
    : { href: `#${data.units[0].key}/content`, label: `Start: ${data.units[0].title}` };
}
function renderHome() {
  const header = node('div', 'unit-header');
  unitHeading = node('h1', '', data.course.title);
  header.append(node('p', 'eyebrow', data.course.semester), unitHeading, studyText('p', 'unit-summary', data.introduction));
  const resume = resumeTarget(), actions = node('div', 'cluster home-actions');
  const go = node('a', 'button primary', resume.label); go.href = resume.href; actions.append(go);
  const due = reviewCount(data.units);
  if (due) { const review = node('a', 'button', `Review ${plural(due, 'item')}`); review.href = '#revision?view=flashcards&mode=review'; actions.append(review); }
  header.append(actions);
  const topics = node('section', 'home-topics'); topics.setAttribute('aria-labelledby', 'home-topics-title');
  const title = node('h2', '', 'Topics'); title.id = 'home-topics-title'; topics.append(title);
  let list, group;
  for (const unit of data.units) {
    const path = (unit.path || []).join(' · ');
    if (!list || path !== group) {
      group = path;
      if (path) topics.append(node('h3', 'topic-group', path));
      list = node('ul', 'topic-list'); topics.append(list);
    }
    const result = unitProgress(unit), status = [];
    if (result.answered) status.push(`Practice ${practiceLabel(result)}`);
    if (result.rated) status.push(`Cards ${result.known}/${result.cards} known`);
    const row = node('li', 'topic-row'), link = node('a');
    link.href = `#${unit.key}/content`;
    link.append(studyText('span', 'topic-title', unit.title), node('span', 'small', path ? `${unit.minutes} min` : `${unit.label} · ${unit.minutes} min`));
    row.append(link, node('span', 'small topic-status', status.join(' · ') || 'Not started'));
    list.append(row);
  }
  const reset = iconButton('Reset progress', 'reset', () => confirmReset(reset)); reset.classList.add('home-reset');
  return [header, topics, append(node('div', 'home-footer'), reset)];
}
function modePicker() {
  const group = node('fieldset', 'mode-options');
  group.append(node('legend', 'visually-hidden', 'Items to study'));
  const review = node('span');
  for (const [value, label] of [['all', 'All items'], ['review', review]]) {
    const option = node('label'), input = node('input');
    input.type = 'radio'; input.name = 'revision-mode'; input.value = value; input.checked = (value === 'review') === reviewing;
    input.addEventListener('change', () => {
      reviewing = value === 'review'; history.replaceState(null, '', viewHash(currentView));
      states.delete('$revision'); if (reviewing) clearReviewAnswers(); renderPanel();
    });
    option.append(input, typeof label === 'string' ? node('span', '', label) : label); group.append(option);
  }
  syncMode = () => { review.textContent = `To review · ${reviewCount(data.units.filter(unit => selectedTopics.has(unit.key)))}`; };
  return group;
}
function render() {
  stopComments(); syncMode = () => {};
  const shell = node('div', 'shell');
  navigationState.location = home ? 'home' : revising ? 'revision' : currentIndex;
  navigationState.context = home ? data.course.title : revising ? 'Revision' : data.units[currentIndex].title;
  navigationState.theme = value => {
    document.documentElement.dataset.theme = value;
    try { localStorage.setItem('study-space:theme', JSON.stringify(value)); } catch { memoryOnly = true; persist(); }
  };
  const sidebar = renderSidebar(navigationState);
  main = node('main', 'main'); main.id = 'content'; main.tabIndex = -1;
  const reading = node('div', 'reading'); reading.append(persistenceNote);
  tabButtons.clear(); panels.clear(); headerDetails = [];
  if (home) {
    document.title = data.course.title;
    reading.append(...renderHome());
  } else {
    const unit = activeUnit(); document.title = `${unit.title} · ${data.course.title}`;
    const heading = node('div', 'unit-header'); unitHeading = studyText('h1', '', unit.title);
    if (revising) {
      heading.append(unitHeading, topicPicker(selectedTopics, () => {
        states.delete('$revision');
        try { localStorage.setItem(selectionKey, JSON.stringify([...selectedTopics])); } catch { memoryOnly = true; }
        renderPanel(); persist();
      }), modePicker());
    } else {
      const ancestry = unit.path || [];
      const breadcrumb = [...ancestry, ...(ancestry.includes(unit.label) ? [] : [unit.label])].join(' · ');
      const summary = studyText('p', 'unit-summary', unit.summary), objectives = node('div', 'objectives');
      objectives.append(node('p', 'small objectives-label', 'Objectives'), append(node('ul'), ...unit.objectives.map(item => studyText('li', '', item.text))));
      heading.append(node('p', 'eyebrow', `${breadcrumb} · ${unit.minutes} min`), unitHeading, summary, objectives);
      headerDetails = [summary, objectives];
    }
    const tabs = node('div', 'tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Study view');
    const available = activeViews();
    for (const view of available) {
      const tab = button('', () => changeView(view)); tab.id = `tab-${view}`;
      tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', `panel-${view}`);
      tab.addEventListener('keydown', event => {
        const index = available.indexOf(view);
        const next = event.key === 'ArrowRight' ? (index + 1) % available.length : event.key === 'ArrowLeft' ? (index + available.length - 1) % available.length : event.key === 'Home' ? 0 : event.key === 'End' ? available.length - 1 : null;
        if (next === null) return; event.preventDefault(); changeView(available[next]); tabButtons.get(currentView).focus();
      });
      tabButtons.set(view, tab); tabs.append(tab);
    }
    for (const view of available) {
      const element = node('div'); element.id = `panel-${view}`; element.setAttribute('role', 'tabpanel');
      element.setAttribute('aria-labelledby', `tab-${view}`); element.tabIndex = 0; panels.set(view, element);
    }
    const viewBar = node('div', 'view-bar'); viewBar.append(tabs);
    step = node('div'); reading.append(heading, viewBar, ...panels.values(), step);
  }
  main.append(reading); shell.append(sidebar, main);
  document.querySelector('#app').replaceChildren(shell);
  if (!home) renderPanel();
  persist();
}
function route(initial = false) {
  const hash = location.hash.slice(1);
  revising = hash === 'revision' || hash.startsWith('revision?');
  const params = new URLSearchParams(revising ? hash.split('?')[1] || '' : '');
  const [key, view] = revising ? ['', params.get('view')] : hash.split('/');
  const index = data.units.findIndex(unit => unit.key === key);
  home = !revising && index < 0; reviewing = revising && params.get('mode') === 'review';
  currentIndex = Math.max(index, 0);
  currentView = home ? 'content' : activeViews().includes(view) ? view : activeViews()[0];
  if (reviewing) { states.delete('$revision'); clearReviewAnswers(); }
  if (narrow.matches) navigationState.collapsed = true;
  remember(); render();
  if (!initial) { readingStart(); focusHeading(unitHeading); }
}
document.querySelector('.skip').addEventListener('click', event => { event.preventDefault(); main.focus(); });
addEventListener('hashchange', () => route());
addEventListener('keydown', event => { if (currentView === 'flashcards') flashcardShortcut(event); });
route(true);
