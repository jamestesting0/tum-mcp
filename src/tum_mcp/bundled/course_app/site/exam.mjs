import data from './data.mjs';
import { node, studyText, append } from './dom.mjs';
import { renderCommentedView } from './comments.mjs';
import { annotateExam } from './anchors.mjs';
import { exerciseState } from './exercise-state.mjs';
import { exercisePage } from './exercises.mjs';
import { exam, examPrefix, examStore, variants, sample, quietLink } from './exam-state.mjs';
import { renderSheet } from './exam-sheet.mjs';
import { renderPatternList, renderPattern } from './exam-patterns.mjs';
import { renderExamMode, paperFor, paperSummary } from './exam-mock.mjs';

const decode = value => { try { return decodeURIComponent(value || ''); } catch { return ''; } };
let store, guided;

function header(title, eyebrow, summary) {
  const heading = studyText('h1', '', title);
  const box = append(node('div', 'unit-header'), node('p', 'eyebrow', eyebrow), heading);
  if (summary) box.append(studyText('p', 'unit-summary', summary));
  return { box, heading };
}
function card(href, title, detail, status) {
  const link = node('a', 'exam-card'); link.href = href;
  link.append(node('span', 'exam-card-title', title), node('span', 'small', detail));
  if (status) link.append(node('span', 'small exam-card-status', status));
  return append(node('li'), link);
}
const replayable = () => variants.filter(({ variant }) => variant.replayable);

function home() {
  const { box, heading } = header('Exam Prep', data.course.title, 'Condensed knowledge, recurring question patterns and practice exams for this course.');
  const root = node('div', 'exam-home'); root.append(box);
  const profile = exam.profile;
  if (profile) {
    const facts = node('dl', 'exam-profile');
    const add = (label, value) => facts.append(node('dt', '', label), studyText('dd', '', value || 'Not stated'));
    add('Format', { written: 'Written exam', online: 'Online exam', programming: 'Programming exam', oral: 'Oral exam', mixed: 'Mixed format' }[profile.format]);
    add('Duration', profile.duration_minutes && `${profile.duration_minutes} minutes`);
    add('Points', profile.total_points && String(profile.total_points));
    add('Allowed aids', profile.allowed_aids);
    if (profile.languages?.length) add('Languages', profile.languages.join(', '));
    root.append(append(node('section', 'exam-section'), node('h2', '', 'The exam'), facts));
  }
  const stats = exam.statistics;
  const evidence = stats.sittings_considered
    ? `${stats.sittings_considered} past exam${stats.sittings_considered === 1 ? '' : 's'}${stats.years?.length ? ` (${stats.years[0]}–${stats.years[1]})` : ''}${stats.sittings_outdated ? `; ${stats.sittings_outdated} older one${stats.sittings_outdated === 1 ? '' : 's'} not counted` : ''}`
    : 'No past exams were available; patterns rely on course material.';
  root.append(node('p', 'small exam-evidence', evidence));
  const cards = node('ul', 'exam-cards');
  const flagged = store.flaggedCount();
  if (exam.concepts.length) cards.append(card('#exam/sheet', 'Cheatsheet', `${exam.concepts.length} entries${exam.map?.nodes?.length ? ' and a semester map' : ''}`, flagged ? `${flagged} marked for review` : ''));
  if (exam.patterns.length) cards.append(card('#exam/patterns', 'Exam patterns', `${exam.patterns.length} recurring question types`, sample(stats.patterns[stats.pattern_order[0]])));
  const papers = replayable().length, mocks = exam.mocks.length;
  if (papers || mocks) cards.append(card('#exam/practice', 'Practice exams', [papers && `${papers} past paper${papers === 1 ? '' : 's'}`, mocks && `${mocks} practice exam${mocks === 1 ? '' : 's'}`].filter(Boolean).join(' · ')));
  root.append(cards);
  return { root, heading, title: 'Exam Prep', items: [] };
}

function practice() {
  const { box, heading } = header('Practice exams', 'Exam Prep', 'Work through real past papers question by question with guidance, or take a paper under exam conditions.');
  const root = node('div', 'exam-practice'); root.append(box);
  const papers = replayable();
  if (papers.length) {
    const list = node('ul', 'exam-cards');
    for (const { variant } of papers) {
      const paper = paperFor('paper', variant.key);
      list.append(card(`#exam/paper/${variant.key}`, paper.title, `${variant.questions.length} question${variant.questions.length === 1 ? '' : 's'}`, paperSummary(paper, store)));
    }
    root.append(append(node('section', 'exam-section'), node('h2', '', 'Past papers'), list));
  }
  if (exam.mocks.length) {
    const list = node('ul', 'exam-cards');
    for (const mock of exam.mocks) {
      const paper = paperFor('mock', mock.key);
      list.append(card(`#exam/mock/${mock.key}`, paper.title, `${mock.duration_minutes} min · ${mock.points} points`, paperSummary(paper, store)));
    }
    root.append(append(node('section', 'exam-section'), node('h2', '', 'Forecast practice exams'),
      node('p', 'small', 'Written for this course from its past patterns and material, with new variants and topics past papers left out. Not past or leaked exams.'), list));
  }
  if (!papers.length && !exam.mocks.length) root.append(node('p', '', 'Practice exams have not been prepared yet.'));
  return { root, heading, title: 'Practice exams', items: [] };
}

