import data from './data.mjs';
import { node, studyText, button, toggletip } from './dom.mjs';
import { openReference } from './reference-panel.mjs';

// The ideas a task builds on, one chip each. The chip's name is the cue: the student can try
// to recall the idea, then open it to see it in one line and, beside the page, the Study
// passage that teaches it. Items with an href (an exam pattern) are plain links; an item with
// nothing to open is its own text.
export function recallRow(items) {
  if (!items.length) return null;
  const row = node('div', 'recall-row');
  row.append(node('span', 'small recall-label', 'Recall'));
  for (const item of items) {
    if (item.href) {
      const link = studyText('a', 'recall-chip', item.label); link.href = item.href;
      row.append(link); continue;
    }
    if (!item.line) { row.append(studyText('span', 'small', item.label)); continue; }
    const chip = studyText('button', 'recall-chip', item.label);
    row.append(toggletip(chip, bubble => {
      bubble.append(studyText('span', 'term-statement', item.line));
      const unit = data.units.find(entry => entry.key === item.unit);
      const block = unit?.blocks.find(entry => item.block && entry.key === item.block);
      if (unit) bubble.append(button('Open lesson', () => openReference(unit, block, chip), 'quiet term-more'));
      if (item.concept) bubble.append(button('Open cheatsheet', async () => (await import('./exam-entry.mjs')).openConcept(item.concept, chip), 'quiet term-more'));
    }, 'recall-tip'));
  }
  return row;
}

// An exam item names the patterns it follows and the concepts it tests. A concept opens the
// Study passage it names, or the first unit that teaches it, and its cheatsheet entry, both
// beside the page. The cheatsheet module loads only when a student opens an entry.
export function examRecall(conceptKeys, patternKeys = []) {
  const exam = data.exam || { concepts: [], patterns: [] };
  const patterns = patternKeys.map(key => exam.patterns.find(item => item.key === key)).filter(Boolean)
    .map(pattern => ({ label: `Pattern: ${pattern.title}`, href: `#exam/patterns/${pattern.key}` }));
  const ideas = conceptKeys.map(key => exam.concepts.find(item => item.key === key)).filter(Boolean).map(concept => {
    const passage = concept.passages?.[0];
    return { label: concept.title, line: concept.line, unit: passage?.unit || concept.units?.[0], block: passage?.block, concept };
  });
  return recallRow([...patterns, ...ideas]);
}
