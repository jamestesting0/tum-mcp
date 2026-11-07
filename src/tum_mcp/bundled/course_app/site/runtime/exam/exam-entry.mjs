import data from '../../data.mjs';
import { node, svgNode, studyText, append, button, sourcesNote } from '../shell/dom.mjs';
import { renderBlockBody } from '../reading/reading.mjs';
import { exam, formula, statusMarker, quietLink } from './exam-state.mjs';
import { openPanel } from '../shell/reference-panel.mjs';
import { workflowSteps } from './exam-patterns.mjs';
import { symbolName } from '../reading/symbols.mjs';

// One cheatsheet entry, shown the same way in the list, the Recall panel and the map card.

const cueIcons = {
  cue: 'M8 3C4.4 3 1.7 5.3.6 8c1.1 2.7 3.8 5 7.4 5s6.3-2.3 7.4-5C14.3 5.3 11.6 3 8 3Zm0 8.2a3.2 3.2 0 1 1 0-6.4 3.2 3.2 0 0 1 0 6.4Zm0-1.7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  pitfall: 'M8.9 1.6a1 1 0 0 0-1.8 0L.4 13.5A1 1 0 0 0 1.3 15h13.4a1 1 0 0 0 .9-1.5L8.9 1.6ZM7.25 6h1.5v4h-1.5V6Zm0 5.5h1.5V13h-1.5v-1.5Z',
};

// The sources an entry cites, its details included.
export const citedBy = concept => [...new Set([...concept.sources.map(item => item.key), ...(concept.details || []).flatMap(block => block.sources)])].sort();

// The row a student scans: title, formula, status and the one line.
export function entryHead(concept) {
  const head = append(node('span', 'exam-entry-head'), studyText('strong', 'exam-entry-title', concept.title));
  const math = formula(concept.formula); if (math) head.append(math);
  head.append(statusMarker(concept));
  if (concept.tier === 'supporting') head.append(node('span', 'exam-tier', 'Supportive'));
  return head;
}

// What an entry shows when opened: cue, pitfall, meanings, conditions, its method and its
// details. Detail titles keep their levels below `base`, the heading level around the entry.
export function entryBody(concept, { mark = element => element, base = 3 } = {}) {
  const body = node('div', 'exam-entry-body');
  // Recognition cue and pitfall read as two labelled rows; the label sits in a side column.
  const cues = node('dl', 'exam-entry-cues');
  for (const [field, label, tone] of [['trigger', 'When you see', 'cue'], ['pitfall', 'Watch out', 'pitfall']]) {
    if (!concept[field]) continue;
    const icon = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
    icon.append(svgNode('path', { d: cueIcons[tone], 'fill-rule': 'evenodd' }));
    cues.append(append(node('dt', `exam-cue ${tone}`), icon, node('span', '', label)), mark(studyText('dd', '', concept[field]), field));
  }
  if (cues.childNodes.length) body.append(cues);
  if (concept.formula) {
    if (concept.formula.symbols?.length) {
      const symbols = node('dl', 'symbols');
      for (const item of concept.formula.symbols) symbols.append(symbolName('dt', '', item.symbol), studyText('dd', '', item.meaning));
      body.append(symbols);
    }
    if (concept.formula.conditions) body.append(studyText('p', 'small', concept.formula.conditions));
  }
  // A non-formula entry's maths (in its line, tables or text) lists its meanings the same way.
  if (concept.symbols?.length) {
    const symbols = node('dl', 'symbols');
    for (const item of concept.symbols) symbols.append(symbolName('dt', '', item.symbol), studyText('dd', '', item.meaning));
    body.append(symbols);
  }
  // An entry whose method is a pattern's workflow shows those steps, each opening what it
  // applies, and leads on to practising them.
  const method = concept.workflow_from && exam.patterns.find(item => item.key === concept.workflow_from);
  if (method) {
    body.append(append(node('div', 'exam-entry-steps'),
      workflowSteps(method),
      append(node('p', 'small'),
        quietLink('Worked practice', `#exam/patterns/${method.key}/worked`),
        ...(method.drill?.length ? [' · ', quietLink('Practise', `#exam/patterns/${method.key}/practise`)] : []))));
  }
  for (const [index, block] of (concept.details || []).entries()) {
    const section = node('div', 'exam-detail');
    if (block.title) {
      const level = Math.min(6, base + (block.level || 1) - 1);
      const title = studyText(`h${level}`, '', block.title); title.dataset.level = String(block.level || 1);
      section.append(title);
    }
    section.append(mark(renderBlockBody(block), `detail:${index}`));
    body.append(section);
  }
  return body;
}

