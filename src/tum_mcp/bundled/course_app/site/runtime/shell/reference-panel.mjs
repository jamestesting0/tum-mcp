import data from '../../data.mjs';
import { node, studyText, append, sourcesNote } from './dom.mjs';
import { renderReading, renderBlockBody } from '../reading/reading.mjs';
import { iconButton } from './navigation.mjs';

// A passage opened beside the task instead of in its place, so the step, drafts and scroll
// position stay where the student left them.
const wide = matchMedia('(min-width: 1200px)');
export function openPanel({ eyebrow, title, sources, body, more }, trigger) {
  document.querySelector('dialog.reference-panel')?.close();
  const panel = node('dialog', 'reference-panel'), heading = studyText('h2', '', title);
  heading.id = 'reference-panel-title'; panel.setAttribute('aria-labelledby', heading.id);
  const close = iconButton('Close', 'close', () => panel.close());
  const label = append(node('div', 'page-eyebrow'), node('p', 'small', eyebrow));
  if (sources) label.append(sources);
  const header = append(node('div', 'reference-panel-header'), append(node('div', ''), label, heading), close);
  const link = node('a', '', more.label); link.href = more.href;
  panel.append(header, body, append(node('p', 'small reference-panel-more'), link));
  // Returning focus can scroll the page; the student comes back to exactly where they were.
  const scroller = trigger.closest('main')?.scrollHeight > trigger.closest('main')?.clientHeight ? trigger.closest('main') : document.scrollingElement;
  const top = scroller.scrollTop;
  panel.addEventListener('close', () => {
    panel.remove(); delete document.documentElement.dataset.reference;
    if (trigger.isConnected) trigger.focus({ preventScroll: true });
    scroller.scrollTop = top;
  });
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); panel.close(); } });
  addEventListener('hashchange', () => panel.close(), { once: true });
  document.body.append(panel);
  // Wide screens keep the task readable beside the panel; narrower ones give the panel the screen.
  if (wide.matches) { document.documentElement.dataset.reference = 'open'; panel.show(); } else panel.showModal();
  close.focus();
}

// The section a block opens, as Study shows it: the block, its untitled continuations
// (formula, figure, derivation) and deeper subsections, up to the next heading at its level.
function sectionBlocks(unit, block) {
  const start = unit.blocks.findIndex(item => item === block || (block.key && item.key === block.key));
  if (start < 0 || !block.title) return [block];
  const level = block.level || 1, blocks = [block];
  for (const next of unit.blocks.slice(start + 1)) {
    if (next.title && next.kind !== 'definition' && (next.level || 1) <= level) break;
    blocks.push(next);
  }
  return blocks;
}

// The panel's title already cites the section's opening, so its own citation goes.
function withoutOpeningCitation(body) {
  body.querySelector('.read-section .section-heading .source-note')?.remove();
  return body;
}

// One Study section under the panel's own title; a whole unit keeps its section titles.
export function openReference(unit, block, trigger) {
  const title = block ? block.title || block.term : unit.title;
  const section = block && sectionBlocks(unit, block);
  // The title cites the section's opening (the block and its untitled continuations) once;
  // its subsections keep their own citations.
  const cut = section ? section.findIndex((item, i) => i > 0 && item.title) : -1;
  const head = section ? section.slice(0, cut < 0 ? section.length : cut) : [];
  const cited = [...new Set(head.flatMap(item => item.sources || []))];
  openPanel({
    eyebrow: unit.title, title,
    sources: block && sourcesNote(cited, data.sources, data.course.synthetic, title, {}, block.pages),
    body: !block ? renderReading({ blocks: unit.blocks })
      : section.length > 1 ? withoutOpeningCitation(renderReading({ blocks: [{ ...block, title: undefined }, ...section.slice(1)] }, { withVideo: false }))
      : append(node('div', 'reading-material'), renderBlockBody(block, { term: false })),
    more: { label: 'Open in Study', href: `#${unit.key}/content${block?.key ? `/${block.key}` : ''}` },
  }, trigger);
}
