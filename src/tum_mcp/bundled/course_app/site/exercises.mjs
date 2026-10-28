import data from './data.mjs';
import { node, studyText, button, append, announce, sourcesNote, focusHeading, scrollReadingTo } from './dom.mjs';
import { renderReading } from './reading.mjs';
import { iconButton, nextStep } from './navigation.mjs';
import { renderResponse } from './exercise-response.mjs';
import { annotateExercise } from './anchors.mjs';
import { renderCommentedView } from './comments.mjs';

const sets = data.exercises?.sets || [];
const ordered = sets.flatMap(group => group.exercises.map(exercise => ({ group, exercise })));
export const exerciseLink = (group, exercise, step = '') => `#exercises/${group.key}/${exercise.key}${step ? `/${step}` : ''}`;
function due(group) {
  const time = group.due_at && new Date(group.due_at);
  return time && Number.isFinite(time.getTime())
    ? `Due ${new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(time)}` : '';
}

export function exerciseOutline(state, current = '', compact = false) {
  const root = node(compact ? 'nav' : 'section', compact ? 'unit-list' : 'exercise-list');
  root.setAttribute('aria-label', 'Course exercises');
  let category;
  for (const group of sets) {
    if (group.category && group.category !== category) {
      category = group.category; root.append(studyText(compact ? 'p' : 'h2', compact ? 'small' : 'topic-group', category));
    }
    const sheet = node('details', 'unit-group exercise-sheet');
    sheet.open = group.exercises.some(item => item.key === current) || group === sets[0];
    sheet.append(studyText('summary', '', group.title));
    const list = node('div', compact ? 'group-children' : '');
    const meta = [group.week, due(group)].filter(Boolean).join(' · ');
    if (!compact && (group.summary || meta)) {
      const about = node('div', 'sheet-meta');
      if (group.summary) about.append(studyText('p', 'unit-summary', group.summary));
      if (meta) about.append(node('p', 'small', meta));
      list.append(about);
    }
    for (const exercise of group.exercises) {
      const link = node('a', 'unit-link'); link.href = exerciseLink(group, exercise);
      if (exercise.key === current) link.setAttribute('aria-current', 'page');
      const status = node('span', 'small', state.status(exercise)); status.dataset.exerciseStatus = exercise.key;
      link.append(studyText('span', 'unit-title', `${exercise.label} · ${exercise.title}`), status);
      list.append(link);
    }
    sheet.append(list); root.append(sheet);
  }
  return root;
}

function disclosure(label, content, opened, onToggle) {
  const details = node('details', 'disclosure exercise-disclosure'); details.open = opened;
  // Exercise sections are disclosures rather than headings; mark them so the contents outline lists them.
  const summary = node('summary', '', label); summary.dataset.contentsEntry = '';
  details.append(summary, content);
  details.addEventListener('toggle', () => onToggle(details.open)); return details;
}
function quietLink(label, href) { const link = node('a', '', label); link.href = href; return link; }

export function renderExercises(hash, state, changed) {
  const root = node('div', 'exercise-workspace'), [, setKey, exerciseKey, stepKey] = hash.split('/');
  let group = sets.find(item => item.key === setKey);
  let exercise = group?.exercises.find(item => item.key === exerciseKey);
  if (!exercise && exerciseKey) {
    group = sets.find(item => item.exercises.some(candidate => candidate.key === exerciseKey));
    exercise = group?.exercises.find(item => item.key === exerciseKey);
  }
  if (!exercise) {
    const heading = node('h1', '', 'Exercises');
    root.append(append(node('div', 'unit-header'), node('p', 'eyebrow', data.course.title), heading));
    if (exerciseKey) root.append(node('p', 'notice', 'That exercise is no longer here. Choose a prepared exercise below.'));
    if (sets.length) root.append(exerciseOutline(state));
    else {
      root.append(node('p', '', 'Exercises have not been prepared for this course.'));
      if (data.units.length) root.append(quietLink('Open Study', '#home'));
    }
    return { root, heading, title: 'Exercises' };
  }
  const following = ordered[ordered.findIndex(item => item.exercise === exercise) + 1];
  return exercisePage(exercise, {
    state, changed, stepKey,
    eyebrow: [group.title, exercise.label, due(group)].filter(Boolean).join(' · '),
    link: step => exerciseLink(group, exercise, step),
    annotate: (element, field, step) => annotateExercise(element, group, exercise, field, step),
    comment: root => renderCommentedView({ ...exercise, setKey: group.key }, 'exercises', root).root,
    onward: following && { href: exerciseLink(following.group, following.exercise), title: following.exercise.title, detail: following.exercise.label },
  });
}

