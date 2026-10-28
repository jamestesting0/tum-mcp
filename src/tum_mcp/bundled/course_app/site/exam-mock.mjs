import data from './data.mjs';
import { node, studyText, append, sourcesNote } from './dom.mjs';
import { renderBlockBody } from './reading.mjs';
import { annotateExam } from './anchors.mjs';
import { exam } from './exam-state.mjs';

const plain = text => studyText('span', '', text || '').textContent;

// A paper is either a forecast practice exam or a replayed past variant, in one shape.
export function paperFor(kind, key) {
  if (kind === 'mock') {
    const mock = exam.mocks.find(item => item.key === key);
    return mock && { kind, key, revision: mock.revision, title: plain(mock.title), minutes: mock.duration_minutes, instructions: mock.instructions,
      forecast: true, questions: mock.questions, item: `mock:${mock.key}` };
  }
  for (const sitting of exam.sittings) for (const variant of sitting.variants) if (variant.key === key && variant.replayable) {
    const label = sitting.variants.length > 1 ? `${plain(sitting.label)} · ${plain(variant.label)}` : plain(sitting.label);
    return { kind: 'paper', key, revision: variant.revision, title: label, minutes: exam.profile?.duration_minutes || null,
      instructions: '', forecast: false, questions: variant.questions, sitting };
  }
  return null;
}
const questionItem = (paper, question) => paper.kind === 'mock' ? paper.item : `question:${question.key}`;

// The question heading already names it, so statement block titles are not repeated.
function statementBody(blocks, mark = () => {}) {
  const root = node('div', 'exam-stem');
  blocks.forEach((block, index) => { const body = renderBlockBody(block); mark(body, index); root.append(body); });
  return root;
}

// The whole paper on one page; each solution opens when the student wants to check.
export function renderPaper(paper) {
  const root = node('div', 'exam-mode'), heading = node('h1', '', paper.title);
  const header = append(node('div', 'unit-header'), node('p', 'eyebrow', paper.forecast ? 'Practice exam' : 'Past exam'), heading);
  root.append(header);
  const total = paper.questions.reduce((sum, question) => sum + (question.points || 0), 0);
  const facts = [paper.minutes && `${paper.minutes} minutes`, total && `${total} points`, exam.profile?.allowed_aids].filter(Boolean);
  if (facts.length) header.append(studyText('p', 'small', facts.join(' · ')));
  if (paper.forecast) header.append(node('p', 'notice', 'AI-written practice exam built from past patterns and course material. It is not a past or leaked exam, and topics can differ in the real exam.'));
  if (paper.instructions) header.append(studyText('p', '', paper.instructions));
  header.append(node('p', 'small', 'Work on paper first, then open each solution to check yourself.'));
  for (const question of paper.questions) {
    const section = node('section', 'exam-section exam-question'); section.dataset.question = question.key;
    const title = `Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`;
    // One citation per question, covering its statement and solution.
    const cited = [...new Set([...question.statement, ...question.solution.blocks].flatMap(block => block.sources))];
    section.append(append(node('div', 'section-heading'), node('h2', '', title), sourcesNote(cited, data.sources, data.course.synthetic, title)));
    section.append(statementBody(question.statement, (element, index) => annotateExam(element, questionItem(paper, question), paper.revision, `${question.key}:statement:${index}`)));
    if (question.parts?.length) section.append(append(node('ol', 'exam-parts'), ...question.parts.map(text => studyText('li', '', text))));
    const solution = node('details', 'disclosure exam-solution');
    solution.append(node('summary', '', 'Solution'), statementBody(question.solution.blocks));
    if (question.marking?.length) {
      solution.append(node('p', 'small', question.marking_basis === 'official' ? 'Official marking' : 'Where the marks are'),
        append(node('ul', 'exam-marking'), ...question.marking.map(item => studyText('li', '', `${item.text} (${item.points})`))));
    }
    section.append(solution);
    root.append(section);
  }
  return { root, heading, title: paper.title, items: paper.kind === 'mock' ? [paper.item] : paper.questions.map(question => `question:${question.key}`) };
}
