import data from './data.mjs';
import { node, studyText, button, append, sourcesNote, announce } from './dom.mjs';
import { renderBlockBody } from './reading.mjs';
import { annotateExam } from './anchors.mjs';
import { exam, topics, formula, conceptBadge, quietLink } from './exam-state.mjs';
import { renderMap } from './exam-map.mjs';

const plain = text => studyText('span', '', text || '').textContent.toLowerCase();

function entry(concept, store, refresh) {
  const article = node('article', `exam-entry ${concept.tier}`); article.id = `concept-${concept.key}`;
  article.dataset.concept = concept.key;
  const details = node('details', 'exam-entry-details');
  const summary = node('summary', 'exam-entry-row');
  const line = annotateExam(studyText('span', 'exam-entry-line', concept.line), `concept:${concept.key}`, concept.revision, 'line');
  summary.append(studyText('strong', 'exam-entry-title', concept.title), line);
  const math = formula(concept.formula); if (math) summary.append(math);
  summary.append(node('span', 'exam-badge small', conceptBadge(concept)));
  details.append(summary);
  const body = node('div', 'exam-entry-body');
  if (concept.trigger) body.append(annotateExam(append(node('p'), node('span', 'exam-label', 'When you see: '), studyText('span', '', concept.trigger)), `concept:${concept.key}`, concept.revision, 'trigger'));
  if (concept.pitfall) body.append(annotateExam(append(node('p'), node('span', 'exam-label', 'Watch out: '), studyText('span', '', concept.pitfall)), `concept:${concept.key}`, concept.revision, 'pitfall'));
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
    section.append(append(node('div', 'section-heading'), studyText('h3', '', block.title), sourcesNote(block.sources, data.sources, data.course.synthetic, block.title)));
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
  if (links.childNodes.length) body.append(links);
  body.append(sourcesNote(concept.sources.map(item => item.key), data.sources, data.course.synthetic, concept.title));
  details.append(body);
  const flag = button('', () => {
    store.flag(concept, !store.flagged(concept)); paint(); refresh();
    announce(store.flagged(concept) ? 'Marked for review.' : 'Review mark removed.');
  }, 'quiet exam-flag');
  function paint() {
    const on = store.flagged(concept);
    flag.setAttribute('aria-pressed', String(on)); flag.textContent = on ? 'Review ✓' : 'Review';
    flag.setAttribute('aria-label', `${on ? 'Remove review mark from' : 'Mark for review:'} ${studyText('span', '', concept.title).textContent}`);
    article.classList.toggle('flagged', on);
  }
  paint();
  article.append(details, flag);
  return { article, details };
}

export function renderSheet(focusKey, store) {
  const root = node('div', 'exam-sheet');
  const heading = node('h1', '', 'Cheatsheet');
  root.append(append(node('div', 'unit-header'), node('p', 'eyebrow', 'Exam Prep'), heading,
    node('p', 'unit-summary', 'Only what is worth remembering for the exam. Open an entry for details.')));
  if (!exam.concepts.length) {
    root.append(node('p', '', 'The cheatsheet has not been prepared yet.'));
    return { root, heading, title: 'Cheatsheet', items: [] };
  }
  root.append(renderMap(key => { location.hash = `#exam/sheet/${key}`; }));
  const toolbar = node('div', 'exam-toolbar'); toolbar.setAttribute('role', 'toolbar'); toolbar.setAttribute('aria-label', 'Cheatsheet tools');
  const search = node('input'); search.type = 'search'; search.placeholder = 'Search the cheatsheet';
  search.setAttribute('aria-label', 'Search the cheatsheet');
  const toggle = (label, onChange) => {
    const control = button(label, () => { control.setAttribute('aria-pressed', String(control.getAttribute('aria-pressed') !== 'true')); onChange(); }, 'quiet');
    control.setAttribute('aria-pressed', 'false'); return control;
  };
  const core = toggle('Core only', () => filter()), review = toggle('Review only', () => filter());
  const entries = [];
  const expand = button('Expand all', () => {
    const opening = expand.getAttribute('aria-pressed') !== 'true';
    for (const item of entries) if (!item.article.hidden || !opening) item.details.open = opening;
    expand.setAttribute('aria-pressed', String(opening)); expand.textContent = opening ? 'Collapse all' : 'Expand all';
  }, 'quiet');
  expand.setAttribute('aria-pressed', 'false');
  const print = button('Print', () => window.print(), 'quiet exam-print');
  const status = node('p', 'small exam-filter-status'); status.setAttribute('role', 'status');
  toolbar.append(search, core, review, expand, print);
  root.append(toolbar, status);
  const groups = [];
  for (const topic of topics) {
    const members = exam.concepts.filter(concept => concept.topic === topic.key);
    if (!members.length) continue;
    const section = node('section', 'exam-topic');
    const title = studyText('h2', '', topic.title); section.append(title);
    const items = members.map(concept => {
      const made = entry(concept, store, () => filter()); entries.push({ ...made, concept });
      section.append(made.article); return made;
    });
    groups.push({ section, items });
    root.append(section);
  }
  const empty = node('p', 'empty-state small', 'No entries match. Clear the search or filters.'); empty.hidden = true; root.append(empty);
  function filter() {
    const query = search.value.trim().toLowerCase(), coreOnly = core.getAttribute('aria-pressed') === 'true', reviewOnly = review.getAttribute('aria-pressed') === 'true';
    let shown = 0;
    for (const item of entries) {
      const concept = item.concept;
      const text = [concept.title, concept.line, concept.trigger, concept.pitfall, concept.formula?.plain].map(plain).join(' ');
      const visible = (!query || text.includes(query)) && (!coreOnly || concept.tier === 'core') && (!reviewOnly || store.flagged(concept));
      item.article.hidden = !visible; shown += visible;
    }
    for (const group of groups) group.section.hidden = group.items.every(item => item.article.hidden);
    empty.hidden = shown > 0;
    status.textContent = query || coreOnly || reviewOnly ? `${shown} of ${entries.length} entries shown` : '';
  }
  search.addEventListener('input', filter);
  root.append(node('p', 'small exam-print-note', 'A printed sheet is a reference. If the exam allows only a handwritten aid, write your own.'));
  if (focusKey) {
    const target = entries.find(item => item.concept.key === focusKey);
    if (target) { target.details.open = true; requestAnimationFrame(() => { target.article.scrollIntoView({ block: 'center', behavior: 'instant' }); target.details.querySelector('summary').focus({ preventScroll: true }); }); }
  }
  return { root, heading, title: 'Cheatsheet', items: exam.concepts.map(concept => `concept:${concept.key}`) };
}
