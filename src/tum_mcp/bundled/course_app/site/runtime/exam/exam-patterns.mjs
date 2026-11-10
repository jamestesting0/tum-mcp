import data from '../../data.mjs';
import { node, studyText, button, append, sourcesNote, pageCitation, shareCitations, plainText, shuffled, pillPanel, scrollReadingTo } from '../shell/dom.mjs';
import { renderBlockBody, renderAnswers, pitfallItem } from '../reading/reading.mjs';
import { renderResponse, optionExplanations, expectedAnswer } from '../exercises/exercise-response.mjs';
import { annotateExam } from '../comments/anchors.mjs';
import { codeReferences, filesIn } from '../shell/files.mjs';
import { exam, patterns, pastQuestions, seen, list } from './exam-state.mjs';
import { examRecall } from '../study/recall.mjs';
import { fitMath, texElement } from '../reading/mathml.mjs';
import { renderCode } from '../reading/code.mjs';
import { withMeanings } from '../reading/symbols.mjs';
import { iconButton, arrowPaging, cycleIndex } from '../shell/navigation.mjs';

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
// A choice is checked; every other item is compared with its answer at will. A hint sits
// beside Check or Compare in one row, as in an Exercises step.
function answerControls(check, identity, answer, expected = true, shown = [], hintText = '') {
  const feedback = node('div', 'exercise-feedback'); feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
  const response = renderResponse(check, '', () => feedback.replaceChildren(), identity, shown);
  const hints = node('div', 'exercise-hints stack'), actions = node('div', 'cluster exercise-actions');
  // The hint's place joins the step only when it is asked for.
  const hint = hintText && button('Hint', () => { hints.replaceChildren(studyText('p', '', hintText)); actions.before(hints); hint.hidden = true; }, 'secondary');
  if (check?.kind === 'choice') {
    actions.append(button('Check', () => {
      const result = response.validate();
      if (!result.valid) { feedback.replaceChildren(node('p', 'small', 'Choose an answer first.')); return; }
      response.showResult(true);
      // The same verdict as Practice and a Guide: the chosen option's feedback, the answer, then Explain.
      feedback.replaceChildren(append(node('section', `feedback${result.correct ? '' : ' incorrect'}`), node('h3', '', result.correct ? 'Correct' : 'Not quite'),
        ...result.repairs.map(text => studyText('p', '', text)), answer, optionExplanations(shuffled(check.options, identity), check.correct, result.chosen)));
    }, 'primary'));
  } else {
    // Compare reveals the same Answer box as an Exercises step.
    const revealed = append(node('section', 'feedback compare'), node('h3', '', 'Answer'));
    if (check && expected) revealed.append(expectedAnswer(check));
    revealed.append(answer);
    const compare = button('Compare', () => {
      const open = feedback.firstChild !== revealed;
      feedback.replaceChildren(...(open ? [revealed] : []));
      compare.setAttribute('aria-expanded', String(open));
    }, 'primary');
    compare.setAttribute('aria-expanded', 'false');
    actions.append(compare);
  }
  if (hint) actions.append(hint);
  return [response.root, feedback, actions];
}

function solutionPanel(...content) {
  return pillPanel('Solution', [{ value: 'solution', label: 'Solution', content: append(node('div'), ...content) }]).element;
}

function drillGuide(item, pattern) {
  const panel = node('div', 'exam-drill-guide');
  const cards = item.guide.map((step, index) => guidedCard(pattern, step, `drill:${item.key}:${index}`, index, item.guide.length, filesIn(item.blocks || [])));
  let index = 0;
  const prev = iconButton('Previous step', 'left', () => show(index - 1));
  const next = iconButton('Next step', 'right', () => show(index + 1));
  const count = node('span', 'small');
  panel.append(append(node('ol', 'exam-guided'), ...cards), append(node('div', 'diagram-controls'), prev, count, next));
  arrowPaging(panel, prev, next);
  function show(position) {
    index = cycleIndex(position, cards.length);
    cards.forEach((card, at) => { card.hidden = at !== index; });
    prev.disabled = next.disabled = cards.length < 2;
    count.textContent = `Step ${index + 1} of ${cards.length}`;
  }
  show(0);
  return panel;
}

