import data from './data.mjs';
import { node, button, append, sourcesNote } from './dom.mjs';
import { iconButton } from './navigation.mjs';

export function flashcardShortcut(event) {
  if (event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (!(event.target instanceof Element)) return;
  const root = document.querySelector('[data-flashcards]');
  if (!root || event.target.closest('input,textarea,select,[contenteditable],a,[role="tab"],summary')) return;
  const control = event.target.closest('button');
  if (control && (!root.contains(control) || (event.key === ' ' && control.dataset.cardAction !== 'flip'))) return;
  const action = { ArrowLeft: 'previous', ArrowRight: 'next', ' ': 'flip', '1': 'again', '2': 'got' }[event.key];
  const target = action && root.querySelector(`[data-card-action="${action}"]`);
  if (!target || target.disabled || target.hidden || target.closest('[hidden]')) return;
  event.preventDefault(); if (!event.repeat) target.click();
}

export function renderFlashcards(unit, ui, progress, persist) {
  const root = node('div', 'flashcard-activity'); root.dataset.flashcards = '';
  const card = unit.flashcards[ui.card], key = `${unit.key}:${unit.revision}:${card.key}`;
  const meta = node('div', 'recall-meta');
  meta.append(node('p', 'small', `${ui.card + 1} / ${unit.flashcards.length}`));
  const arrows = node('div', 'cluster');
  const prev = iconButton('Previous card (Left arrow)', 'left', () => move(-1));
  const next = iconButton('Next card (Right arrow)', 'right', () => move(1));
  prev.disabled = ui.card === 0; next.disabled = ui.card === unit.flashcards.length - 1;
  prev.dataset.cardAction = 'previous'; next.dataset.cardAction = 'next';
  prev.setAttribute('aria-keyshortcuts', 'ArrowLeft'); next.setAttribute('aria-keyshortcuts', 'ArrowRight');
  arrows.append(prev, next); meta.append(arrows);
  const surface = button('', flip, 'flashcard'); surface.dataset.cardAction = 'flip';
  surface.title = 'Flip card (Space)'; surface.setAttribute('aria-keyshortcuts', 'Space');
  const turn = node('span', 'card-turn');
  const front = node('span', 'card-face card-front'); front.id = 'card-front';
  front.append(node('span', 'small', 'Question'), node('span', 'recall-prompt', card.front));
  const back = node('span', 'card-face card-back'); back.id = 'card-back';
  back.append(node('span', 'small', 'Answer'), node('span', 'recall-prompt', card.back));
  turn.append(front, back); surface.append(turn);
  const note = sourcesNote(card.sources, data.sources, data.course.synthetic);
  const status = node('p', 'card-status small'); status.setAttribute('aria-live', 'polite');
  const again = button('Again', () => rate(false)); again.dataset.cardAction = 'again';
  const got = button('Got it', () => rate(true)); got.dataset.cardAction = 'got';
  for (const [control, keyLabel] of [[again, '1'], [got, '2']]) {
    control.setAttribute('aria-label', control.textContent); control.title = `${control.textContent} (${keyLabel})`;
    control.append(node('kbd', '', keyLabel)); control.setAttribute('aria-keyshortcuts', keyLabel);
  }
  const ratings = append(node('div', 'cluster card-ratings'), again, got);
  const hint = node('p', 'card-shortcuts small');
  hint.append(node('kbd', '', '←'), node('kbd', '', '→'), document.createTextNode(' move · '), node('kbd', '', 'Space'), document.createTextNode(' flip'));
  function update() {
    surface.dataset.revealed = String(ui.revealed);
    surface.setAttribute('aria-pressed', String(ui.revealed));
    surface.setAttribute('aria-labelledby', ui.revealed ? back.id : front.id);
    front.setAttribute('aria-hidden', String(ui.revealed)); back.setAttribute('aria-hidden', String(!ui.revealed));
    front.inert = ui.revealed; back.inert = !ui.revealed;
    ratings.hidden = !ui.revealed; note.hidden = !ui.revealed;
    again.setAttribute('aria-pressed', String(progress.cards[key] === false));
    got.setAttribute('aria-pressed', String(progress.cards[key] === true));
  }
  function flip() { ui.revealed = !ui.revealed; update(); }
  function rate(remembered) {
    if (!ui.revealed) return;
    progress.cards[key] = remembered; persist(); update();
    status.textContent = remembered ? 'Got it.' : 'Marked for review.';
  }
  function move(delta) {
    const index = ui.card + delta;
    if (index < 0 || index >= unit.flashcards.length) return;
    ui.card = index; ui.revealed = false;
    const replacement = renderFlashcards(unit, ui, progress, persist);
    root.replaceWith(replacement); replacement.querySelector('.flashcard').focus({ preventScroll: true });
  }
  update(); root.append(meta, surface, ratings, status, note, hint);
  return root;
}
