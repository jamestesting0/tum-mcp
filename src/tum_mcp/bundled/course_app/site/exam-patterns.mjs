import data from './data.mjs';
import { node, studyText, button, append, sourcesNote, pageCitation, shareCitations, plainText } from './dom.mjs';
import { renderBlockBody, renderAnswers } from './reading.mjs';
import { renderResponse, optionExplanations, expectedAnswer } from './exercise-response.mjs';
import { annotateExam } from './anchors.mjs';
import { codeReferences, filesIn } from './files.mjs';
import { exam, patterns, concepts, pastQuestions, seen, sample, list, quietLink } from './exam-state.mjs';

const plain = text => plainText(text || '');

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
// An optional check, and the answer whenever the student wants it.
// A choice is checked; every other item is compared with its answer at will.
function answerControls(check, identity, answer, expected = true, shown = []) {
  const feedback = node('div', 'exercise-feedback'); feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
  const response = renderResponse(check, '', () => feedback.replaceChildren(), identity, shown);
  if (check?.kind === 'choice') {
    const actions = append(node('div', 'cluster exercise-actions'), button('Check answer', () => {
      const result = response.validate();
      if (!result.valid) { feedback.replaceChildren(node('p', 'small', 'Choose an answer first.')); return; }
      response.showResult(true);
      feedback.replaceChildren(append(node('section', `feedback${result.correct ? '' : ' incorrect'}`), node('h3', '', result.correct ? 'Correct' : 'Not quite'),
        ...(result.correct ? [] : result.repairs.map(text => studyText('p', '', text))), answer), optionExplanations(check, identity));
    }, 'primary'));
    return [response.root, actions, feedback];
  }
  const compare = node('details', 'disclosure exam-answer'); compare.append(node('summary', '', 'Compare'));
  if (check && expected) compare.append(expectedAnswer(check));
  compare.append(answer);
  return [response.root, compare];
}

function drillItem(item, pattern) {
  const root = node('div', 'exam-drill-item');
  root.append(annotateExam(studyText('p', 'exam-drill-prompt', item.prompt), `pattern:${pattern.key}`, pattern.revision, `drill:${item.key}`));
  if (item.blocks?.length) root.append(blocksWithoutTitles(item.blocks));
  root.append(...answerControls(item.check, `drill-${pattern.key}-${item.key}`, studyText('p', '', item.explanation)));
  return root;
}

// The pattern's workflow applied to one question, one labelled step per move.
function workedPractice(pattern) {
  const example = pattern.example, past = example.question && pastQuestions.get(example.question);
  const blocks = past ? past.question.statement : example.blocks, solution = past ? past.question.solution : example.solution;
  const steps = node('ol', 'exam-guided'), shownFiles = filesIn(blocks);
  example.steps.forEach((step, index) => {
    const card = node('li', 'exam-guided-step');
    card.append(append(node('p', 'exam-guided-label'), node('span', 'exam-guided-number', `Step ${step.step}`), studyText('span', '', pattern.workflow[step.step - 1].do)));
    card.append(annotateExam(studyText('p', 'exam-guided-prompt', step.prompt), `pattern:${pattern.key}`, pattern.revision, `practice:${index}`));
    if (step.code?.length) card.append(codeReferences(step.code, shownFiles));
    if (step.hint) { const hint = node('details', 'disclosure plain'); hint.append(node('summary', '', 'Hint'), studyText('p', '', step.hint)); card.append(hint); }
    card.append(...answerControls(step.check, `practice-${pattern.key}-${index}`, blocksWithoutTitles(step.answer), step.check?.kind !== 'self_check', (step.code || []).map(ref => ref.path)));
    steps.append(card);
  });
  const full = node('details', 'disclosure');
  full.append(node('summary', '', 'Full solution'), renderAnswers(solution));
  return section('Worked practice', ...(past ? [node('p', 'small', `From ${plain(past.sitting.label)}, question ${past.question.number}`)] : []), blocksWithoutTitles(blocks), steps, full);
}

export function renderPattern(key) {
  const pattern = patterns.get(key);
  if (!pattern) return null;
  const item = `pattern:${pattern.key}`, mark = (element, field) => annotateExam(element, item, pattern.revision, field);
  const stats = exam.statistics.patterns[pattern.key];
  const root = node('div', 'exam-pattern');
  const heading = studyText('h1', '', pattern.title);
  const eyebrow = node('p', 'eyebrow', 'Exam pattern');
  const header = append(node('div', 'unit-header'), eyebrow, heading, mark(studyText('p', 'unit-summary', pattern.summary), 'summary'));
  // Past-exam evidence appears only when there is some; the citation says where the pattern comes from.
  if (stats.sittings_considered) header.append(append(node('p', 'small exam-badge'), seen(stats), sample(stats) ? ` · ${sample(stats)}` : ''));
  root.append(header);
  const cited = sourcesNote(pattern.sources.map(source => source.key), data.sources, data.course.synthetic, pattern.title);
  pageCitation(cited, eyebrow); root.dataset.citations = cited.dataset.sources;
  root.append(section('Recognise it', mark(list('exam-cues', pattern.cues), 'cues')));
  const steps = node('ol', 'exam-workflow');
  pattern.workflow.forEach((step, index) => {
    const row = mark(append(node('li'), studyText('span', '', step.do)), `step:${index}`);
    if (step.why) { const why = node('details', 'disclosure plain'); why.append(node('summary', '', 'Why'), studyText('p', '', step.why)); row.append(why); }
    steps.append(row);
  });
  root.append(section('Workflow', steps));
  if (pattern.template?.length) root.append(section('Answer template', mark(blocksWithoutTitles(pattern.template), 'template')));
  if (pattern.marking?.length) root.append(section('Where the marks are', mark(list('', pattern.marking), 'marking')));
  if (pattern.pitfalls?.length) root.append(section('Pitfalls', mark(list('', pattern.pitfalls), 'pitfalls')));
  root.append(workedPractice(pattern));
  if (pattern.variations?.length) root.append(section('How it varied', mark(list('', pattern.variations), 'variations')));
  if (pattern.drill?.length) root.append(section('Practise', ...pattern.drill.map(drill => drillItem(drill, pattern))));
  const related = pattern.concepts.map(key => concepts.get(key)).filter(Boolean);
  if (related.length) {
    const links = node('p', 'small');
    related.forEach((concept, index) => { if (index) links.append(' · '); links.append(quietLink(plain(concept.title), `#exam/sheet/${concept.key}`)); });
    // The Study topics behind these entries, where the ideas are taught step by step.
    for (const unit of data.units.filter(item => related.some(concept => (concept.units || []).includes(item.key)))) {
      links.append(' · ', quietLink(`Study: ${plain(unit.title)}`, `#study/${unit.key}/content`));
    }
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
  shareCitations(root, eyebrow);
  return { root, heading, title: plain(pattern.title), items: [item] };
}
