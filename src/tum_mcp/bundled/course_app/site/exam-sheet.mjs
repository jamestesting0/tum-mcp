import data from './data.mjs';
import { node, svgNode, studyText, append, sourcesNote, pageCitation } from './dom.mjs';
import { renderBlockBody } from './reading.mjs';
import { annotateExam } from './anchors.mjs';
import { exam, topics, formula, statusMarker, quietLink } from './exam-state.mjs';
import { renderMap } from './exam-map.mjs';


const cueIcons = {
  cue: 'M8 3C4.4 3 1.7 5.3.6 8c1.1 2.7 3.8 5 7.4 5s6.3-2.3 7.4-5C14.3 5.3 11.6 3 8 3Zm0 8.2a3.2 3.2 0 1 1 0-6.4 3.2 3.2 0 0 1 0 6.4Zm0-1.7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  pitfall: 'M8.9 1.6a1 1 0 0 0-1.8 0L.4 13.5A1 1 0 0 0 1.3 15h13.4a1 1 0 0 0 .9-1.5L8.9 1.6ZM7.25 6h1.5v4h-1.5V6Zm0 5.5h1.5V13h-1.5v-1.5Z',
};

// The sources an entry cites, its details included.
const citedBy = concept => [...new Set([...concept.sources.map(item => item.key), ...(concept.details || []).flatMap(block => block.sources)])].sort();

function entry(concept, cite) {
  const article = node('article', `exam-entry ${concept.tier}`); article.id = `concept-${concept.key}`;
  article.dataset.concept = concept.key;
  const details = node('details', 'exam-entry-details');
  const summary = node('summary', 'exam-entry-row');
  const line = annotateExam(studyText('span', 'exam-entry-line', concept.line), `concept:${concept.key}`, concept.revision, 'line');
  const head = append(node('span', 'exam-entry-head'), studyText('strong', 'exam-entry-title', concept.title));
  const math = formula(concept.formula); if (math) head.append(math);
  head.append(statusMarker(concept));
  if (concept.tier === 'supporting') head.append(node('span', 'exam-tier', 'Supportive'));
  summary.append(head, line);
  details.append(summary);
  const body = node('div', 'exam-entry-body');
  // Recognition cue and pitfall read as two labelled rows; the label sits in a side column.
  const cues = node('dl', 'exam-entry-cues');
  for (const [field, label, tone] of [['trigger', 'When you see', 'cue'], ['pitfall', 'Watch out', 'pitfall']]) {
    if (!concept[field]) continue;
    const icon = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
    icon.append(svgNode('path', { d: cueIcons[tone], 'fill-rule': 'evenodd' }));
    cues.append(append(node('dt', `exam-cue ${tone}`), icon, node('span', '', label)),
      annotateExam(studyText('dd', '', concept[field]), `concept:${concept.key}`, concept.revision, field));
  }
  if (cues.childNodes.length) body.append(cues);
  if (concept.formula) {
    if (concept.formula.symbols?.length) {
      const symbols = node('dl', 'symbols');
      for (const item of concept.formula.symbols) symbols.append(studyText('dt', '', item.symbol), studyText('dd', '', item.meaning));
      body.append(symbols);
    }
    if (concept.formula.conditions) body.append(studyText('p', 'small', concept.formula.conditions));
  }
  for (const [index, block] of (concept.details || []).entries()) {
    const section = node('div', 'exam-detail');
    if (block.title) section.append(studyText('h3', '', block.title));
    section.append(annotateExam(renderBlockBody(block), `concept:${concept.key}`, concept.revision, `detail:${index}`));
    body.append(section);
  }
  const related = exam.patterns.filter(pattern => pattern.concepts.includes(concept.key));
  const links = node('p', 'small exam-entry-links');
  for (const pattern of related) { if (links.childNodes.length) links.append(' · '); links.append(quietLink(studyText('span', '', pattern.title).textContent, `#exam/patterns/${pattern.key}`)); }
  for (const key of concept.units || []) {
    const unit = data.units.find(item => item.key === key);
    if (unit) { if (links.childNodes.length) links.append(' · '); links.append(quietLink(`Study: ${unit.title}`, `#study/${unit.key}/content`)); }
  }
  // An entry cites its sources itself only when its section or the page does not already.
  const footer = node('div', 'exam-entry-footer');
  if (links.childNodes.length) footer.append(links);
  if (cite) footer.append(sourcesNote(citedBy(concept), data.sources, data.course.synthetic, concept.title));
  if (footer.childNodes.length) body.append(footer);
  details.append(body);
  article.append(details);
  return { article, details };
}

export function renderSheet(focusKey) {
  const root = node('div', 'exam-sheet');
  const heading = node('h1', '', 'Cheatsheet');
  const eyebrow = node('p', 'eyebrow', 'Exam');
  root.append(append(node('div', 'unit-header'), eyebrow, heading));
  if (!exam.concepts.length) {
    root.append(node('p', '', 'The cheatsheet has not been prepared yet.'));
    return { root, heading, title: 'Cheatsheet', items: [] };
  }
  root.append(renderMap(key => { location.hash = `#exam/sheet/${key}`; }));
  const entries = [], same = list => new Set(list.map(concept => citedBy(concept).join(' '))).size === 1;
  // Shared sources are cited once: for the page when every entry shares them, else per section.
  const pageWide = same(exam.concepts);
  if (pageWide) pageCitation(sourcesNote(citedBy(exam.concepts[0]), data.sources, data.course.synthetic), eyebrow);
  for (const topic of topics) {
    const members = exam.concepts.filter(concept => concept.topic === topic.key);
    if (!members.length) continue;
    const shared = !pageWide && same(members), title = studyText('h2', '', topic.title);
    const section = append(node('section', 'exam-topic'), shared ? append(node('div', 'section-heading'), title, sourcesNote(citedBy(members[0]), data.sources, data.course.synthetic, topic.title)) : title);
    for (const concept of members) { const made = entry(concept, !pageWide && !shared); entries.push({ ...made, concept }); section.append(made.article); }
    root.append(section);
  }
  if (focusKey) {
    const target = entries.find(item => item.concept.key === focusKey);
    if (target) { target.details.open = true; requestAnimationFrame(() => { target.article.scrollIntoView({ block: 'center', behavior: 'instant' }); target.details.querySelector('summary').focus({ preventScroll: true }); }); }
  }
  return { root, heading, title: 'Cheatsheet', items: exam.concepts.map(concept => `concept:${concept.key}`) };
}
