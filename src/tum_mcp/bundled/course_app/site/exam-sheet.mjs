import data from './data.mjs';
import { node, studyText, append, sourcesNote, pageCitation } from './dom.mjs';
import { annotateExam } from './anchors.mjs';
import { exam, topics } from './exam-state.mjs';
import { renderMap } from './exam-map.mjs';
import { entry, citedBy } from './exam-entry.mjs';

export function renderSheet(focusKey) {
  const root = node('div', 'exam-sheet');
  const heading = node('h1', '', 'Cheatsheet');
  const eyebrow = node('p', 'eyebrow', 'Exam');
  root.append(append(node('div', 'unit-header'), eyebrow, heading));
  if (!exam.concepts.length) {
    root.append(node('p', '', 'The cheatsheet has not been prepared yet.'));
    return { root, heading, title: 'Cheatsheet', items: [] };
  }
  root.append(renderMap());
  const entries = [], same = list => new Set(list.map(concept => citedBy(concept).join(' '))).size === 1;
  // Shared sources are cited once: for the page when every entry shares them, else per section.
  const pageWide = same(exam.concepts);
  if (pageWide) pageCitation(sourcesNote(citedBy(exam.concepts[0]), data.sources, data.course.synthetic), eyebrow);
  for (const topic of topics) {
    const members = exam.concepts.filter(concept => concept.topic === topic.key);
    if (!members.length) continue;
    const shared = !pageWide && same(members), title = studyText('h2', '', topic.title);
    const section = append(node('section', 'exam-topic'), shared ? append(node('div', 'section-heading'), title, sourcesNote(citedBy(members[0]), data.sources, data.course.synthetic, topic.title)) : title);
    // A section path groups related references inside the topic; a heading opens where the
    // path changes, so authored order stays the order on the page.
    let previous = [];
    for (const concept of members) {
      const path = concept.path || [];
      path.forEach((label, depth) => {
        if (previous[depth] === label && previous.slice(0, depth).join('\n') === path.slice(0, depth).join('\n')) return;
        section.append(studyText(`h${3 + depth}`, 'exam-path', label));
      });
      previous = path;
      const mark = (element, field) => annotateExam(element, `concept:${concept.key}`, concept.revision, field);
      const made = entry(concept, { cite: !pageWide && !shared, mark, base: 3 + path.length });
      entries.push({ ...made, concept });
      section.append(made.article);
    }
    root.append(section);
  }
  if (focusKey) {
    const target = entries.find(item => item.concept.key === focusKey);
    if (target) {
      if (target.details) target.details.open = true;
      requestAnimationFrame(() => {
        target.article.scrollIntoView({ block: 'center', behavior: 'instant' });
        const focus = target.details?.querySelector('summary') || target.article;
        if (!target.details) target.article.tabIndex = -1;
        focus.focus({ preventScroll: true });
      });
    }
  }
  return { root, heading, title: 'Cheatsheet', items: exam.concepts.map(concept => `concept:${concept.key}`) };
}