function paperOverview(variantKey) {
  const paper = paperFor('paper', variantKey);
  if (!paper) return null;
  const { box, heading } = header(paper.title, 'Past paper');
  const root = node('div', 'exam-paper'); root.append(box);
  const modes = node('ul', 'exam-cards');
  modes.append(card(`#exam/paper/${variantKey}/${paper.questions[0].key}`, 'Guided', 'One question at a time, with hints, checks and solutions'));
  modes.append(card(`#exam/paper/${variantKey}/exam`, 'Exam conditions', paper.minutes ? `${paper.minutes} minutes, no hints` : 'No hints until you finish', paperSummary(paper, store)));
  root.append(modes);
  const list = node('ol', 'exam-paper-questions');
  for (const question of paper.questions) {
    const state = guided.get(guidedExercise(paper, question)).steps;
    const done = Object.values(state).some(step => step.checked !== null || step.compared);
    list.append(append(node('li'), quietLink(`Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`, `#exam/paper/${variantKey}/${question.key}`), node('span', 'small', done ? ' · started' : '')));
  }
  root.append(append(node('section', 'exam-section'), node('h2', '', 'Questions'), list));
  return { root, heading, title: paper.title, items: [] };
}

// A past question becomes an exercise: its guidance, or its solution as a single step.
function guidedExercise(paper, question) {
  const steps = question.guidance?.steps?.length ? question.guidance.steps
    : [{ key: 'solve', purpose: 'Solve', prompt: 'Solve the question, then compare with the solution.', hints: [], explanation: 'Compare your answer with the solution below.', check: question.check || null, blocks: [] }];
  return {
    key: question.key, label: `Question ${question.number}`, title: `Question ${question.number}`,
    revision: paper.revision, statement: question.statement, parts: [], objectives: question.guidance?.objectives || [],
    prerequisites: question.guidance?.prerequisites || [], steps, solution: question.solution, transfer: question.guidance?.transfer,
    sources: paper.sitting.variants.find(variant => variant.key === paper.key).sources.map(source => ({ key: source.key })),
  };
}

function guidedQuestion(variantKey, questionKey, stepKey, changed) {
  const paper = paperFor('paper', variantKey);
  const index = paper?.questions.findIndex(question => question.key === questionKey) ?? -1;
  if (index < 0) return null;
  const question = paper.questions[index], following = paper.questions[index + 1];
  const exercise = guidedExercise(paper, question);
  const page = exercisePage(exercise, {
    state: guided, changed, stepKey,
    eyebrow: `${paper.title} · Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`,
    link: step => `#exam/paper/${variantKey}/${question.key}/${step}`,
    annotate: (element, field, step) => annotateExam(element, `question:${question.key}`, paper.revision, step ? `${step}:${field}` : field),
    comment: root => renderCommentedView({ key: question.key, revision: paper.revision, title: exercise.title, items: [`question:${question.key}`] }, 'exam', root).root,
    onward: following ? { href: `#exam/paper/${variantKey}/${following.key}`, title: `Question ${following.number}`, detail: paper.title }
      : { href: `#exam/paper/${variantKey}/exam`, title: 'Take this paper under exam conditions', detail: paper.title },
  });
  return { ...page, items: [`question:${question.key}`] };
}

export function renderExam(hash, read, write, changed) {
  store ||= examStore(read, write);
  guided ||= exerciseState(read, write, `${examPrefix}guided:`);
  const [, section, key, part, step] = hash.split('/').map(decode);
  let page = null;
  if (!section) page = home();
  else if (section === 'sheet') page = renderSheet(key, store);
  else if (section === 'patterns') page = key ? renderPattern(key) : renderPatternList();
  else if (section === 'practice') page = practice();
  else if (section === 'mock') { const paper = paperFor('mock', key); page = paper && renderExamMode(paper, store); }
  else if (section === 'paper') {
    if (!part) page = paperOverview(key);
    else if (part === 'exam') { const paper = paperFor('paper', key); page = paper && renderExamMode(paper, store); }
    else page = guidedQuestion(key, part, step, changed);
  }
  if (!page) {
    page = home();
    page.root.prepend(node('p', 'notice', 'That page is no longer here. Choose a section below.'));
  }
  const root = page.navigateStep ? page.root : renderCommentedView({ key: section || 'home', title: page.title, items: page.items || [] }, 'exam', page.root).root;
  return { ...page, root, current: section || '' };
}

export function examOutline(current = '') {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Exam Prep');
  const entries = [['', 'Overview', '#exam'], ['sheet', 'Cheatsheet', '#exam/sheet'], ['patterns', 'Exam patterns', '#exam/patterns'], ['practice', 'Practice exams', '#exam/practice']];
  for (const [key, label, href] of entries) {
    if ((key === 'sheet' && !exam.concepts.length) || (key === 'patterns' && !exam.patterns.length) || (key === 'practice' && !replayable().length && !exam.mocks.length)) continue;
    const link = quietLink('', href, 'unit-link'); link.append(node('span', 'unit-title', label));
    if (key === current || (key === 'practice' && ['paper', 'mock'].includes(current))) link.setAttribute('aria-current', 'page');
    nav.append(link);
  }
  return nav;
}
