import data from './data.mjs';
import { node, studyText, button, sourcesNote } from './dom.mjs';
import { iconButton, iconGlyph } from './navigation.mjs';

export function reviewQuestion(context) {
  const { unit, question, answer, trigger, position } = context;
  const dialog = node('dialog', 'question-review');
  const header = node('div', 'question-review-header');
  const owner = question.origin?.title || unit.title;
  header.append(node('p', 'small', `${position} · ${owner}`), iconButton('Close review', 'close', () => dialog.close()));
  const body = node('div', 'question-review-body');
  const heading = studyText('h2', '', question.prompt); heading.id = 'question-review-title';
  dialog.setAttribute('aria-labelledby', heading.id);
  body.append(heading);
  const choices = node('div', 'question-review-options'); choices.setAttribute('role', 'list');
  const explanation = node('div', 'question-review-explanation');
  function reveal(show) {
    choices.replaceChildren(); explanation.replaceChildren();
    for (const option of question.options) {
      const row = node('div', 'option'); row.setAttribute('role', 'listitem');
      const correct = show && option.key === question.correct;
      const chosen = answer?.checked && option.key === answer.selected;
      row.dataset.state = correct ? 'correct' : chosen ? 'incorrect' : 'other';
      const content = node('span', 'option-body'); content.append(studyText('span', '', option.text));
      if (correct || chosen) {
        const tag = node('span', 'option-state');
        tag.append(iconGlyph(correct ? 'check' : 'close'), chosen ? (correct ? 'Your answer · Correct' : 'Your answer') : 'Correct answer');
        content.append(tag);
      }
      row.append(content); choices.append(row);
    }
    if (show) {
      const chosen = answer?.checked && question.options.find(option => option.key === answer.selected);
      if (chosen && chosen.key !== question.correct) explanation.append(studyText('p', '', chosen.feedback));
      explanation.append(studyText('p', '', question.explanation), sourcesNote(question.sources, data.sources, data.course.synthetic));
    } else explanation.append(button('Show answer', () => { reveal(true); explanation.focus(); }, 'quiet'));
  }
  explanation.tabIndex = -1;
  reveal(context.answered);
  body.append(choices, explanation); dialog.append(header, body);
  trigger.closest('.practice-summary').append(dialog);
  function remove() { dialog.close(); }
  dialog.addEventListener('close', () => {
    removeEventListener('hashchange', remove); dialog.remove();
    if (trigger.isConnected) trigger.focus({ preventScroll: true });
  }, { once: true });
  dialog.addEventListener('click', event => {
    const box = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
  });
  addEventListener('hashchange', remove, { once: true });
  dialog.showModal();
}
