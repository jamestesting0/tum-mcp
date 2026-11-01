import data from './data.mjs';
import { node, studyText, button, append, sourcesNote, pageCitation, shareCitations, plainText, shuffled } from './dom.mjs';
import { renderBlockBody, renderAnswers } from './reading.mjs';
import { renderResponse, optionExplanations, expectedAnswer, answerMark } from './exercise-response.mjs';
import { annotateExam } from './anchors.mjs';
import { codeReferences, filesIn } from './files.mjs';
import { exam, patterns, pastQuestions, seen, sample, list } from './exam-state.mjs';
import { examRecall } from './recall.mjs';
import { fitMath, texElement } from './mathml.mjs';
import { renderCode } from './code.mjs';
import { withMeanings } from './symbols.mjs';

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
    const actions = append(node('div', 'cluster exercise-actions'), button('Check', () => {
      const result = response.validate();
      if (!result.valid) { feedback.replaceChildren(node('p', 'small', 'Choose an answer first.')); return; }
      response.showResult(true);
      // The same verdict as Practice and a Guide: the chosen option's feedback, the answer, then Explain.
      feedback.replaceChildren(append(node('section', `feedback${result.correct ? '' : ' incorrect'}`), node('h3', '', result.correct ? 'Correct' : 'Not quite'),
        ...result.repairs.map(text => studyText('p', '', text)), answer, optionExplanations(shuffled(check.options, identity), check.correct, result.chosen)));
    }, 'primary'));
    return [response.root, actions, feedback];
  }
  // Compare reveals the same Answer box as an Exercises step.
  const compare = node('details', 'disclosure answer-reveal'), revealed = append(node('section', 'feedback compare'), node('h3', '', 'Answer'));
  if (check && expected) revealed.append(expectedAnswer(check));
  revealed.append(answer);
  compare.append(node('summary', '', 'Compare'), revealed);
  return [response.root, compare];
}

function solutionPanel(...content) {
  const full = node('details', 'disclosure');
  full.append(node('summary', '', 'Solution'), append(node('div', 'disclosure-panel'), ...content));
  return full;
}

// Practice without steps. Every item is worked on paper and opens its Solution, like a
// Worked practice question; only a multiple choice is checked on screen.
function drillItem(item, pattern) {
  const root = node('div', 'exam-drill-item'), identity = `drill-${pattern.key}-${item.key}`;
  root.append(annotateExam(studyText('p', 'exam-drill-prompt', item.prompt), `pattern:${pattern.key}`, pattern.revision, `drill:${item.key}`));
  if (item.blocks?.length) root.append(blocksWithoutTitles(item.blocks));
  const explanation = studyText('p', '', item.explanation), worked = item.solution?.length ? [blocksWithoutTitles(item.solution)] : [];
  if (item.check?.kind === 'choice') {
    root.append(...answerControls(item.check, identity, explanation));
    if (worked.length) root.append(solutionPanel(...worked));
    return root;
  }
  // A code, table, graph or plot answer keeps its own input above the Solution.
  const response = renderResponse(item.check, '', () => {}, identity);
  root.append(response.root, solutionPanel(...(item.check ? [expectedAnswer(item.check)] : []), explanation, ...worked));
  return root;
}

// The workflow reads as a numbered procedure. A decision step lists its cases under it,
// what the student sees and the move it calls for, before the step's reason.
// What a step or case applies opens under it on a click: the rule, the formula, the code.
// Closed, the workflow reads as a procedure to recall; open, it shows exactly what to write.
function applyPanel(apply) {
  const panel = node('div', 'disclosure-panel apply-panel');
  if (apply.text) panel.append(studyText('p', 'apply-text', apply.text));
  const seen = new Set();
  for (const latex of apply.math || []) {
    const math = append(node('div', 'apply-math'), texElement(latex, { display: true, symbols: (apply.symbols || []).map(item => item.symbol), seen }) || node('code', '', latex));
    fitMath(math, 0.75); panel.append(withMeanings(math, apply.symbols || [], latex));
  }
  if (apply.code) panel.append(append(node('div', 'code-region apply-code'), renderCode(apply.code, apply.language)));
  return panel;
}

// The chevron stays on the line of the text's last word or formula.
function withChevron(element) {
  const chevron = node('span', 'apply-chevron'), tail = node('span', 'apply-tail');
  chevron.setAttribute('aria-hidden', 'true');
  let last = element.lastChild;
  while (last?.nodeType === Node.TEXT_NODE && !last.textContent.trim()) last = last.previousSibling;
  if (last?.nodeType === Node.TEXT_NODE) {
    const text = last.textContent.trimEnd(), at = text.search(/\S+$/);
    last.textContent = text.slice(0, at); tail.append(text.slice(at));
  } else if (last) tail.append(last);
  tail.append(chevron); element.append(tail);
  return element;
}

function applicable(tag, className, text, apply) {
  if (!apply) return studyText(tag, className, text);
  const details = node('details', `workflow-apply ${className}`);
  details.append(append(node('summary'), withChevron(studyText('span', '', text))), applyPanel(apply));
  return details;
}

function workflowSection(pattern, mark) {
  const steps = node('ol', 'exam-workflow');
  pattern.workflow.forEach((step, index) => {
    const body = append(node('div', 'workflow-body'), applicable('p', 'workflow-do', step.do, step.apply));
    if (step.cases?.length) {
      body.append(append(node('ul', 'workflow-cases'), ...step.cases.map(item => {
        const arrow = node('span', 'case-arrow', '→'); arrow.setAttribute('aria-hidden', 'true');
        return append(node('li'), studyText('span', 'case-when', item.when), arrow, applicable('span', 'case-then', item.then, item.apply));
      })));
    }
    if (step.why) body.append(studyText('p', 'workflow-why', step.why));
    steps.append(mark(append(node('li'), body), `step:${index}`));
  });
  return section('Workflow', steps);
}

