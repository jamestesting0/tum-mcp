import data from './data.mjs';
import { node, button, append, sourcesNote, focusHeading } from './dom.mjs';

export function renderFlashcards(unit, ui, progress, persist) {
  const root = node('div');
  const meta = node('div', 'recall-meta');
  const count = node('p', 'small', `Card ${ui.card + 1} of ${unit.flashcards.length}`);
  meta.append(count);
  const card = unit.flashcards[ui.card];
  const key = `${unit.key}:${unit.revision}:${card.key}`;
  const surface = node('section', 'surface');
  const prompt = node('h2', 'recall-prompt', card.front);
  const answer = node('div', 'card-answer'); answer.hidden = !ui.revealed;
  answer.append(node('p', '', card.back), sourcesNote(card.sources, data.sources, data.course.synthetic));
  const status = node('p', 'small'); status.setAttribute('aria-live', 'polite');
  const again = button('Again', () => rate(false));
  const got = button('Got it', () => rate(true));
  again.setAttribute('aria-pressed', String(progress.cards[key] === false));
  got.setAttribute('aria-pressed', String(progress.cards[key] === true));
  const ratings = append(node('div', 'cluster card-actions'), again, got); ratings.hidden = !ui.revealed;
  const reveal = button(ui.revealed ? 'Hide answer' : 'Show answer', () => {
    ui.revealed = !ui.revealed; answer.hidden = !ui.revealed; ratings.hidden = !ui.revealed;
    reveal.textContent = ui.revealed ? 'Hide answer' : 'Show answer';
    reveal.setAttribute('aria-expanded', String(ui.revealed));
  }, 'primary');
  reveal.setAttribute('aria-expanded', String(ui.revealed));
  function rate(remembered) {
    progress.cards[key] = remembered; persist();
    again.setAttribute('aria-pressed', String(!remembered)); got.setAttribute('aria-pressed', String(remembered));
    status.textContent = remembered ? 'Remembered.' : 'Marked for review.';
  }
  surface.append(prompt, append(node('div', 'card-actions'), reveal), answer, ratings, status);
  const navigation = node('div', 'unit-footer');
  const prev = button('Previous card', () => move(-1)); prev.disabled = ui.card === 0;
  const next = button('Next card', () => move(1)); next.disabled = ui.card === unit.flashcards.length - 1;
  navigation.append(prev, next);
  function move(delta) {
    ui.card += delta; ui.revealed = false;
    root.replaceWith(renderFlashcards(unit, ui, progress, persist));
    focusHeading(document.querySelector('.recall-prompt'));
  }
  root.append(meta, surface, navigation);
  return root;
}

export function renderPractice(unit, ui, progress, persist) {
  const root = node('div');
  const question = unit.questions[ui.question];
  const key = `${unit.key}:${unit.revision}:${question.key}`;
  const state = ui.answers.get(question.key) || { selected: null, checked: false };
  ui.answers.set(question.key, state);
  const count = node('p', 'small', `Question ${ui.question + 1} of ${unit.questions.length} · ${question.level === 'recall' ? 'Recall' : question.level === 'apply' ? 'Application' : 'Reasoning'}`);
  const form = node('form', 'practice-question');
  const group = node('fieldset');
  group.append(node('legend', '', question.prompt));
  for (const option of question.options) {
    const label = node('label', 'option');
    const radio = node('input'); radio.type = 'radio'; radio.name = 'answer'; radio.value = option.key;
    radio.checked = state.selected === option.key; radio.disabled = state.checked;
    radio.addEventListener('change', () => { state.selected = option.key; check.disabled = false; });
    label.append(radio, node('span', '', option.text)); group.append(label);
  }
  const check = node('button', 'primary', state.checked ? 'Answer checked' : 'Check answer');
  check.type = 'submit'; check.disabled = state.checked || state.selected === null;
  form.append(group, append(node('div', 'card-actions'), check));
  const feedback = node('div'); feedback.setAttribute('aria-live', 'polite');
  function showFeedback() {
    const correct = state.selected === question.correct;
    const chosen = question.options.find(option => option.key === state.selected);
    const correctChoice = question.options.find(option => option.key === question.correct);
    const panel = node('section', `feedback${correct ? '' : ' incorrect'}`);
    panel.append(node('h3', '', correct ? 'Correct' : 'Not quite'), node('p', '', chosen.feedback));
    if (!correct) panel.append(node('p', '', `Correct answer: ${correctChoice.text}`));
    panel.append(node('p', '', question.explanation));
    const alternatives = node('details', 'source-note'); alternatives.append(node('summary', '', 'Check the other options'));
    alternatives.append(append(node('ul'), ...question.options.filter(option => option.key !== state.selected).map(option => node('li', '', `${option.text} — ${option.feedback}`))));
    panel.append(alternatives, sourcesNote(question.sources, data.sources, data.course.synthetic));
    panel.append(button('Try again', () => {
      state.selected = null; state.checked = false; delete progress.questions[key]; persist();
      root.replaceWith(renderPractice(unit, ui, progress, persist));
      const legend = document.querySelector('legend'); focusHeading(legend); legend.scrollIntoView({ block: 'nearest' });
    }, 'quiet'));
    feedback.replaceChildren(panel);
  }
  form.addEventListener('submit', event => {
    event.preventDefault(); if (state.selected === null || state.checked) return;
    state.checked = true; progress.questions[key] = state.selected === question.correct; persist();
    group.querySelectorAll('input').forEach(input => { input.disabled = true; });
    check.disabled = true; check.textContent = 'Answer checked'; showFeedback();
  });
  if (state.checked) showFeedback();
  const navigation = node('div', 'unit-footer');
  const prev = button('Previous question', () => move(-1)); prev.disabled = ui.question === 0;
  const next = button('Next question', () => move(1)); next.disabled = ui.question === unit.questions.length - 1;
  function move(delta) {
    ui.question += delta; root.replaceWith(renderPractice(unit, ui, progress, persist));
    const legend = document.querySelector('legend'); focusHeading(legend);
  }
  navigation.append(prev, next);
  root.append(count, form, feedback, navigation);
  return root;
}