// The complete task is attempted first; prepared help opens only on request.
function drillItem(item, pattern) {
  const root = node('div', 'exam-drill-item'), identity = `drill-${pattern.key}-${item.key}`;
  root.append(annotateExam(studyText('p', 'exam-drill-prompt', item.prompt), `pattern:${pattern.key}`, pattern.revision, `drill:${item.key}`));
  if (item.blocks?.length) root.append(blocksWithoutTitles(item.blocks));
  const explanation = studyText('p', '', item.explanation), worked = item.solution?.length ? [blocksWithoutTitles(item.solution)] : [];
  if (item.guide?.length) {
    if (item.check?.kind === 'choice') root.append(...answerControls(item.check, identity, studyText('p', '', item.explanation)));
    else root.append(renderResponse(item.check, '', () => {}, identity).root);
    const solution = append(node('div'), ...(item.check ? [expectedAnswer(item.check)] : []), explanation, ...worked);
    root.append(pillPanel('Help', [
      { value: 'guide', label: 'Guide', content: drillGuide(item, pattern) },
      { value: 'solution', label: 'Solution', content: solution },
    ]).element);
    return root;
  }
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
const lineIdentity = text => (text || '').trim().replace(/\s+/g, ' ').replace(/[.;:!?]+$/u, '').toLowerCase();
function applyPanel(apply, summary) {
  const panel = node('div', 'disclosure-panel apply-panel');
  if (apply.text && lineIdentity(apply.text) !== lineIdentity(summary)) panel.append(studyText('p', 'apply-text', apply.text));
  const seen = new Set();
  for (const latex of apply.math || []) {
    const math = append(node('div', 'apply-math'), texElement(latex, { display: true, symbols: (apply.symbols || []).map(item => item.symbol), seen }) || node('code', '', latex));
    fitMath(math); panel.append(withMeanings(math, apply.symbols || [], latex));
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
  if (!apply || (!apply.math?.length && !apply.code && lineIdentity(apply.text) === lineIdentity(text))) return studyText(tag, className, text);
  const details = node('details', `workflow-apply ${className}`);
  details.append(append(node('summary'), withChevron(studyText('span', '', text))), applyPanel(apply, text));
  return details;
}

// The workflow as numbered steps, each opening what it applies; the cheatsheet entry of a
// concept the pattern uses shows the same steps.
const workflowId = (pattern, number) => `workflow-${pattern.key}-${number}`;
export function workflowSteps(pattern, mark = element => element, linked = false) {
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
    // Only the pattern page's own workflow is the target of its step links; copies elsewhere
    // (cheatsheet entries) carry no id, so ids stay unique.
    const item = append(node('li'), body); if (linked) item.id = workflowId(pattern, index + 1);
    steps.append(mark(item, `step:${index}`));
  });
  return steps;
}

function workflowSection(pattern, mark) {
  return section('Workflow', workflowSteps(pattern, mark, true));
}

// Each pitfall opens with the task moment it happens in, then the wrong working, its
// correction and why the wrong one fails.
function pitfallsSection(pattern, mark) {
  const rows = pattern.pitfalls.map((pitfall, index) => {
    return mark(pitfallItem(pitfall), `pitfall:${index}`);
  });
  return section('Pitfalls', append(node('ul', 'pitfalls'), ...rows));
}

// One step of a worked example. On a decision step it asks which case applies, with the
// workflow's own cases as the options.
function guidedCard(pattern, step, field, position, total, shownFiles) {
  const card = node('li', 'exam-guided-step');
  // The header only counts; the step number leads to the workflow step it applies.
  const label = button(`Step ${position + 1} of ${total}`, () => {
    const target = document.getElementById(workflowId(pattern, step.step));
    if (!target) return;
    scrollReadingTo(target); target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash');
  }, 'exam-guided-number');
  label.title = `Workflow step ${step.step}`;
  card.append(append(node('p', 'exam-guided-label'), label));
  card.append(annotateExam(studyText('p', 'exam-guided-prompt', step.prompt), `pattern:${pattern.key}`, pattern.revision, `practice:${field}`));
  if (step.code?.length) card.append(codeReferences(step.code, shownFiles));
  const check = step.case ? {
    kind: 'choice', correct: `case-${step.case}`,
    options: pattern.workflow[step.step - 1].cases.map((item, index) => ({ key: `case-${index + 1}`, text: item.when, feedback: step.case_feedback[index] })),
  } : step.check;
  card.append(...answerControls(check, `practice-${pattern.key}-${field}`, blocksWithoutTitles(step.answer), check?.kind !== 'self_check', (step.code || []).map(ref => ref.path), step.hint || ''));
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
  root.dataset.patternTarget = 'worked';
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
  // A frequency means something only across several exams; one exam is listed in the table.
  if (stats.sittings_considered > 1) header.append(node('p', 'small exam-badge', seen(stats)));
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
  if (pattern.drill?.length) {
    const practice = section('Practise', ...pattern.drill.map(drill => drillItem(drill, pattern)));
    practice.dataset.patternTarget = 'practise';
    root.append(practice);
  }
  if (stats.instances.length) {
    const table = node('table', 'exam-instances'), head = node('tr');
    for (const title of ['Exam', 'Question', 'Points']) { const th = node('th', '', title); th.scope = 'col'; head.append(th); }
    table.append(append(node('thead'), head));
    const body = node('tbody');
    for (const instance of stats.instances) {
      const row = node('tr'), number = node('td');
      // A stored question opens in its paper, so a past instance is practised where it was asked.
      if (instance.stored) { const link = node('a', '', instance.number); link.href = `#exam/paper/${encodeURIComponent(instance.paper)}/${encodeURIComponent(instance.question)}`; number.append(link); }
      else number.textContent = instance.number;
      row.append(node('td', '', `${instance.label}${instance.variant && instance.variant !== instance.label ? ` · ${instance.variant}` : ''}`), number,
        node('td', '', instance.points == null ? '–' : String(instance.points)));
      body.append(row);
    }
    table.append(body);
    const region = append(node('div', 'table-region'), table); region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Past questions of this pattern');
    root.append(section('In past exams', region));
  }
  shareCitations(root, eyebrow);
  return { root, heading, title: plain(pattern.title), items: [item] };
}
