import data from '../../data.mjs';
import { node, studyText, button, append, announce, sourcesNote, shareCitations, focusHeading, scrollReadingTo, preparationDisclosure, topicRow, shuffled, pillPanel } from '../shell/dom.mjs';
import { renderReading, renderBlockBody, renderAnswers } from '../reading/reading.mjs';
import { arrowPaging, usePager, iconButton, iconGlyph, nextStep, cycleIndex } from '../shell/navigation.mjs';
import { renderResponse, optionExplanations, expectedAnswer } from './exercise-response.mjs';
import { annotateExercise } from '../comments/anchors.mjs';
import { markCompleted, isCompleted } from '../shell/completion.mjs';
import { recallRow, exerciseExamLinks } from '../study/recall.mjs';
import { codeReferences, filesIn } from '../shell/files.mjs';
import { renderCommentedView } from '../comments/comments.mjs';
import { exerciseVideo } from '../lecture/video.mjs';

const sets = data.exercises?.sets || [];
const ordered = sets.flatMap(group => group.exercises.map(exercise => ({ group, exercise })));
export const exerciseLink = (group, exercise, step = '') => `#exercises/${group.key}/${exercise.key}${step ? `/${step}` : ''}`;
function due(group) {
  const time = group.due_at && new Date(group.due_at);
  return time && Number.isFinite(time.getTime())
    ? `Due ${new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(time)}` : '';
}

// A category is named only when it groups several sets and says more than their titles.
function categoryLabel(group) {
  const category = group.category || '', members = sets.filter(item => (item.category || '') === category);
  return category && members.length > 1 && !members.every(item => item.title.startsWith(category)) ? category : '';
}

export function exerciseOutline(current = '') {
  const root = node('nav', 'unit-list');
  root.setAttribute('aria-label', 'Course exercises');
  let category = null;
  for (const group of sets) {
    // Otherwise a thin rule marks where the next group starts.
    let starts = false;
    if ((group.category || '') !== category) {
      starts = category !== null; category = group.category || '';
      if (categoryLabel(group)) { root.append(studyText('p', 'small', category)); starts = false; }
    }
    const sheet = node('details', `unit-group exercise-sheet${starts ? ' group-start' : ''}`);
    sheet.open = group.exercises.some(item => item.key === current) || group === sets[0];
    sheet.append(append(node('summary'), studyText('span', '', group.title)));
    const list = node('div', 'group-children');
    for (const exercise of group.exercises) {
      const link = node('a', 'unit-link'); link.href = exerciseLink(group, exercise);
      if (exercise.key === current) link.setAttribute('aria-current', 'page');
      link.append(studyText('span', 'unit-title', `${exercise.label} · ${exercise.title}`));
      list.append(link);
    }
    sheet.append(list); root.append(sheet);
  }
  return root;
}

// Any work on a problem: a viewed solution or a step drafted, hinted, compared, checked or skipped.
export const exerciseStarted = value => value.solutionViewed || Object.values(value.partSolutions).some(part => part.viewed)
  || Object.values(value.steps).some(step => step.draft || step.hints || step.compared || step.skipped || step.checked !== null);