// Each pitfall opens with the task moment it happens in, then the wrong working, its
// correction and why the wrong one fails.
function pitfallsSection(pattern, mark) {
  const line = (right, text) => append(node('p', `pitfall-line ${right ? 'right' : 'wrong'}`), answerMark(right), studyText('span', '', text));
  const rows = pattern.pitfalls.map((pitfall, index) => {
    const row = node('li', 'pitfall'), situation = studyText('p', 'pitfall-situation', pitfall.situation);
    if (pitfall.step) situation.prepend(node('span', 'pitfall-step', `Step ${pitfall.step}`), ' ');
    row.append(situation, line(false, pitfall.wrong), line(true, pitfall.right), studyText('p', 'pitfall-why', pitfall.why));
    return mark(row, `pitfall:${index}`);
  });
  return section('Pitfalls', append(node('ul', 'pitfalls'), ...rows));
}

// One step of a worked example. On a decision step it asks which case applies, with the
// workflow's own cases as the options.
function guidedCard(pattern, step, field, position, total, shownFiles) {
  const card = node('li', 'exam-guided-step');
  card.append(append(node('p', 'exam-guided-label'), node('span', 'exam-guided-number', `Step ${position + 1} of ${total}`), studyText('span', '', pattern.workflow[step.step - 1].do)));
  card.append(annotateExam(studyText('p', 'exam-guided-prompt', step.prompt), `pattern:${pattern.key}`, pattern.revision, `practice:${field}`));
  if (step.code?.length) card.append(codeReferences(step.code, shownFiles));
  if (step.hint) { const hint = node('details', 'disclosure plain'); hint.append(node('summary', '', 'Hint'), studyText('p', '', step.hint)); card.append(hint); }
  const check = step.case ? {
    kind: 'choice', correct: `case-${step.case}`,
    options: pattern.workflow[step.step - 1].cases.map((item, index) => ({ key: `case-${index + 1}`, text: item.when, feedback: step.case_feedback[index] })),
  } : step.check;
  card.append(...answerControls(check, `practice-${pattern.key}-${field}`, blocksWithoutTitles(step.answer), check?.kind !== 'self_check', (step.code || []).map(ref => ref.path)));
  return card;
}

// The pattern's workflow applied to a question, one labelled step per move. When the
// question has parts, each part runs the workflow and is numbered on its own.
function exampleView(pattern, example, number) {
  const past = example.question && pastQuestions.get(example.question);
  const blocks = past ? past.question.statement : example.blocks, solution = past ? past.question.solution : example.solution;
  const view = node('div', 'pattern-example'), shownFiles = filesIn(blocks), groups = [];
  if (past) view.append(node('p', 'small', `From ${plain(past.sitting.label)}, question ${past.question.number}`));
  view.append(blocksWithoutTitles(blocks));
  example.steps.forEach((step, index) => {
    if (!groups.length || groups.at(-1).part !== step.part) groups.push({ part: step.part, steps: [] });
    groups.at(-1).steps.push({ step, index });
  });
  for (const group of groups) {
    if (group.part) view.append(node('p', 'example-part', `(${group.part})`));
    view.append(append(node('ol', 'exam-guided'), ...group.steps.map(({ step, index }, position) =>
      guidedCard(pattern, step, `${number}:${index}`, position, group.steps.length, shownFiles))));
  }
  view.append(solutionPanel(renderAnswers(solution)));
  return view;
}

// Several examples sit behind neutral labels, one at a time, so a label never names the case.
function workedPractice(pattern) {
  const views = pattern.examples.map((example, number) => exampleView(pattern, example, number));
  const root = section('Worked practice');
  if (views.length > 1) {
    const switcher = node('div', 'example-switch'); switcher.setAttribute('role', 'group'); switcher.setAttribute('aria-label', 'Examples');
    const buttons = views.map((_, index) => button(`Example ${index + 1}`, () => show(index)));
    const show = shown => views.forEach((view, index) => { view.hidden = index !== shown; buttons[index].setAttribute('aria-pressed', String(index === shown)); });
    switcher.append(...buttons); root.append(switcher); show(0);
  }
  root.append(...views);
  return root;
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
  // The pattern is named already, so its concepts can be recalled before the student starts.
  const recall = examRecall(pattern.concepts);
  if (recall) header.append(recall);
  root.append(header);
  const cited = sourcesNote(pattern.sources.map(source => source.key), data.sources, data.course.synthetic, pattern.title);
  pageCitation(cited, eyebrow); root.dataset.citations = cited.dataset.sources;
  root.append(section('Recognise it', mark(list('exam-cues', pattern.cues), 'cues')));
  root.append(workflowSection(pattern, mark));
  if (pattern.marking?.length) root.append(section('Where the marks are', mark(list('', pattern.marking), 'marking')));
  if (pattern.pitfalls?.length) root.append(pitfallsSection(pattern, mark));
  root.append(workedPractice(pattern));
  if (pattern.variations?.length) root.append(section('How it varied', mark(list('', pattern.variations), 'variations')));
  if (pattern.drill?.length) root.append(section('Practise', ...pattern.drill.map(drill => drillItem(drill, pattern))));
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
