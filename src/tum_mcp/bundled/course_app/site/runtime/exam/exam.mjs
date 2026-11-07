import data from '../../data.mjs';
import { node, studyText, append, topicRow } from '../shell/dom.mjs';
import { renderCommentedView } from '../comments/comments.mjs';
import { annotateExam } from '../comments/anchors.mjs';
import { exerciseState } from '../exercises/exercise-state.mjs';
import { exercisePage, exerciseStarted } from '../exercises/exercises.mjs';
import { exam, examPrefix, variants, quietLink } from './exam-state.mjs';
import { renderSheet } from './exam-sheet.mjs';
import { renderPattern } from './exam-patterns.mjs';
import { renderPaper, paperFor } from './exam-mock.mjs';
import { nextStep, iconGlyph } from '../shell/navigation.mjs';
import { isCompleted } from '../shell/completion.mjs';
import { examRecall } from '../study/recall.mjs';

const decode = value => { try { return decodeURIComponent(value || ''); } catch { return ''; } };
let guided, store;
// Pages opened, so a pattern or paper the student has started reads as in progress.
const visitsKey = `${examPrefix}visited`;
const visited = () => { const value = store.read(visitsKey, {}); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; };
function visit(href) { const value = visited(); if (!value[href]) store.write(visitsKey, { ...value, [href]: true }); }

function header(title, eyebrow, summary) {
  const heading = studyText('h1', '', title);
  const box = append(node('div', 'unit-header'), node('p', 'eyebrow', eyebrow), heading);
  if (summary) box.append(studyText('p', 'unit-summary', summary));
  return { box, heading };
}
function card(href, title, detail) {
  const link = node('a', 'exam-card'); link.href = href;
  link.append(node('span', 'exam-card-title', title), node('span', 'small', detail));
  return append(node('li'), link);
}
const replayable = () => variants.filter(({ variant }) => variant.replayable);
const orderedPatterns = () => (exam.statistics.pattern_order || []).map(key => exam.patterns.find(item => item.key === key)).filter(Boolean);
// The first practice paper: past papers before forecasts.
const firstPaper = () => { const past = replayable()[0]; return past ? `#exam/paper/${past.variant.key}` : exam.mocks[0] ? `#exam/mock/${exam.mocks[0].key}` : ''; };
// Exam pages in reading order, as the outline lists them: cheatsheet, patterns, then papers.
function sequence() {
  return [
    ...(exam.concepts.length ? [{ href: '#exam/sheet', title: 'Cheatsheet', detail: `${exam.concepts.length} entries` }] : []),
    ...orderedPatterns().map(pattern => ({ href: `#exam/patterns/${pattern.key}`, title: pattern.title, detail: 'Exam pattern' })),
    ...replayable().map(({ variant }) => ({ href: `#exam/paper/${variant.key}`, title: paperFor('paper', variant.key).title, detail: 'Past paper' })),
    ...exam.mocks.map(mock => ({ href: `#exam/mock/${mock.key}`, title: paperFor('mock', mock.key).title, detail: 'Practice exam' })),
  ];
}
function onward(href) {
  const pages = sequence(), index = pages.findIndex(page => page.href === href);
  return index >= 0 && pages[index + 1] ? nextStep(pages[index + 1]) : null;
}

function home() {
  const { box, heading } = header('Exam', data.course.title);
  const root = node('div', 'exam-home'); root.append(box);
  const profile = exam.profile;
  if (profile) {
    const facts = node('dl', 'exam-profile');
    const add = (label, value) => facts.append(append(node('div'), node('dt', '', label), studyText('dd', '', value || 'Not stated')));
    add('Format', { written: 'Written exam', online: 'Online exam', programming: 'Programming exam', oral: 'Oral exam', mixed: 'Mixed format' }[profile.format]);
    add('Duration', profile.duration_minutes && `${profile.duration_minutes} minutes`);
    add('Total points', profile.total_points && String(profile.total_points));
    add('Allowed aids', profile.allowed_aids);
    if (profile.languages?.length) add(profile.languages.length === 1 ? 'Language' : 'Languages', profile.languages.join(', '));
    root.append(append(node('section', 'exam-section'), facts,
      ...(profile.notes ? [studyText('p', 'small exam-profile-note', profile.notes)] : [])));
  }
  const stats = exam.statistics;
  // The evidence line only appears when past exams exist; without them there is nothing to report.
  const years = stats.years?.length ? ` (${stats.years[0] === stats.years[1] ? stats.years[0] : `${stats.years[0]}–${stats.years[1]}`})` : '';
  if (stats.sittings_considered) root.append(node('p', 'small exam-evidence',
    `${stats.sittings_considered} past exam${stats.sittings_considered === 1 ? '' : 's'}${years}${stats.sittings_outdated ? `; ${stats.sittings_outdated} older one${stats.sittings_outdated === 1 ? '' : 's'} not counted` : ''}`));
  // The same rows as the Study and Exercises homes: each page with its status, and Continue.
  const seen = visited(), status = (href, started) => isCompleted(href) ? 'Done' : started || seen[href] ? 'In progress' : 'Not started';
  const groups = [];
  if (exam.concepts.length) groups.push({ title: '', rows: [{ href: '#exam/sheet', title: 'Cheatsheet', details: [`${exam.concepts.length} entries${exam.map?.edges?.length ? ' and a semester map' : ''}`] }] });
  if (exam.patterns.length) groups.push({ title: 'Exam patterns', rows: orderedPatterns().map(pattern => ({ href: `#exam/patterns/${pattern.key}`, title: pattern.title, details: [] })) });
  const practice = [
    ...replayable().map(({ variant }) => {
      const paper = paperFor('paper', variant.key);
      const started = paper.questions.some(question => question.guidance && exerciseStarted(guided.get(guidedExercise(paper, question))));
      return { href: `#exam/paper/${variant.key}`, title: paper.title, details: ['Past paper'], started };
    }),
    ...exam.mocks.map(mock => ({ href: `#exam/mock/${mock.key}`, title: paperFor('mock', mock.key).title, details: ['Practice exam'] })),
  ];
  if (practice.length) groups.push({ title: 'Practice exams', rows: practice });
  const rows = groups.flatMap(group => group.rows).map(row => ({ ...row, status: status(row.href, row.started) }));
  const empty = !rows.length;
  if (empty) { root.append(node('p', '', 'Exam has not been prepared for this course.')); return { root, heading, title: 'Exam', items: [], empty }; }
  const resume = rows.find(row => row.status === 'In progress') || rows.find(row => row.status === 'Not started');
  if (resume) {
    const go = node('a', 'button primary resume'); go.href = resume.href;
    go.append(iconGlyph('play'), node('span', 'visually-hidden', `${resume.status === 'In progress' ? 'Continue' : 'Start'}: `), studyText('span', '', resume.title));
    box.append(append(node('div', 'cluster home-actions'), go));
  }
  const list = node('section', 'home-topics exam-list'); list.setAttribute('aria-label', 'Exam');
  let index = 0;
  for (const group of groups) {
    if (group.title) list.append(studyText('h3', 'topic-group', group.title));
    list.append(append(node('ul', 'topic-list'), ...group.rows.map(() => { const row = rows[index++]; return topicRow(row.href, row.title, row.details, row.status); })));
  }
  root.append(list);
  return { root, heading, title: 'Exam', items: [], empty };
}