function exerciseStatus(group, exercise, state) {
  if (isCompleted(exerciseLink(group, exercise))) return 'Done';
  return exerciseStarted(state.get(exercise)) ? 'In progress' : 'Not started';
}
// As on the Study home: continue the first problem in progress, or start the first one not started.
function resumeLink(state) {
  const rows = sets.flatMap(group => group.exercises.map(exercise => ({ group, exercise, status: exerciseStatus(group, exercise, state) })));
  const row = rows.find(item => item.status === 'In progress') || rows.find(item => item.status === 'Not started');
  if (!row) return null;
  const go = node('a', 'button primary resume'); go.href = exerciseLink(row.group, row.exercise);
  go.append(iconGlyph('play'), node('span', 'visually-hidden', `${row.status === 'In progress' ? 'Continue' : 'Start'}: `),
    studyText('span', '', `${row.exercise.label} · ${row.exercise.title}`));
  return go;
}
// The Exercises home lists sheets the way the Study home lists topics: a group heading, then
// one row per problem with its status.
function exerciseList(state) {
  const root = node('section', 'home-topics exercise-list');
  root.setAttribute('aria-label', 'Course exercises');
  // Problems not prepared yet, so a partial workspace never looks complete.
  const pending = data.pending || [], unstarted = pending.filter(item => !item.set);
  let category = null;
  for (const group of sets) {
    if ((group.category || '') !== category) {
      category = group.category || '';
      if (categoryLabel(group)) root.append(studyText('h2', 'topic-group', category));
    }
    root.append(studyText('h3', 'topic-group', group.title));
    const meta = [group.week, due(group)].filter(Boolean).join(' · ');
    if (meta) root.append(node('p', 'small sheet-meta', meta));
    if (group.summary) root.append(studyText('p', 'sheet-summary', group.summary));
    for (const entry of pending.filter(item => item.set === group.key)) {
      const label = entry.provisional ? 'Provisional practice still unprepared' : 'Not prepared yet';
      root.append(studyText('p', 'small pending', `${label}: ${entry.labels.join(', ')}`));
    }
    root.append(append(node('ul', 'topic-list'), ...group.exercises.map(exercise =>
      topicRow(exerciseLink(group, exercise), `${exercise.label} · ${exercise.title}`, [], exerciseStatus(group, exercise, state)))));
  }
  for (const [provisional, title] of [[false, 'Not prepared yet'], [true, 'Provisional practice']]) {
    const entries = unstarted.filter(entry => Boolean(entry.provisional) === provisional);
    if (entries.length) root.append(preparationDisclosure({ title, noun: 'sheet',
      entries: entries.map(entry => ({ title: entry.source, labels: [entry.labels.join(', ')] })),
    }));
  }
  return root;
}

function disclosure(label, content, opened, onToggle) {
  const details = node('details', 'disclosure exercise-disclosure'); details.open = opened;
  // Exercise sections are disclosures rather than headings; mark them so the contents outline lists them.
  const summary = node('summary', '', label); summary.dataset.contentsEntry = '';
  // Guide, Solution and every other exercise section open into the same contained panel.
  content.classList.add('disclosure-panel');
  details.append(summary, content);
  details.addEventListener('toggle', () => onToggle(details.open)); return details;
}
function quietLink(label, href) { const link = node('a', '', label); link.href = href; return link; }

