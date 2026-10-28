import data from './data.mjs';
import { node, studyText } from './dom.mjs';
import { parseMath } from './mathml.mjs';

export const exam = data.exam || { topics: [], sittings: [], concepts: [], links: [], patterns: [], mocks: [], statistics: { patterns: {}, concepts: {}, pattern_order: [] }, map: { nodes: [] } };
export const examPrefix = `course-exam:${data.course.identity}:`;
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};

export function examStore(read, write) {
  const flagsKey = `${examPrefix}review`;
  const flags = object(read(flagsKey, {}));
  return {
    flagged(concept) { return flags[concept.key] === concept.revision; },
    flag(concept, value) {
      if (value) flags[concept.key] = concept.revision; else delete flags[concept.key];
      write(flagsKey, flags);
    },
    flaggedCount() { return exam.concepts.filter(concept => flags[concept.key] === concept.revision).length; },
    attempt(kind, key, revision) {
      const storage = `${examPrefix}${kind}:${key}:${revision}`, saved = object(read(storage, {}));
      const value = {
        answers: object(saved.answers), marks: object(saved.marks),
        started: saved.started === true, finished: saved.finished === true, timed: saved.timed === true,
        elapsed: Number.isFinite(saved.elapsed) ? Math.max(0, saved.elapsed) : 0,
        running: Number.isFinite(saved.running) ? saved.running : null,
      };
      return { value, save: () => write(storage, value), clear: () => write(storage, {}) };
    },
  };
}

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
  if (concept.basis === 'untested_core') return 'Not yet tested';
  if (concept.basis === 'emphasized') return 'Emphasized in the course';
  if (concept.basis === 'prerequisite') return 'Needed for tested ideas';
  return total ? `Seen ${stats?.sittings_seen || 0}/${total}` : 'Tested';
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
