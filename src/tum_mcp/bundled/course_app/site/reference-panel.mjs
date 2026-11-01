import data from './data.mjs';
import { node, studyText, append, sourcesNote } from './dom.mjs';
import { renderReading, renderBlockBody } from './reading.mjs';
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

// One Study passage under the panel's own title; a whole unit keeps its section titles.
export function openReference(unit, block, trigger) {
  const title = block ? block.title || block.term : unit.title;
  openPanel({
    eyebrow: unit.title, title,
    sources: block && sourcesNote(block.sources, data.sources, data.course.synthetic, title, {}, block.pages),
    body: block ? append(node('div', 'reading-material'), renderBlockBody(block, { term: false })) : renderReading({ blocks: unit.blocks }),
    more: { label: 'Open in Study', href: `#${unit.key}/content${block?.key ? `/${block.key}` : ''}` },
  }, trigger);
}