export function renderExercises(hash, state) {
  const root = node('div', 'exercise-workspace'), [, setKey, exerciseKey, stepKey] = hash.split('/');
  let group = sets.find(item => item.key === setKey);
  let exercise = group?.exercises.find(item => item.key === exerciseKey);
  if (!exercise && exerciseKey) {
    group = sets.find(item => item.exercises.some(candidate => candidate.key === exerciseKey));
    exercise = group?.exercises.find(item => item.key === exerciseKey);
  }
  if (!exercise) {
    const heading = node('h1', '', 'Exercises'), header = append(node('div', 'unit-header'), node('p', 'eyebrow', data.course.title), heading);
    root.append(header);
    if (exerciseKey) root.append(node('p', 'notice', 'That exercise is no longer here.'));
    const empty = !sets.length && !data.pending?.some(item => !item.set);
    const resume = resumeLink(state);
    if (resume) header.append(append(node('div', 'cluster home-actions'), resume));
    if (!empty) root.append(exerciseList(state));
    else {
      root.append(node('p', '', 'Exercises have not been prepared for this course.'));
      if (data.units.length) root.append(quietLink('Open Study', '#home'));
    }
    return { root, heading, title: 'Exercises', empty };
  }
  const following = ordered[ordered.findIndex(item => item.exercise === exercise) + 1];
  return exercisePage(exercise, {
    state, stepKey, completes: exerciseLink(group, exercise), video: `${group.key}/${exercise.key}`, set: group.key,
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
  // The lesson first, then the cheatsheet entry, then the exam patterns that use it.
  const examLinks = options.set ? exerciseExamLinks(options.set, exercise.key) : { patterns: [], ideas: [] };
  const recall = recallRow([...exercise.prerequisites.map(prerequisite => {
    const unit = data.units.find(item => item.key === prerequisite.unit);
    const index = unit ? unit.blocks.findIndex(item => prerequisite.block && item.key === prerequisite.block) : -1;
    // Before Study is prepared, the explanation itself is the reminder.
    if (!unit) return { label: prerequisite.explanation };
    // An untitled block is named by the section it continues.
    const named = unit.blocks.slice(0, index + 1).reverse().find(item => item.title || item.term);
    return { label: named ? named.title || named.term : unit.title, line: prerequisite.explanation, unit: prerequisite.unit, block: prerequisite.block };
  }), ...examLinks.ideas, ...examLinks.patterns].filter((item, at, all) => all.findIndex(other => other.label === item.label) === at));
  if (recall) root.insertBefore(recall, statement);
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
    const owns = key => steps.some(item => item.key === key);
    const opened = Boolean(stepKey) ? owns(stepKey) : value.helpOpen && (owns(value.lastStep) || (!multi));
    let index = steps.findIndex(item => item.key === (stepKey || value.lastStep));
    if (index < 0) index = 0;
    const navigation = node('div', 'step-navigation'), counter = node('span', 'step-count');
    const prev = iconButton('Previous step', 'left', event => { event.currentTarget.focus({ preventScroll: true }); location.hash = options.link(steps[cycleIndex(index - 1, steps.length)].key); });
    const next = iconButton('Next step', 'right', event => {
      event.currentTarget.focus({ preventScroll: true });
      const savedStep = value.steps[steps[index].key];
      if (savedStep.checked === null && !savedStep.compared) savedStep.skipped = true;
      state.save(exercise);
      location.hash = options.link(steps[cycleIndex(index + 1, steps.length)].key);
    });
    navigation.append(append(node('p', 'small'), counter), prev, next);
    const body = node('div', 'step-body'); panel.append(navigation, body);
    arrowPaging(panel, prev, next, { active: opened });
    function paint() {
      const step = steps[index], saved = value.steps[step.key];
      value.lastStep = step.key; body.replaceChildren();
      counter.textContent = `Step ${index + 1} of ${steps.length}`;
      prev.disabled = next.disabled = steps.length < 2;
      const title = target(studyText(`h${Math.min(6, guideLevel)}`, '', step.prompt), 'prompt', step.key);
      title.dataset.stepPrompt = '';
      const citations = step.sources?.length ? step.sources : step.check?.graph?.sources || step.check?.plot?.sources || exercise.sources.map(item => item.key);
      body.append(append(node('div', 'section-heading'), title, sourcesNote(citations, data.sources, data.course.synthetic, step.prompt)));
      if (step.blocks?.length) {
        const rich = renderReading({ blocks: step.blocks }, { depth: guideLevel, inherited: citations });
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
          section.append(node('h3', '', 'Answer'));
          if (check) section.append(expectedAnswer(check));
          section.append(studyText('p', '', step.explanation));
          if (check?.feedback) section.append(append(node('p', 'small'), node('strong', '', 'If yours differs: '), studyText('span', '', check.feedback)));
          feedback.append(section);
        } else if (checked && result.valid) {
          // A choice opens with the chosen option's feedback, as in Practice; Explain covers the rest.
          const choice = check.kind === 'choice', said = (choice || !result.correct ? result.repairs : []).map(repair => studyText('p', '', repair));
          const section = verdict(result.correct, ...said, ...(result.correct ? [studyText('p', '', step.explanation)] : []));
          if (choice) section.append(optionExplanations(shuffled(check.options, `exercise-${exercise.key}-${step.key}`), check.correct, result.chosen));
          feedback.append(section);
        }
        const ready = compares ? saved.compared : checked && result.correct;
        primary.textContent = ready ? (finishes ? 'Finish' : 'Next step') : compares ? 'Compare' : 'Check';
        primary.disabled = Boolean(check && !compares && !result.valid);
        hint.textContent = 'Hint';
        hint.hidden = ready || saved.hints >= step.hints.length;
      }
      // The answer appears before the button that moves on, so the student reads it first.
      const actions = append(node('div', 'cluster exercise-actions'), primary, hint);
      body.append(response.root, hints, feedback, actions);
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
    return { part: group.part, reveal: () => {}, steps, panel, navigation, owns, opened, paint, get index() { return index; }, set index(value) { index = value; } };
  });
  guides.forEach(guide => guide.paint());
  // Painting every guide moves lastStep; it belongs to the step the student opened.
  const active = guides.find(guide => guide.owns(requestedStep)) || guides[0];
  value.lastStep = active.steps[active.index].key;
  state.save(exercise);
  root.append(help);
  let trim = null;
  // Guide and Solution share one pill and one panel per part; the open segment is remembered.
  const guideValue = guide => `guide:${guides.indexOf(guide)}`;
  function helpPill(own, solution, solutionOpen, saveSolution) {
    const segments = own.map(guide => ({ value: guideValue(guide), label: own.length > 1 && guide.part ? `Guide ${guide.part}` : 'Guide', content: guide.panel }));
    if (solution) segments.push({ value: 'solution', label: 'Solution', content: solution });
    const openGuide = own.find(guide => guide.opened);
    const selected = solution && solutionOpen ? 'solution' : openGuide ? guideValue(openGuide) : null;
    const choose = chosen => {
      const guide = guides.find(item => guideValue(item) === chosen);
      value.helpOpen = Boolean(guide);
      if (guide) { value.lastStep = guide.steps[guide.index].key; usePager(guide.panel); }
      if (solution) saveSolution(chosen === 'solution');
      state.save(exercise); activityChanged();
    };
    const pill = pillPanel('Help', segments, { selected, onChange: choose });
    for (const guide of own) guide.reveal = () => { pill.open(guideValue(guide)); choose(guideValue(guide)); };
    return pill.element;
  }
  const placed = new Set();
  if (partSections.size) {
    exercise.parts.forEach((part, index) => {
      const saved = value.partSolutions[part], own = guides.filter(guide => guide.part === part);
      own.forEach(guide => placed.add(guide));
      const answer = renderAnswers(exercise.solution, (element, field) => target(element, field), index);
      partSections.get(part).append(append(node('div', 'exercise-part-help'), helpPill(own, answer, saved.open, opened => {
        saved.open = opened; saved.viewed ||= opened;
      })));
    });
    const loose = guides.filter(guide => !placed.has(guide));
    if (loose.length) help.append(helpPill(loose, null));
    if (exercise.solution.notes?.length) {
      const notes = renderAnswers({ answers: [], notes: exercise.solution.notes }, (element, field) => target(element, field));
      help.append(disclosure('Solution notes', notes, value.solutionOpen, opened => {
        value.solutionOpen = opened; state.save(exercise); activityChanged();
      }));
    }
    if (options.video) help.append(exerciseVideo(exercise, options.video));
  } else {
    const solution = renderAnswers(exercise.solution, (element, field) => target(element, field));
    if (options.afterSolution) solution.append(options.afterSolution);
    help.append(helpPill(guides.filter(guide => guide.steps.length), solution, value.solutionOpen, opened => {
      value.solutionOpen = opened; value.solutionViewed ||= opened;
    }));
    if (options.video) {
      if (exercise.parts?.length > 1) help.append(exerciseVideo(exercise, options.video));
      else exerciseVideo(exercise, options.video, solution);
    }
  }
  if (exercise.transfer) {
    const answer = node('details', 'disclosure answer-reveal');
    answer.append(node('summary', '', 'Compare'), append(node('section', 'feedback compare'), node('h3', '', 'Answer'),
      target(append(node('div', 'reading-material'), ...exercise.transfer.answer.map(block => renderBlockBody(block))), 'transfer-answer')));
    answer.addEventListener('toggle', activityChanged);
    help.append(disclosure('Try another', append(node('div', 'stack'), target(studyText('p', '', exercise.transfer.prompt), 'transfer-prompt'), answer), false, activityChanged));
  }
  if (onward) root.append(onward);
  shareCitations(root, eyebrow);
  return { root: options.comment(root),
    heading: stepKey ? active.panel.querySelector('[data-step-prompt]') : heading,
    // A guided past question is labelled and titled "Question N"; the header names it once.
    title: [...new Set([exercise.label, exercise.title])].join(' · '), current: exercise.key,
    navigateStep(key) {
      const guide = guides.find(item => item.owns(key));
      if (!guide) return false;
      const nextIndex = guide.steps.findIndex(item => item.key === key), navigation = guide.navigation;
      const usingArrows = navigation.contains(document.activeElement);
      const previousTop = navigation.getBoundingClientRect().top;
      const scroller = matchMedia('(max-width: 799px)').matches ? document.scrollingElement : root.closest('main');
      trim?.(); root.style.paddingBottom = '0px';
      guide.index = nextIndex; guide.reveal();
      const prompt = guide.paint();
      if (usingArrows) { if (document.activeElement.disabled) navigation.querySelector('button:not(:disabled)')?.focus({ preventScroll: true }); }
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
