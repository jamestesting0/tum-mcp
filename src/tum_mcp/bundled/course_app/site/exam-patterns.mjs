import data from './data.mjs';
import { node, studyText, button, append, sourcesNote } from './dom.mjs';
import { renderReading, renderBlockBody } from './reading.mjs';
import { renderResponse } from './exercise-response.mjs';
import { annotateExam } from './anchors.mjs';
import { exam, patterns, concepts, pastQuestions, seen, sample, list, quietLink } from './exam-state.mjs';

const ordered = (exam.statistics.pattern_order || []).map(key => patterns.get(key)).filter(Boolean);
const plain = text => studyText('span', '', text || '').textContent;

function section(title, ...children) {
  const element = node('section', 'exam-section');
  element.append(studyText('h2', '', title), ...children);
  return element;
}
function blocksWithoutTitles(blocks) {
  const root = node('div', 'exam-stem');
  for (const block of blocks) root.append(renderBlockBody(block));
  return root;
}
// One deterministic answer check with feedback; paper work is always fine.
function drillItem(item, pattern) {
  const root = node('div', 'exam-drill-item');
  root.append(annotateExam(studyText('p', 'exam-drill-prompt', item.prompt), `pattern:${pattern.key}`, pattern.revision, `drill:${item.key}`));
  if (item.blocks?.length) root.append(renderReading({ blocks: item.blocks }));
  const feedback = node('div', 'exercise-feedback'); feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
  let draft = '';
  const response = renderResponse(item.check, draft, value => { draft = value; feedback.replaceChildren(); }, `drill-${pattern.key}-${item.key}`);
  const reveal = () => feedback.replaceChildren(append(node('section', 'feedback'), node('h3', '', 'Explanation'), studyText('p', '', item.explanation)));
  const action = button(item.check ? (item.check.kind === 'self_check' ? 'Compare' : 'Check answer') : 'Show explanation', () => {
    if (!item.check || item.check.kind === 'self_check') { reveal(); return; }
    const result = response.validate();
    if (!result.valid) { feedback.replaceChildren(node('p', 'small', 'Answer first, then check.')); return; }
    response.showResult(true);
    feedback.replaceChildren(append(node('section', `feedback${result.correct ? '' : ' incorrect'}`), node('h3', '', result.correct ? 'Correct' : 'Not quite'),
      ...(result.correct ? [studyText('p', '', item.explanation)] : result.repairs.map(text => studyText('p', '', text)))));
  }, 'primary');
  root.append(response.root, append(node('div', 'cluster exercise-actions'), action), feedback);
  return root;
}

function recognitionDrill() {
  const pool = [...pastQuestions.values()].filter(({ question }) => (question.status ?? 'classified') === 'classified' && question.statement?.length && patterns.has(question.patterns?.[0]));
  if (!pool.length || ordered.length < 2) return null;
  const root = node('section', 'exam-section exam-recognition'); root.append(node('h2', '', 'Which pattern is this?'));
  root.append(node('p', 'small', 'Real past questions, without their titles. Name the pattern before solving.'));
  const body = node('div'); root.append(body);
  let index = 0;
  function show() {
    const { sitting, question } = pool[index % pool.length], answer = patterns.get(question.patterns[0]);
    const others = ordered.filter(item => item !== answer).sort((a, b) => (b.topic === answer.topic) - (a.topic === answer.topic) || a.key.localeCompare(b.key)).slice(0, 3);
    const options = [answer, ...others].sort((a, b) => plain(a.title).localeCompare(plain(b.title)));
    const choices = node('fieldset', 'exercise-choices'); choices.append(node('legend', 'small', `${sitting.label}, question ${question.number}`));
    const feedback = node('div', 'exercise-feedback'); feedback.setAttribute('role', 'status');
    for (const option of options) {
      const label = node('label', 'option'), input = node('input'); input.type = 'radio'; input.name = 'recognition'; input.value = option.key;
      input.addEventListener('change', () => {
        const right = option === answer;
        feedback.replaceChildren(append(node('section', `feedback${right ? '' : ' incorrect'}`), node('h3', '', right ? 'Correct' : 'Not quite'),
          append(node('p'), document.createTextNode(right ? 'Cues: ' : `This is “${plain(answer.title)}”. Cues: `), studyText('span', '', answer.cues.join('; '))),
          quietLink('Open the pattern', `#exam/patterns/${answer.key}`)));
      });
      label.append(input, studyText('span', 'option-body', option.title)); choices.append(label);
    }
    const next = button('Next question', () => { index++; show(); next.focus(); }, 'secondary');
    next.hidden = pool.length < 2;
    body.replaceChildren(blocksWithoutTitles(question.statement), choices, feedback, next);
  }
  show();
  return root;
}

