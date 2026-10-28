import data from './data.mjs';
import { node, svgNode, studyText } from './dom.mjs';
import { parseMath } from './mathml.mjs';

export const exam = data.exam || { topics: [], sittings: [], concepts: [], links: [], patterns: [], mocks: [], statistics: { patterns: {}, concepts: {}, pattern_order: [] }, map: { nodes: [] } };
export const examPrefix = `course-exam:${data.course.identity}:`;
export const concepts = new Map(exam.concepts.map(item => [item.key, item]));
export const patterns = new Map(exam.patterns.map(item => [item.key, item]));
export const topics = [...exam.topics].sort((a, b) => a.order - b.order || a.key.localeCompare(b.key));
export const variants = exam.sittings.flatMap(sitting => sitting.variants.map(variant => ({ sitting, variant })));
export const pastQuestions = new Map(variants.flatMap(({ sitting, variant }) => variant.questions.map(question => [question.key, { sitting, variant, question }])));

export function seen(statistics) {
  if (!statistics?.sittings_considered) return 'No current past exams';
  const base = `Seen in ${statistics.sittings_seen} of ${statistics.sittings_considered} exams`;
  return statistics.last_label ? `${base} · last ${statistics.last_label}` : base;
}
// Small samples are stated plainly; a frequency is history, never a prediction.
export function sample(statistics) {
  const count = statistics?.sittings_considered || 0;
  return count === 0 ? 'No past exam evidence' : count < 4 ? `Based on ${count} past exam${count === 1 ? '' : 's'} only` : '';
}
export function conceptBadge(concept) {
  const stats = exam.statistics.concepts[concept.key], total = exam.statistics.sittings_considered;
  if (concept.basis === 'untested_core') return 'Untested';
  if (concept.basis === 'emphasized') return 'Emphasized in the course';
  if (concept.basis === 'prerequisite') return 'Needed for tested ideas';
  return total ? `Seen ${stats?.sittings_seen || 0}/${total}` : 'Tested';
}
// Status as a compact pill: an icon carries the kind, a short label the meaning.
const statusIcons = {
  tested: 'M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm3.1 4.9-3.6 4a.75.75 0 0 1-1.1 0L4.9 8.8a.75.75 0 1 1 1.1-1l1 1.1 3-3.4a.75.75 0 0 1 1.1 1Z',
  untested: 'M8 2.25a5.75 5.75 0 1 0 0 11.5 5.75 5.75 0 0 0 0-11.5ZM.75 8a7.25 7.25 0 1 1 14.5 0A7.25 7.25 0 0 1 .75 8ZM8 6a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z',
  emphasized: 'M8 1.25c.3 0 .55.2.64.48l1.12 3.51 3.51 1.12a.67.67 0 0 1 0 1.28l-3.51 1.12-1.12 3.51a.67.67 0 0 1-1.28 0L6.24 8.76 2.73 7.64a.67.67 0 0 1 0-1.28l3.51-1.12 1.12-3.51A.67.67 0 0 1 8 1.25Z',
  foundation: 'M7.66 1.58a.75.75 0 0 1 .68 0l6 3a.75.75 0 0 1 0 1.34l-6 3a.75.75 0 0 1-.68 0l-6-3a.75.75 0 0 1 0-1.34l6-3ZM1.33 9.08a.75.75 0 0 1 1-.34L8 11.58l5.66-2.84a.75.75 0 1 1 .68 1.34l-6 3a.75.75 0 0 1-.68 0l-6-3a.75.75 0 0 1-.33-1Z',
};
function conceptStatus(concept) {
  const stats = exam.statistics.concepts[concept.key], total = exam.statistics.sittings_considered;
  if (concept.basis === 'untested_core') return { tone: 'untested', label: 'Untested' };
  if (concept.basis === 'emphasized') return { tone: 'emphasized', label: 'Emphasized', detail: 'Emphasized in the course' };
  if (concept.basis === 'prerequisite') return { tone: 'foundation', label: 'Foundation', detail: 'Needed for tested ideas' };
  return total ? { tone: 'tested', label: `${stats?.sittings_seen || 0} of ${total} exams`, detail: `Seen in ${stats?.sittings_seen || 0} of ${total} past exams` } : { tone: 'tested', label: 'Tested' };
}
export function statusMarker(concept) {
  const status = conceptStatus(concept);
  const pill = node('span', `exam-status ${status.tone}`);
  const icon = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
  icon.append(svgNode('path', { d: statusIcons[status.tone], 'fill-rule': 'evenodd' }));
  pill.append(icon, node('span', '', status.label));
  if (status.detail) { pill.title = status.detail; pill.append(node('span', 'visually-hidden', ` (${status.detail})`)); }
  return pill;
}
export function formula(item) {
  const math = item?.mathml && parseMath(item.mathml);
  if (!math) return item?.plain ? node('span', 'exam-formula', item.plain) : null;
  const box = node('span', 'exam-formula'); math.setAttribute('display', 'inline');
  box.setAttribute('role', 'img'); box.setAttribute('aria-label', item.plain); box.append(math);
  return box;
}
export function list(className, items) {
  const element = node('ul', className);
  for (const text of items) element.append(studyText('li', '', text));
  return element;
}
export function quietLink(label, href, className = '') { const link = node('a', className, label); link.href = href; return link; }
