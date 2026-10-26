import data from './data.mjs';
import { node, studyText, button, append, sourcesNote, focusHeading } from './dom.mjs';
import { iconButton, iconGlyph } from './navigation.mjs';
import { itemKey } from './revision.mjs';
import { annotate } from './anchors.mjs';
import { reviewQuestion } from './question-review.mjs';

export function renderPractice(unit, ui, progress, persist) {
  const root = node('div');
  const question = unit.questions[ui.question];
  const key = itemKey(unit, question);
  const last = ui.question === unit.questions.length - 1;
  const state = ui.answers.get(key) || { selected: null, checked: false };
  ui.answers.set(key, state);
  const count = node('p', 'small', `${ui.question + 1}/${unit.questions.length} · ${question.level === 'recall' ? 'Recall' : question.level === 'apply' ? 'Application' : 'Reasoning'}`);
  const form = node('form', 'practice-question');
  const group = node('fieldset');
  group.append(annotate(studyText('legend', '', question.prompt), unit, question, 'practice', 'prompt'));
  const labels = new Map();
  for (const option of question.options) {
    const label = node('label', 'option');
    const radio = node('input'); radio.type = 'radio'; radio.name = 'answer'; radio.value = option.key;
    radio.checked = state.selected === option.key; radio.disabled = state.checked;
    radio.addEventListener('change', () => { state.selected = option.key; check.disabled = false; });
    const body = node('span', 'option-body');
    body.append(annotate(studyText('span', '', option.text), unit, question, 'practice', `option:${option.key}`));
    label.append(radio, body);
    label.addEventListener('click', event => {
      const selection = getSelection();
      if (event.target !== radio && selection && !selection.isCollapsed && label.contains(selection.anchorNode) && label.contains(selection.focusNode)) event.preventDefault();
    });
    labels.set(option.key, label); group.append(label);
  }
  const check = node('button', 'primary', 'Check answer');
  check.type = 'submit'; check.disabled = state.selected === null;
  const actions = append(node('div', 'card-actions'), check); actions.hidden = state.checked;
  form.append(group, actions);
  const feedback = node('div'); feedback.setAttribute('aria-live', 'polite');
  function mark() {
    form.dataset.checked = 'true';
    for (const [optionKey, label] of labels) {
      const correct = optionKey === question.correct, chosen = optionKey === state.selected;
      label.dataset.state = correct ? 'correct' : chosen ? 'incorrect' : 'other';
      if (!correct && !chosen) continue;
      const tag = node('span', 'option-state');
      tag.append(iconGlyph(correct ? 'check' : 'close'), chosen ? 'Your answer' : 'Correct answer');
      label.querySelector('.option-body').append(tag);
    }
  }
  function summary() {
    const results = unit.questions.map((item, index) => ({ index, item, value: progress.questions[itemKey(unit, item)] }));
    const correct = results.filter(result => result.value === true).length;
    const missing = results.filter(result => typeof result.value !== 'boolean').length;
    const box = node('div', 'practice-summary');
    box.append(node('h3', '', 'End of set'), node('p', '', `${correct} of ${results.length} correct${missing ? ` · ${missing} not answered` : ''}`));
    const open = results.filter(result => result.value !== true);
    if (open.length) {
      const list = node('ul', 'summary-list');
      for (const result of open) {
        const item = node('li');
        const jump = button('', () => reviewQuestion({
          unit, question: result.item, answer: ui.answers.get(itemKey(unit, result.item)),
          answered: typeof result.value === 'boolean', trigger: jump,
          position: `${result.index + 1}/${results.length}`,
        }), 'summary-item');
        const copy = node('span', 'summary-copy');
        copy.append(studyText('span', 'summary-prompt', `${result.index + 1}. ${result.item.prompt}`), node('span', 'small', result.value === false ? 'Incorrect' : 'Not answered'));
        const action = node('span', 'summary-action'); action.append('Review', iconGlyph('right'));
        jump.append(copy, action);
        item.append(jump); list.append(item);
      }
      box.append(list);
    }
    return box;
  }
  function showFeedback() {
    mark();
    const correct = state.selected === question.correct;
    const chosen = question.options.find(option => option.key === state.selected);
    const correctChoice = question.options.find(option => option.key === question.correct);
    const panel = node('section', `feedback${correct ? '' : ' incorrect'}`);
    const title = node('h3', '', correct ? 'Correct' : 'Not quite'); title.tabIndex = -1;
    panel.append(title, annotate(studyText('p', '', chosen.feedback), unit, question, 'practice', `feedback:${chosen.key}`));
    if (!correct) {
      const answer = node('p', '', 'Correct answer: '); answer.append(annotate(studyText('span', '', correctChoice.text), unit, question, 'practice', 'correct')); panel.append(answer);
    }
    panel.append(annotate(studyText('p', '', question.explanation), unit, question, 'practice', 'explanation'));
    const alternatives = node('details', 'source-note other-options'); alternatives.append(node('summary', '', 'Other options'));
    alternatives.append(append(node('ul'), ...question.options.filter(option => option.key !== state.selected).map(option => {
      const item = node('li'); item.append(annotate(studyText('span', '', option.text), unit, question, 'practice', `option:${option.key}`), document.createTextNode(' — '), annotate(studyText('span', '', option.feedback), unit, question, 'practice', `feedback:${option.key}`)); return item;
    })));
    panel.append(alternatives, sourcesNote(question.sources, data.sources, data.course.synthetic));
    const next = node('div', 'cluster feedback-actions');
    next.append(button('Try again', () => {
      state.selected = null; state.checked = false; delete progress.questions[key]; persist();
      replaceQuestion();
    }, 'secondary'));
    if (!last) next.append(button('Continue', () => go(ui.question + 1), 'primary'));
    panel.append(next);
    if (last) panel.append(summary());
    feedback.replaceChildren(panel);
    return title;
  }
  form.addEventListener('submit', event => {
    event.preventDefault(); if (state.selected === null || state.checked) return;
    state.checked = true; progress.questions[key] = state.selected === question.correct; persist();
    group.querySelectorAll('input').forEach(input => { input.disabled = true; });
    actions.hidden = true; showFeedback().focus();
    root.dispatchEvent(new CustomEvent('study-activity-change', { bubbles: true }));
  });
  if (state.checked) showFeedback();
  const meta = node('div', 'recall-meta practice-meta');
  const position = node('div'); position.append(count);
  if (question.origin) position.append(node('p', 'small', question.origin.title));
  const navigation = node('div', 'cluster practice-navigation');
  navigation.setAttribute('role', 'group'); navigation.setAttribute('aria-label', 'Question navigation');
  const prev = iconButton('Previous question', 'left', () => go(ui.question - 1)); prev.disabled = ui.question === 0;
  const next = iconButton('Next question', 'right', () => go(ui.question + 1)); next.disabled = last;
  function go(index) {
    if (index < 0 || index >= unit.questions.length) return;
    ui.question = index; replaceQuestion();
  }
  function replaceQuestion() {
    const replacement = renderPractice(unit, ui, progress, persist); root.replaceWith(replacement);
    replacement.dispatchEvent(new CustomEvent('study-activity-change', { bubbles: true }));
    const legend = replacement.querySelector('legend'); focusHeading(legend); legend.scrollIntoView({ block: 'nearest' });
  }
  navigation.append(prev, next); meta.append(position, navigation);
  root.append(meta, form, feedback);
  return root;
}
