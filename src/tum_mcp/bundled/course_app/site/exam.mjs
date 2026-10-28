import data from './data.mjs';
import { node, studyText, append } from './dom.mjs';
import { renderCommentedView } from './comments.mjs';
import { annotateExam } from './anchors.mjs';
import { exerciseState } from './exercise-state.mjs';
import { exercisePage } from './exercises.mjs';
import { exam, examPrefix, variants, sample, quietLink } from './exam-state.mjs';
import { renderSheet } from './exam-sheet.mjs';
import { renderPattern } from './exam-patterns.mjs';
import { renderPaper, paperFor } from './exam-mock.mjs';

const decode = value => { try { return decodeURIComponent(value || ''); } catch { return ''; } };
let guided;

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
const orderedPatterns = () => (exam.statistics.pattern_order || []).map(key => exam.patterns.find(item => item.key === key)).filter(Boolean);
// The first practice paper: past papers before forecasts.
const firstPaper = () => { const past = replayable()[0]; return past ? `#exam/paper/${past.variant.key}` : exam.mocks[0] ? `#exam/mock/${exam.mocks[0].key}` : ''; };

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
  if (exam.concepts.length) cards.append(card('#exam/sheet', 'Cheatsheet', `${exam.concepts.length} entries${exam.map?.nodes?.length ? ' and a semester map' : ''}`));
  if (exam.patterns.length) cards.append(card(`#exam/patterns/${orderedPatterns()[0].key}`, 'Exam patterns', `${exam.patterns.length} recurring question types`, sample(stats.patterns[stats.pattern_order[0]])));
  const papers = replayable().length, mocks = exam.mocks.length;
  if (papers || mocks) cards.append(card(firstPaper(), 'Practice exams', [papers && `${papers} past paper${papers === 1 ? '' : 's'}`, mocks && `${mocks} practice exam${mocks === 1 ? '' : 's'}`].filter(Boolean).join(' · ')));
  root.append(cards);
  return { root, heading, title: 'Exam Prep', items: [] };
}

function paperOverview(variantKey) {
  const paper = paperFor('paper', variantKey);
  if (!paper) return null;
  const { box, heading } = header(paper.title, 'Past paper');
  const root = node('div', 'exam-paper'); root.append(box);
  const modes = node('ul', 'exam-cards');
  modes.append(card(`#exam/paper/${variantKey}/${paper.questions[0].key}`, 'Guided', 'One question at a time, with hints, checks and solutions'));
  modes.append(card(`#exam/paper/${variantKey}/exam`, 'Whole paper', 'Every question on one page, each with its solution'));
  root.append(modes);
  const list = node('ol', 'exam-paper-questions');
  for (const question of paper.questions) {
    list.append(append(node('li'), quietLink(`Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`, `#exam/paper/${variantKey}/${question.key}`)));
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

function guidedQuestion(variantKey, questionKey, stepKey) {
  const paper = paperFor('paper', variantKey);
  const index = paper?.questions.findIndex(question => question.key === questionKey) ?? -1;
  if (index < 0) return null;
  const question = paper.questions[index], following = paper.questions[index + 1];
  const exercise = guidedExercise(paper, question);
  const page = exercisePage(exercise, {
    state: guided, stepKey, untitledStatement: true,
    eyebrow: `${paper.title} · Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`,
    link: step => `#exam/paper/${variantKey}/${question.key}/${step}`,
    annotate: (element, field, step) => annotateExam(element, `question:${question.key}`, paper.revision, step ? `${step}:${field}` : field),
    comment: root => renderCommentedView({ key: question.key, revision: paper.revision, title: exercise.title, items: [`question:${question.key}`] }, 'exam', root).root,
    onward: following ? { href: `#exam/paper/${variantKey}/${following.key}`, title: `Question ${following.number}`, detail: paper.title }
      : { href: `#exam/paper/${variantKey}/exam`, title: 'See the whole paper', detail: paper.title },
  });
  return { ...page, items: [`question:${question.key}`] };
}

export function renderExam(hash, read, write) {
  guided ||= exerciseState(read, write, `${examPrefix}guided:`);
  const [, section, key, part, step] = hash.split('/').map(decode);
  let page = null;
  if (!section) page = home();
  else if (section === 'sheet') page = renderSheet(key);
  else if (section === 'patterns') page = renderPattern(key || orderedPatterns()[0]?.key);
  else if (section === 'mock') { const paper = paperFor('mock', key); page = paper && renderPaper(paper); }
  else if (section === 'paper') {
    if (!part) page = paperOverview(key);
    else if (part === 'exam') { const paper = paperFor('paper', key); page = paper && renderPaper(paper); }
    else page = guidedQuestion(key, part, step);
  }
  if (!page) {
    page = home();
    page.root.prepend(node('p', 'notice', 'That page is no longer here. Choose a section below.'));
  }
  const root = page.navigateStep ? page.root : renderCommentedView({ key: section || 'home', title: page.title, items: page.items || [] }, 'exam', page.root).root;
  return { ...page, root, current: section || '', currentKey: key || '' };
}

// The course title already opens the overview, so the outline lists only the sections;
// sections with pages of their own collapse into groups.
export function examOutline(current = '', currentKey = '') {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Exam Prep');
  const link = (label, href, active, detail = '') => {
    const item = quietLink('', href, 'unit-link'); item.append(studyText('span', 'unit-title', label));
    if (detail) item.append(node('span', 'small', detail));
    if (active) item.setAttribute('aria-current', 'page');
    return item;
  };
  const group = (title, open, children) => {
    const box = node('details', 'unit-group'); box.open = open;
    box.append(node('summary', '', title), append(node('div', 'group-children'), ...children));
    return box;
  };
  if (exam.concepts.length) nav.append(link('Cheatsheet', '#exam/sheet', current === 'sheet'));
  if (exam.patterns.length) {
    nav.append(group('Exam patterns', current === 'patterns', [
      ...orderedPatterns().map(pattern => link(pattern.title, `#exam/patterns/${pattern.key}`, current === 'patterns' && (currentKey || orderedPatterns()[0].key) === pattern.key)),
    ]));
  }
  const papers = replayable();
  if (papers.length || exam.mocks.length) {
    nav.append(group('Practice exams', ['paper', 'mock'].includes(current), [
      ...papers.map(({ variant }) => link(paperFor('paper', variant.key).title, `#exam/paper/${variant.key}`, current === 'paper' && currentKey === variant.key, 'Past paper')),
      ...exam.mocks.map(mock => link(paperFor('mock', mock.key).title, `#exam/mock/${mock.key}`, current === 'mock' && currentKey === mock.key, 'Forecast')),
    ]));
  }
  return nav;
}