// One exercise with optional guided steps and a solution; Exam Prep reuses it for past papers.
export function exercisePage(exercise, options) {
  const { state, changed, stepKey } = options;
  const root = node('div', 'exercise-workspace');
  const value = state.get(exercise);
  value.started = true; state.save(exercise);
  const heading = studyText('h1', '', exercise.title), header = node('div', 'unit-header');
  const target = (element, field, step = '') => options.annotate(element, field, step);
  const activityChanged = () => root.dispatchEvent(new Event('study-activity-change', { bubbles: true }));
  header.append(studyText('p', 'eyebrow', options.eyebrow), heading);
  if (exercise.kind === 'distilled') {
    const practice = node('p', 'small practice-for', 'Practice for ');
    exercise.distilled_from.forEach((key, index) => {
      const original = ordered.find(entry => entry.exercise.key === key);
      if (!original) return;
      if (index) practice.append(', ');
      practice.append(quietLink(`${original.exercise.label} · ${original.exercise.title}`, exerciseLink(original.group, original.exercise)));
    });
    if (exercise.concepts?.length) practice.append(append(node('span', 'practice-concepts'), ...exercise.concepts.map(text => studyText('span', 'chip', text))));
    header.append(practice);
  }
  root.append(header);
  const statement = renderReading({ blocks: exercise.statement }); statement.id = 'exercise-question';
  [...statement.querySelectorAll('.reading-material')].forEach((element, index) => target(element, `statement:${index}`));
  root.append(statement);
  if (exercise.parts?.length) root.append(append(node('ul'), ...exercise.parts.map((part, index) => target(studyText('li', '', part), `part:${index}`))));
  for (const prerequisite of exercise.prerequisites) {
    const note = studyText('p', 'small', prerequisite.explanation);
    const unit = data.units.find(item => item.key === prerequisite.unit);
    if (unit) note.append(' ', quietLink(`Review ${unit.title}`, `#study/${unit.key}/content`));
    root.append(note);
  }
  const panel = node('section', 'exercise-step');
  if (exercise.objectives?.length) {
    const goals = node('div', 'exercise-goals');
    goals.append(node('p', 'small objectives-label', 'Goals'), append(node('ul'), ...exercise.objectives.map(text => studyText('li', '', text))));
    panel.append(goals);
  }
  const guidance = disclosure('Guidance', panel, value.helpOpen || Boolean(stepKey), opened => {
    value.helpOpen = opened; state.save(exercise); activityChanged();
  });
  root.append(guidance);
  let index = exercise.steps.findIndex(item => item.key === (stepKey || value.lastStep));
  if (index < 0) index = 0;
  const navigation = node('div', 'step-navigation'), counter = node('p', 'small');
  const prev = iconButton('Previous step', 'left', event => { event.currentTarget.focus({ preventScroll: true }); location.hash = options.link(exercise.steps[index - 1].key); });
  const next = iconButton('Next step', 'right', event => {
    event.currentTarget.focus({ preventScroll: true });
    const savedStep = value.steps[exercise.steps[index].key];
    if (savedStep.checked === null && !savedStep.compared) savedStep.skipped = true;
    state.save(exercise);
    location.hash = options.link(exercise.steps[index + 1].key);
  });
  navigation.append(counter, prev, next);
  const body = node('div', 'step-body'); panel.append(navigation, body);
  const mark = button(value.reviewed ? 'Reviewed' : 'Mark reviewed', () => setReviewed(!value.reviewed), 'secondary review-toggle');
  mark.setAttribute('aria-pressed', String(value.reviewed));
  function setReviewed(reviewed) {
    value.reviewed = reviewed; mark.textContent = reviewed ? 'Reviewed' : 'Mark reviewed';
    mark.setAttribute('aria-pressed', String(reviewed)); state.save(exercise); changed();
  }
  const onward = options.onward && nextStep(options.onward);
  function verdict(correct, ...paragraphs) {
    const section = node('section', `feedback${correct ? '' : ' incorrect'}`);
    section.append(node('h3', '', correct ? 'Correct' : 'Not quite'), ...paragraphs);
    return section;
  }
  function paintStep() {
    const step = exercise.steps[index], saved = value.steps[step.key];
    value.lastStep = step.key; body.replaceChildren();
    counter.textContent = `Step ${index + 1} / ${exercise.steps.length}`;
    prev.disabled = index === 0; next.disabled = index === exercise.steps.length - 1;
    const title = target(studyText('h2', '', step.prompt), 'prompt', step.key);
    const citations = step.sources?.length ? step.sources : step.check?.graph?.sources || step.check?.plot?.sources || exercise.sources.map(item => item.key);
    body.append(append(node('div', 'section-heading'), title, sourcesNote(citations, data.sources, data.course.synthetic, step.prompt)));
    if (step.blocks?.length) {
      const rich = renderReading({ blocks: step.blocks });
      [...rich.querySelectorAll('.reading-material')].forEach((element, i) => target(element, `block:${i}`, step.key));
      body.append(rich);
    }
    const feedback = node('div', 'exercise-feedback');
    feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
    let checked = saved.checked === saved.draft && saved.checked !== null;
    const check = step.check;
    const response = renderResponse(check, saved.draft, text => {
      saved.draft = text.slice(0, 64000); saved.checked = null; checked = false; saved.compared = false;
      state.save(exercise); update(); activityChanged();
    }, `exercise-${exercise.key}-${step.key}`);
    if (response.root.matches('.reading-material')) target(response.root, 'graph', step.key);
    for (const element of response.root.querySelectorAll('.reading-material')) target(element, 'graph', step.key);
    const primary = button('', event => {
      if (event.detail > 1) return;
      const result = response.validate();
      if (!check || (checked && result.correct) || (check.kind === 'self_check' && saved.compared)) { advance(); return; }
      if (check.kind === 'self_check') { saved.compared = true; state.attempt(exercise, step); }
      else if (result.valid) { saved.checked = saved.draft; checked = true; state.attempt(exercise, step, result.correct); }
      state.save(exercise); update(); activityChanged();
    }, 'primary');
    primary.addEventListener('keydown', event => { if (event.repeat) event.preventDefault(); });
    const hints = node('div', 'exercise-hints stack');
    function paintHelp() {
      hints.replaceChildren();
      for (const [i, text] of step.hints.slice(0, saved.hints).entries()) hints.append(target(studyText('p', '', text), `hint:${i}`, step.key));
      if (saved.revealed) hints.append(target(studyText('p', '', step.explanation), 'reasoning', step.key));
    }
    const hint = button('', () => {
      if (saved.hints < step.hints.length) { saved.hints++; announce(step.hints[saved.hints - 1]); }
      else { saved.revealed = true; announce(step.explanation); }
      paintHelp(); update(); state.save(exercise); activityChanged();
    }, 'secondary');
    function update() {
      const result = response.validate(); feedback.replaceChildren(); target(feedback, 'feedback', step.key);
      response.showResult(checked);
      if (check?.kind === 'self_check' && saved.compared) {
        const section = node('section', 'feedback');
        section.append(node('h3', '', 'Compare with your work'), studyText('p', '', check.model_answer), append(node('ul'), ...check.rubric.map(text => studyText('li', '', text))));
        feedback.append(section);
      } else if (checked && result.valid) {
        feedback.append(result.correct ? verdict(true, studyText('p', '', step.explanation)) : verdict(false, ...result.repairs.map(repair => studyText('p', '', repair))));
      } else if (saved.draft && check?.kind === 'numeric' && !result.valid) feedback.append(node('p', 'small', 'Enter a number such as 0.5 or 2e-3.'));
      const ready = !check || (check.kind === 'self_check' ? saved.compared : checked && result.correct);
      primary.textContent = ready ? (index === exercise.steps.length - 1 ? 'Finish' : 'Continue') : check.kind === 'self_check' ? 'Compare' : 'Check answer';
      primary.disabled = Boolean(check && check.kind !== 'self_check' && !result.valid);
      hint.textContent = saved.hints < step.hints.length ? (saved.hints ? 'Next hint' : 'Hint') : 'Show reasoning';
      hint.hidden = Boolean(check && ready) || saved.revealed;
    }
    const actions = append(node('div', 'cluster exercise-actions'), primary, hint);
    body.append(response.root, actions, feedback, hints);
    paintHelp();
    function advance() {
      if (index === exercise.steps.length - 1) {
        setReviewed(true); announce('Marked reviewed.');
        const destination = onward?.querySelector('a') || mark;
        scrollReadingTo(end); destination.focus({ preventScroll: true }); return;
      }
      location.hash = options.link(exercise.steps[index + 1].key);
    }
    update(); state.save(exercise); return title;
  }
  const end = append(node('div', 'cluster exercise-end'), mark);
  paintStep();
  const solution = append(node('div'), node('p', 'small', exercise.solution.origin === 'official' ? 'Official solution' : 'Prepared solution, not official'), renderReading({ blocks: exercise.solution.blocks }));
  [...solution.querySelectorAll('.reading-material')].forEach((element, index) => target(element, `solution:${index}`));
  root.append(disclosure('Solution', solution, value.solutionOpen, opened => {
    value.solutionOpen = opened; value.solutionViewed ||= opened; state.save(exercise); activityChanged();
  }));
  if (exercise.transfer) {
    const answer = node('details', 'disclosure plain');
    answer.append(node('summary', '', 'Compare'), target(studyText('p', '', exercise.transfer.answer), 'transfer-answer'));
    answer.addEventListener('toggle', activityChanged);
    root.append(disclosure('Try another', append(node('div', 'stack'), target(studyText('p', '', exercise.transfer.prompt), 'transfer-prompt'), answer), false, activityChanged));
  }
  root.append(end);
  if (onward) root.append(onward);
  return { root: options.comment(root),
    heading: stepKey ? panel.querySelector('.step-body h2') : heading,
    title: `${exercise.label} · ${exercise.title}`, current: exercise.key,
    navigateStep(key) {
      const nextIndex = exercise.steps.findIndex(item => item.key === key);
      if (nextIndex < 0) return false;
      const usingArrows = navigation.contains(document.activeElement);
      const previousTop = navigation.getBoundingClientRect().top;
      const scroller = matchMedia('(max-width: 799px)').matches ? document.scrollingElement : root.closest('main');
      root.style.paddingBottom = '0px';
      index = nextIndex; guidance.open = true; value.helpOpen = true;
      const prompt = paintStep();
      if (usingArrows) { if (document.activeElement.disabled) (prev.disabled ? next : prev).focus({ preventScroll: true }); }
      else focusHeading(prompt);
      if (previousTop >= 0 && previousTop <= innerHeight - 44) {
        const desired = scroller.scrollTop + navigation.getBoundingClientRect().top - previousTop;
        const space = Math.max(0, desired - (scroller.scrollHeight - scroller.clientHeight));
        if (space) root.style.paddingBottom = `${Math.ceil(space)}px`;
        scroller.scrollTo({ top: desired, behavior: 'instant' });
      } else scrollReadingTo(navigation);
      announce(`Step ${index + 1} of ${exercise.steps.length}. ${exercise.steps[index].prompt}`);
      activityChanged(); return true;
    } };
}
