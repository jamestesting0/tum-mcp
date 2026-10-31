import data from './data.mjs';
import { node, studyText, button, append, announce, sourcesNote, shareCitations, focusHeading, scrollReadingTo, preparationDisclosure } from './dom.mjs';
import { renderReading, renderBlockBody, renderAnswers } from './reading.mjs';
import { iconButton, nextStep } from './navigation.mjs';
import { renderResponse, optionExplanations, expectedAnswer } from './exercise-response.mjs';
import { annotateExercise } from './anchors.mjs';
import { markCompleted } from './completion.mjs';
import { codeReferences, filesIn } from './files.mjs';
import { renderCommentedView } from './comments.mjs';

const sets = data.exercises?.sets || [];
const ordered = sets.flatMap(group => group.exercises.map(exercise => ({ group, exercise })));
export const exerciseLink = (group, exercise, step = '') => `#exercises/${group.key}/${exercise.key}${step ? `/${step}` : ''}`;
function due(group) {
  const time = group.due_at && new Date(group.due_at);
  return time && Number.isFinite(time.getTime())
    ? `Due ${new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(time)}` : '';
}

export function exerciseOutline(current = '', compact = false) {
  const root = node(compact ? 'nav' : 'section', compact ? 'unit-list' : 'exercise-list');
  root.setAttribute('aria-label', 'Course exercises');
  // Problems not prepared yet, so a partial workspace never looks complete.
  const pending = data.pending || [], unstarted = pending.filter(item => !item.set);
  let category = null;
  for (const group of sets) {
    // A category is named only when it groups several sets and says more than their titles;
    // otherwise a thin rule marks where the next group starts.
    let starts = false;
    if ((group.category || '') !== category) {
      starts = category !== null; category = group.category || '';
      const members = sets.filter(item => (item.category || '') === category);
      if (category && members.length > 1 && !members.every(item => item.title.startsWith(category))) {
        root.append(studyText(compact ? 'p' : 'h2', compact ? 'small' : 'topic-group', category)); starts = false;
      }
    }
    const sheet = node('details', `unit-group exercise-sheet${starts ? ' group-start' : ''}`);
    sheet.open = group.exercises.some(item => item.key === current) || group === sets[0];
    const summary = node('summary');
    if (compact) summary.append(studyText('span', '', group.title));
    else {
      const count = group.exercises.length;
      const meta = [`${count} ${count === 1 ? 'problem' : 'problems'}`, group.week, due(group)].filter(Boolean).join(' · ');
      summary.append(append(node('span', 'sheet-copy'), studyText('span', 'topic-title', group.title), node('span', 'small', meta)));
    }
    sheet.append(summary);
    const list = node('div', compact ? 'group-children' : '');
    if (!compact && group.summary) list.append(studyText('p', 'sheet-summary', group.summary));
    if (!compact) for (const entry of pending.filter(item => item.set === group.key)) list.append(studyText('p', 'small pending', `Not prepared yet: ${entry.labels.join(', ')}`));
    for (const exercise of group.exercises) {
      const link = node('a', 'unit-link'); link.href = exerciseLink(group, exercise);
      if (exercise.key === current) link.setAttribute('aria-current', 'page');
      link.append(studyText('span', 'unit-title', `${exercise.label} · ${exercise.title}`));
      list.append(link);
    }
    sheet.append(list); root.append(sheet);
  }
  if (!compact && unstarted.length) {
    root.append(preparationDisclosure({ title: 'Not prepared yet', noun: 'sheet',
      description: 'These sheets do not have prepared exercises yet.',
      entries: unstarted.map(entry => ({ title: entry.source, labels: [entry.labels.join(', ')] })),
    }));
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

// The Study passage a prerequisite names, opened beside the exercise instead of in its place,
// so the step, drafts and scroll position stay where the student left them.
const wide = matchMedia('(min-width: 1200px)');
function openReference(unit, block, trigger) {
  document.querySelector('dialog.reference-panel')?.close();
  const panel = node('dialog', 'reference-panel'), title = studyText('h2', '', block ? block.title || block.term : unit.title);
  title.id = 'reference-panel-title'; panel.setAttribute('aria-labelledby', title.id);
  const close = iconButton('Close', 'close', () => panel.close());
  const eyebrow = append(node('div', 'page-eyebrow'), node('p', 'small', unit.title));
  if (block) eyebrow.append(sourcesNote(block.sources, data.sources, data.course.synthetic, block.title || block.term, {}, block.pages));
  const heading = append(node('div', ''), eyebrow, title);
  const header = append(node('div', 'reference-panel-header'), heading, close);
  // One passage under the panel's own title; a whole unit keeps its section titles.
  const body = block ? append(node('div', 'reading-material'), renderBlockBody(block, { term: false })) : renderReading({ blocks: unit.blocks });
  const more = quietLink('Open in Study', `#${unit.key}/content${block?.key ? `/${block.key}` : ''}`);
  panel.append(header, body, append(node('p', 'small reference-panel-more'), more));
  // Returning focus can scroll the page; the student comes back to exactly where they were.
  const scroller = trigger.closest('main')?.scrollHeight > trigger.closest('main')?.clientHeight ? trigger.closest('main') : document.scrollingElement;
  const top = scroller.scrollTop;
  panel.addEventListener('close', () => {
    panel.remove(); delete document.documentElement.dataset.reference;
    if (trigger.isConnected) trigger.focus({ preventScroll: true });
    scroller.scrollTop = top;
  });
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); panel.close(); } });
  addEventListener('hashchange', () => panel.close(), { once: true });
  document.body.append(panel);
  // Wide screens keep the exercise readable beside the panel; narrower ones give the panel the screen.
  if (wide.matches) { document.documentElement.dataset.reference = 'open'; panel.show(); } else panel.showModal();
  close.focus();
}