export function renderPatternList() {
  const root = node('div', 'exam-patterns');
  const heading = node('h1', '', 'Exam patterns');
  root.append(append(node('div', 'unit-header'), node('p', 'eyebrow', 'Exam Prep'), heading,
    node('p', 'unit-summary', 'Recurring question types from past exams, each with a workflow that solves them. Ordered by how often and how recently they appeared.')));
  if (!ordered.length) { root.append(node('p', '', 'Exam patterns have not been prepared yet.')); return { root, heading, title: 'Exam patterns', items: [] }; }
  const note = sample(exam.statistics.patterns[ordered[0].key]);
  if (note) root.append(node('p', 'notice', `${note}: treat the order as a rough guide and study every core topic.`));
  const listing = node('ol', 'exam-pattern-list');
  for (const pattern of ordered) {
    const stats = exam.statistics.patterns[pattern.key];
    const link = node('a', 'unit-link'); link.href = `#exam/patterns/${pattern.key}`;
    link.append(studyText('span', 'unit-title', pattern.title), studyText('span', 'small', pattern.summary), node('span', 'small exam-badge', seen(stats)));
    listing.append(append(node('li'), link));
  }
  root.append(listing);
  const drill = recognitionDrill(); if (drill) root.append(drill);
  return { root, heading, title: 'Exam patterns', items: [] };
}

export function renderPattern(key) {
  const pattern = patterns.get(key);
  if (!pattern) return null;
  const item = `pattern:${pattern.key}`, mark = (element, field) => annotateExam(element, item, pattern.revision, field);
  const stats = exam.statistics.patterns[pattern.key];
  const root = node('div', 'exam-pattern');
  const heading = studyText('h1', '', pattern.title);
  const evidence = append(node('p', 'small exam-badge'), seen(stats), stats.sittings_considered && sample(stats) ? ` · ${sample(stats)}` : '');
  const header = append(node('div', 'unit-header'), node('p', 'eyebrow', 'Exam pattern'), heading, mark(studyText('p', 'unit-summary', pattern.summary), 'summary'),
    append(node('div', 'section-heading'), evidence, sourcesNote(pattern.sources.map(source => source.key), data.sources, data.course.synthetic, pattern.title)));
  root.append(header);
  root.append(section('Recognise it', mark(list('exam-cues', pattern.cues), 'cues')));
  const steps = node('ol', 'exam-workflow');
  pattern.workflow.forEach((step, index) => {
    const row = mark(append(node('li'), studyText('span', '', step.do)), `step:${index}`);
    if (step.why) { const why = node('details', 'disclosure plain'); why.append(node('summary', '', 'Why'), studyText('p', '', step.why)); row.append(why); }
    steps.append(row);
  });
  root.append(section('Workflow', steps));
  if (pattern.template?.length) root.append(section('Answer template', mark(blocksWithoutTitles(pattern.template), 'template')));
  if (pattern.marking?.length) root.append(section('Where the marks are', node('p', 'small', pattern.marking_basis === 'official' ? 'From official marking' : 'Inferred from solutions, not official'), mark(list('', pattern.marking), 'marking')));
  if (pattern.pitfalls?.length) root.append(section('Pitfalls', mark(list('', pattern.pitfalls), 'pitfalls')));
  if (pattern.example) {
    const past = pattern.example.question && pastQuestions.get(pattern.example.question);
    const blocks = past ? past.question.statement : pattern.example.blocks, solution = past ? past.question.solution : pattern.example.solution;
    const origin = past ? `${past.sitting.label}, question ${past.question.number}` : 'Authored example';
    const answer = node('details', 'disclosure'); answer.append(node('summary', '', solution.origin === 'official' ? 'Official solution' : 'Prepared solution, not official'), renderReading({ blocks: solution.blocks }));
    root.append(section('Worked example', node('p', 'small', origin), renderReading({ blocks }), answer));
  }
  if (pattern.variations?.length) root.append(section('How it varied', mark(list('', pattern.variations), 'variations')));
  if (pattern.drill?.length) root.append(section('Practise', ...pattern.drill.map(drill => drillItem(drill, pattern))));
  const related = pattern.concepts.map(key => concepts.get(key)).filter(Boolean);
  if (related.length) {
    const links = node('p', 'small');
    related.forEach((concept, index) => { if (index) links.append(' · '); links.append(quietLink(plain(concept.title), `#exam/sheet/${concept.key}`)); });
    root.append(section('Cheatsheet entries', links));
  }
  if (stats.instances.length) {
    const table = node('table', 'exam-instances'), head = node('tr');
    for (const title of ['Exam', 'Question', 'Points', 'Counted']) { const th = node('th', '', title); th.scope = 'col'; head.append(th); }
    table.append(append(node('thead'), head));
    const body = node('tbody');
    for (const instance of stats.instances) {
      const row = node('tr');
      row.append(node('td', '', `${instance.label}${instance.variant && instance.variant !== instance.label ? ` · ${instance.variant}` : ''}`), node('td', '', instance.number),
        node('td', '', instance.points == null ? '–' : String(instance.points)), node('td', '', instance.considered ? 'Yes' : 'No (older syllabus)'));
      body.append(row);
    }
    table.append(body);
    const region = append(node('div', 'table-region'), table); region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Past questions of this pattern');
    root.append(section('In past exams', region));
  }
  return { root, heading, title: plain(pattern.title), items: [item] };
}