// Where else the entry leads: the Study units that teach it and the patterns that use it.
export function entryLinks(concept) {
  const links = node('p', 'small exam-entry-links');
  const add = link => { if (links.childNodes.length) links.append(' · '); links.append(link); };
  const linked = new Set();
  for (const passage of concept.passages || []) {
    const unit = data.units.find(item => item.key === passage.unit);
    const block = unit?.blocks.find(item => item.key === passage.block);
    if (!block) continue;
    add(quietLink(`Study: ${block.title || block.term || unit.title}`, `#study/${unit.key}/content/${block.key}`));
    linked.add(unit.key);
  }
  for (const key of concept.units || []) {
    const unit = data.units.find(item => item.key === key);
    if (unit && !linked.has(key)) add(quietLink(`Study: ${unit.title}`, `#study/${unit.key}/content`));
  }
  for (const target of concept.exercises || []) {
    const group = data.exercises?.sets.find(item => item.key === target.set);
    const exercise = group?.exercises.find(item => item.key === target.exercise);
    if (exercise) add(quietLink(`Exercise: ${exercise.title}`, `#exercises/${group.key}/${exercise.key}`));
  }
  for (const pattern of exam.patterns) {
    if (pattern.key !== concept.workflow_from && pattern.concepts.includes(concept.key)) add(quietLink(`Practise: ${pattern.title}`, `#exam/patterns/${pattern.key}/practise`));
  }
  return links.childNodes.length ? links : null;
}

// Related links and citations belong inside the expansion, including for one-line facts.
export function entry(concept, { cite = false, mark = element => element, base = 3, id = true } = {}) {
  const article = node('article', `exam-entry ${concept.tier}`);
  if (id) { article.id = `concept-${concept.key}`; article.dataset.concept = concept.key; }
  const line = mark(studyText('span', 'exam-entry-line', concept.line), 'line');
  const body = entryBody(concept, { mark, base });
  const recall = body.childNodes.length > 0;
  const footer = node('div', 'exam-entry-footer');
  const links = entryLinks(concept); if (links) footer.append(links);
  if (cite) footer.append(sourcesNote(citedBy(concept), data.sources, data.course.synthetic, concept.title));
  const opens = body.childNodes.length || footer.childNodes.length;
  if (!opens) {
    article.append(append(node('div', 'exam-entry-row static'), entryHead(concept), line));
    return { article, details: null };
  }
  const details = node('details', `exam-entry-details${recall ? ' has-recall' : ''}`);
  const summary = append(node('summary', 'exam-entry-row'), entryHead(concept), line);
  // An entry taller than the screen ends with a way to close it, so the student need not
  // scroll back to its title; closing returns to that title.
  const collapse = button('', () => {
    details.open = false;
    summary.scrollIntoView({ block: 'nearest' }); summary.focus({ preventScroll: true });
  }, 'quiet exam-entry-collapse');
  const chevron = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' });
  chevron.append(svgNode('path', { d: 'M4 10l4-4 4 4' }));
  collapse.append(chevron, node('span', '', 'Collapse'));
  collapse.setAttribute('aria-label', `Collapse ${studyText('span', '', concept.title).textContent}`);
  collapse.hidden = true; footer.prepend(collapse); body.append(footer);
  details.addEventListener('toggle', () => {
    if (details.open) requestAnimationFrame(() => { collapse.hidden = body.offsetHeight < innerHeight * 0.8; });
  });
  details.append(summary, body);
  article.append(details);
  return { article, details };
}

// A cheatsheet entry beside the page, as a Study passage opens, so the question stays in place.
export function openConcept(concept, trigger) {
  const body = node('div', 'exam-entry exam-entry-panel');
  const head = append(node('p', 'exam-entry-head'), studyText('span', 'exam-entry-line', concept.line));
  const math = formula(concept.formula); if (math) head.prepend(math, ' ');
  body.append(head, entryBody(concept));
  const links = entryLinks(concept); if (links) body.append(links);
  openPanel({
    eyebrow: 'Cheatsheet', title: concept.title, body,
    sources: sourcesNote(citedBy(concept), data.sources, data.course.synthetic, concept.title),
    more: { label: 'Open in Cheatsheet', href: `#exam/sheet/${concept.key}` },
  }, trigger);
}