export function renderExercises(hash, state) {
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
    if (sets.length || data.pending?.some(item => !item.set)) root.append(exerciseOutline());
    else {
      root.append(node('p', '', 'Exercises have not been prepared for this course.'));
      if (data.units.length) root.append(quietLink('Open Study', '#home'));
    }
    return { root, heading, title: 'Exercises' };
  }
  const following = ordered[ordered.findIndex(item => item.exercise === exercise) + 1];
  return exercisePage(exercise, {
    state, stepKey, completes: exerciseLink(group, exercise),
    eyebrow: [group.title, exercise.label, due(group)].filter(Boolean).join(' · '),
    link: step => exerciseLink(group, exercise, step),
    annotate: (element, field, step) => annotateExercise(element, group, exercise, field, step),
    comment: root => renderCommentedView({ ...exercise, setKey: group.key }, 'exercises', root).root,
    onward: following && { href: exerciseLink(following.group, following.exercise), title: following.exercise.title, detail: following.exercise.label },
  });
}

// One exercise with optional guided steps and a solution; Exam reuses it for past papers.
export function exercisePage(exercise, options) {
  const { state, stepKey } = options;
  const root = node('div', 'exercise-workspace');
  const value = state.get(exercise);
  const requestedStep = stepKey || value.lastStep;
  const workspaceFiles = filesIn(exercise.statement);
  const heading = studyText('h1', '', exercise.title), header = node('div', 'unit-header');
  const target = (element, field, step = '') => options.annotate(element, field, step);
  const activityChanged = () => root.dispatchEvent(new Event('study-activity-change', { bubbles: true }));
  const eyebrow = studyText('p', 'eyebrow', options.eyebrow);
  header.append(eyebrow, heading);
  if (exercise.kind === 'distilled') {
    const practice = node('p', 'small practice-for', 'Practice for ');
    exercise.distilled_from.forEach((key, index) => {
      const original = ordered.find(entry => entry.exercise.key === key);
      if (!original) return;
      if (index) practice.append(', ');
      practice.append(quietLink(`${original.exercise.label} · ${original.exercise.title}`, exerciseLink(original.group, original.exercise)));
    });
    header.append(practice);
  }
  root.append(header);
  // Under a "Question N" heading the statement's own block titles would only repeat it.
  const statement = options.untitledStatement ? append(node('div', 'exam-stem'), ...exercise.statement.map(renderBlockBody)) : renderReading({ blocks: exercise.statement });
  statement.id = 'exercise-question';
  [...statement.querySelectorAll(options.untitledStatement ? '.block-body' : '.reading-material')].forEach((element, index) => target(element, `statement:${index}`));
  const partSections = new Map();
  let partSection = null, partLevel = 0;
  for (const section of [...statement.children]) {
    const block = exercise.statement[Number(section.dataset.blockIndex)];
    const part = Object.entries(exercise.part_blocks || {}).find(([, key]) => key === block?.key)?.[0];
    if (part) {
      partSection = node('div', 'exercise-part'); partSection.dataset.part = part;
      statement.insertBefore(partSection, section); partSections.set(part, partSection);
      partLevel = block.level || 1;
    } else if (partSection && block?.title && (block.level || 1) <= partLevel) {
      partSection = null;
    }
    if (partSection) partSection.append(section);
  }
  root.append(statement);
  for (const prerequisite of exercise.prerequisites) {
    const note = studyText('p', 'small prerequisite', prerequisite.explanation);
    const unit = data.units.find(item => item.key === prerequisite.unit);
    const block = unit?.blocks.find(item => prerequisite.block && item.key === prerequisite.block);
    if (unit) {
      const review = button(`Review ${block ? block.title || block.term : unit.title}`, () => openReference(unit, block, review), 'quiet reference-trigger');
      note.append(' ', review);
    }
    root.insertBefore(note, statement);
  }
  // One guide per original part, as each part is its own problem; a single-part exercise has one.
  const groups = [];
  for (const step of exercise.steps) {
    const last = groups[groups.length - 1];
    if (last && last.part === (step.part || null)) last.steps.push(step);
    else groups.push({ part: step.part || null, steps: [step] });
  }
  const multi = groups.length > 1;
  const onward = options.onward && nextStep(options.onward);
  const help = node('div', 'exercise-help');
  function verdict(correct, ...paragraphs) {
    const section = node('section', `feedback${correct ? '' : ' incorrect'}`);
    section.append(node('h3', '', correct ? 'Correct' : 'Not quite'), ...paragraphs);
    return section;
  }
  const guides = groups.map((group, groupIndex) => {
    const steps = group.steps, lastGroup = groupIndex === groups.length - 1;
    const partBlock = !options.untitledStatement && group.part
      && exercise.statement.find(block => block.key === exercise.part_blocks[group.part]);
    const guideLevel = partBlock ? (partBlock.level || 1) + 2 : 2;
    const panel = node('section', 'exercise-step');
    if (groupIndex === 0 && exercise.objectives?.length) {
      const goals = node('div', 'exercise-goals');
      goals.append(node('p', 'small objectives-label', 'Goals'), append(node('ul'), ...exercise.objectives.map(text => studyText('li', '', text))));
      panel.append(goals);
    }
    const owns = key => steps.some(item => item.key === key);
    const opened = Boolean(stepKey) ? owns(stepKey) : value.helpOpen && (owns(value.lastStep) || (!multi));
    const label = multi ? `Guide · ${group.part}` : 'Guidance';
    const details = disclosure(label, panel, opened, isOpen => {
      value.helpOpen = isOpen;
      if (isOpen) value.lastStep = steps[index].key;
      state.save(exercise); activityChanged();
    });
    details.classList.add('exercise-guide');
    details.querySelector('summary').dataset.contentsLevel = String(Math.min(6, guideLevel));
    let index = steps.findIndex(item => item.key === (stepKey || value.lastStep));
    if (index < 0) index = 0;
    const navigation = node('div', 'step-navigation'), counter = node('p', 'small');
    const prev = iconButton('Previous step', 'left', event => { event.currentTarget.focus({ preventScroll: true }); location.hash = options.link(steps[index - 1].key); });
    const next = iconButton('Next step', 'right', event => {
      event.currentTarget.focus({ preventScroll: true });
      const savedStep = value.steps[steps[index].key];
      if (savedStep.checked === null && !savedStep.compared) savedStep.skipped = true;
      state.save(exercise);
      location.hash = options.link(steps[index + 1].key);
    });
    navigation.append(counter, prev, next);
    const body = node('div', 'step-body'); panel.append(navigation, body);
    function paint() {
      const step = steps[index], saved = value.steps[step.key];
      value.lastStep = step.key; body.replaceChildren();
      counter.textContent = `Step ${index + 1} / ${steps.length}`;
      prev.disabled = index === 0; next.disabled = index === steps.length - 1;
      const title = target(studyText(`h${Math.min(6, guideLevel)}`, '', step.prompt), 'prompt', step.key);
      title.dataset.stepPrompt = '';
      const citations = step.sources?.length ? step.sources : step.check?.graph?.sources || step.check?.plot?.sources || exercise.sources.map(item => item.key);
      body.append(append(node('div', 'section-heading'), title, sourcesNote(citations, data.sources, data.course.synthetic, step.prompt)));
      if (step.blocks?.length) {
        const rich = renderReading({ blocks: step.blocks }, { depth: guideLevel });
        [...rich.querySelectorAll('.reading-material')].forEach((element, i) => target(element, `block:${i}`, step.key));
        body.append(rich);
      }
      if (step.code?.length) body.append(codeReferences(step.code, workspaceFiles));
      const feedback = node('div', 'exercise-feedback');
      feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
      let checked = saved.checked === saved.draft && saved.checked !== null;
      const check = step.check;
      const response = renderResponse(check, saved.draft, text => {
        saved.draft = text.slice(0, 64000); saved.checked = null; checked = false; saved.compared = false;
        state.save(exercise); update(); activityChanged();
      }, `exercise-${exercise.key}-${step.key}`, (step.code || []).map(ref => ref.path));
      if (response.root.matches('.reading-material')) target(response.root, 'graph', step.key);
      for (const element of response.root.querySelectorAll('.reading-material')) target(element, 'graph', step.key);
      // Only a choice is checked; every other step, including one without a check, is compared.
      const compares = !check || check.kind !== 'choice';
      const primary = button('', event => {
        if (event.detail > 1) return;
        const result = response.validate();
        if ((checked && result.correct) || (compares && saved.compared)) { advance(); return; }
        if (compares) { saved.compared = true; state.attempt(exercise, step); }
        else if (result.valid) { saved.checked = saved.draft; checked = true; state.attempt(exercise, step, result.correct); }
        state.save(exercise); update(); activityChanged();
      }, 'primary');
      primary.addEventListener('keydown', event => { if (event.repeat) event.preventDefault(); });
      const hints = node('div', 'exercise-hints stack');
      function paintHelp() {
        hints.replaceChildren();
        for (const [i, text] of step.hints.slice(0, saved.hints).entries()) hints.append(target(studyText('p', '', text), `hint:${i}`, step.key));
      }
      // Hints are the only help before Compare; Compare is the one place the answer and its reasoning appear.
      const hint = button('', () => {
        if (saved.hints >= step.hints.length) return;
        saved.hints++; announce(step.hints[saved.hints - 1]);
        paintHelp(); update(); state.save(exercise); activityChanged();
      }, 'secondary');
      const finishes = index === steps.length - 1 && lastGroup;
      function update() {
        const result = response.validate(); feedback.replaceChildren(); target(feedback, 'feedback', step.key);
        response.showResult(!compares && checked);
        if (compares && saved.compared) {
          const section = node('section', 'feedback compare');
          section.append(node('h3', '', 'Compare with your work'));
          if (check) section.append(expectedAnswer(check));
          section.append(studyText('p', '', step.explanation));
          if (check?.feedback) section.append(append(node('p', 'small'), node('strong', '', 'If yours differs: '), studyText('span', '', check.feedback)));
          feedback.append(section);
        } else if (checked && result.valid) {
          feedback.append(result.correct ? verdict(true, studyText('p', '', step.explanation)) : verdict(false, ...result.repairs.map(repair => studyText('p', '', repair))));
          if (check.kind === 'choice') feedback.append(optionExplanations(check, `exercise-${exercise.key}-${step.key}`));
        }
        const ready = compares ? saved.compared : checked && result.correct;
        primary.textContent = ready ? (finishes ? 'Finish' : 'Continue') : compares ? 'Compare' : 'Check answer';
        primary.disabled = Boolean(check && !compares && !result.valid);
        hint.textContent = saved.hints ? 'Next hint' : 'Hint';
        hint.hidden = ready || saved.hints >= step.hints.length;
      }
      const actions = append(node('div', 'cluster exercise-actions'), primary, hint);
      body.append(response.root, actions, feedback, hints);
      paintHelp();
      function advance() {
        if (index < steps.length - 1) { location.hash = options.link(steps[index + 1].key); return; }
        // The last step of one part leads to the next part's guide.
        if (!lastGroup) { location.hash = options.link(groups[groupIndex + 1].steps[0].key); return; }
        // Finishing the last step marks the exercise completed, as right-clicking its entry does.
        if (options.completes) { markCompleted(options.completes); announce('Marked completed.'); }
        const destination = onward?.querySelector('a');
        if (destination) { scrollReadingTo(onward); destination.focus({ preventScroll: true }); }
      }
      update(); state.save(exercise); if (root.dataset.citations !== undefined) shareCitations(root, eyebrow); return title;
    }
    if (group.part && !options.untitledStatement) partSections.get(group.part).append(append(node('div', 'exercise-part-help'), details));
    else help.append(details);
    return { steps, details, panel, navigation, owns, paint, get index() { return index; }, set index(value) { index = value; } };
  });
  guides.forEach(guide => guide.paint());
  // Painting every guide moves lastStep; it belongs to the step the student opened.
  const active = guides.find(guide => guide.owns(requestedStep)) || guides[0];
  value.lastStep = active.steps[active.index].key;
  state.save(exercise);
  root.append(help);
  let trim = null;
  if (partSections.size) {
    exercise.parts.forEach((part, index) => {
      const controls = partSections.get(part).querySelector('.exercise-part-help');
      const saved = value.partSolutions[part];
      const answer = renderAnswers(exercise.solution, (element, field) => target(element, field), index);
      const solution = disclosure('Solution', answer, saved.open, opened => {
        saved.open = opened; saved.viewed ||= opened; state.save(exercise); activityChanged();
      });
      solution.classList.add('exercise-solution');
      solution.querySelector('summary').dataset.contentsLevel = controls.querySelector('summary').dataset.contentsLevel;
      controls.append(solution);
    });
    if (exercise.solution.notes?.length) {
      const notes = renderAnswers({ answers: [], notes: exercise.solution.notes }, (element, field) => target(element, field));
      help.append(disclosure('Solution notes', notes, value.solutionOpen, opened => {
        value.solutionOpen = opened; state.save(exercise); activityChanged();
      }));
    }
  } else {
    const solution = renderAnswers(exercise.solution, (element, field) => target(element, field));
    help.append(disclosure('Solution', solution, value.solutionOpen, opened => {
      value.solutionOpen = opened; value.solutionViewed ||= opened; state.save(exercise); activityChanged();
    }));
  }
  if (exercise.transfer) {
    const answer = node('details', 'disclosure plain');
    answer.append(node('summary', '', 'Compare'), target(append(node('div', 'reading-material'), ...exercise.transfer.answer.map(block => renderBlockBody(block))), 'transfer-answer'));
    answer.addEventListener('toggle', activityChanged);
    help.append(disclosure('Try another', append(node('div', 'stack'), target(studyText('p', '', exercise.transfer.prompt), 'transfer-prompt'), answer), false, activityChanged));
  }
  if (onward) root.append(onward);
  shareCitations(root, eyebrow);
  return { root: options.comment(root),
    heading: stepKey ? active.panel.querySelector('[data-step-prompt]') : heading,
    title: `${exercise.label} · ${exercise.title}`, current: exercise.key,
    navigateStep(key) {
      const guide = guides.find(item => item.owns(key));
      if (!guide) return false;
      const nextIndex = guide.steps.findIndex(item => item.key === key), navigation = guide.navigation;
      const usingArrows = navigation.contains(document.activeElement);
      const previousTop = navigation.getBoundingClientRect().top;
      const scroller = matchMedia('(max-width: 799px)').matches ? document.scrollingElement : root.closest('main');
      trim?.(); root.style.paddingBottom = '0px';
      guide.index = nextIndex; guide.details.open = true; value.helpOpen = true;
      const prompt = guide.paint();
      if (usingArrows) { if (document.activeElement.disabled) (prev.disabled ? next : prev).focus({ preventScroll: true }); }
      else focusHeading(prompt);
      if (previousTop >= 0 && previousTop <= innerHeight - 44) {
        const desired = scroller.scrollTop + navigation.getBoundingClientRect().top - previousTop;
        const space = Math.max(0, desired - (scroller.scrollHeight - scroller.clientHeight));
        if (space) root.style.paddingBottom = `${Math.ceil(space)}px`;
        scroller.scrollTo({ top: desired, behavior: 'instant' });
        if (space) {
          // The padding only holds the arrows in place; it shrinks as the student scrolls up,
          // so the page never offers empty space below its end.
          const target = scroller === document.scrollingElement ? window : scroller;
          const shrink = () => {
            const padding = parseFloat(root.style.paddingBottom) || 0;
            const need = Math.max(0, Math.ceil(scroller.scrollTop + scroller.clientHeight - (scroller.scrollHeight - padding)));
            if (need < padding) root.style.paddingBottom = `${need}px`;
            if (!need) trim();
          };
          trim = () => { target.removeEventListener('scroll', shrink); trim = null; };
          target.addEventListener('scroll', shrink, { passive: true });
        }
      } else scrollReadingTo(navigation);
      announce(`Step ${nextIndex + 1} of ${guide.steps.length}. ${guide.steps[nextIndex].prompt}`);
      activityChanged(); return true;
    } };
}