function paperOverview(variantKey) {
  const paper = paperFor('paper', variantKey);
  if (!paper) return null;
  const { box, heading } = header(paper.title, 'Past paper');
  const root = node('div', 'exam-paper'); root.append(box);
  const modes = node('ul', 'exam-cards');
  modes.append(card(`#exam/paper/${variantKey}/${paper.questions[0].key}`, paper.questions.every(question => question.guidance) ? 'Guide' : 'Questions', 'One question at a time'));
  modes.append(card(`#exam/paper/${variantKey}/exam`, 'Whole paper', 'All questions on one page'));
  root.append(modes);
  const list = node('ol', 'exam-paper-questions');
  for (const question of paper.questions) {
    list.append(append(node('li'), quietLink(`Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`, `#exam/paper/${variantKey}/${question.key}`)));
  }
  root.append(append(node('section', 'exam-section'), node('h2', '', 'Questions'), list));
  return { root, heading, title: paper.title, items: [] };
}

// A prepared past-question guide uses the same interaction as an exercise.
function guidedExercise(paper, question) {
  const steps = question.guidance.steps;
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
  if (!question.guidance) {
    const page = renderPaper({ ...paper, title: `${paper.title} · Question ${question.number}`, questions: [question] });
    page.root.querySelector('.unit-header').append(node('p', 'small', 'Guidance has not been prepared for this question.'));
    page.root.append(nextStep(following ? { href: `#exam/paper/${variantKey}/${following.key}`, title: `Question ${following.number}`, detail: paper.title }
      : { href: `#exam/paper/${variantKey}/exam`, title: 'See the whole paper', detail: paper.title }));
    return page;
  }
  const exercise = guidedExercise(paper, question);
  const page = exercisePage(exercise, {
    state: guided, stepKey, untitledStatement: true,
    eyebrow: `${paper.title} · Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`,
    link: step => `#exam/paper/${variantKey}/${question.key}/${step}`,
    annotate: (element, field, step) => annotateExam(element, `question:${question.key}`, paper.revision, step ? `${step}:${field}` : field),
    comment: root => renderCommentedView({ key: question.key, revision: paper.revision, title: exercise.title, items: [`question:${question.key}`] }, 'exam', root).root,
    // Recall waits behind the full solution: recognising the pattern is what the paper practises.
    afterSolution: examRecall(question.concepts || [], question.patterns || []),
    onward: following ? { href: `#exam/paper/${variantKey}/${following.key}`, title: `Question ${following.number}`, detail: paper.title }
      : { href: `#exam/paper/${variantKey}/exam`, title: 'See the whole paper', detail: paper.title },
  });
  return { ...page, items: [`question:${question.key}`] };
}

export function renderExam(hash, read, write) {
  guided ||= exerciseState(read, write, `${examPrefix}guided:`);
  store = { read, write };
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
    page.root.prepend(node('p', 'notice', 'That page is no longer here.'));
  }
  const here = { sheet: '#exam/sheet', patterns: `#exam/patterns/${key || orderedPatterns()[0]?.key}`, mock: `#exam/mock/${key}`, paper: `#exam/paper/${key}` }[section];
  if (here && section !== 'sheet') visit(here);
  const following = !page.navigateStep && here && onward(here);
  if (following) page.root.append(following);
  const root = page.navigateStep ? page.root : renderCommentedView({ key: section || 'home', title: page.title, items: page.items || [] }, 'exam', page.root).root;
  return { ...page, root, current: section || '', currentKey: key || '' };
}

// The course title already opens the overview, so the outline lists only the sections;
// sections with pages of their own collapse into groups.
export function examOutline(current = '', currentKey = '') {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Exam');
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
