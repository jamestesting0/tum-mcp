import { node, studyText } from './dom.mjs';
import { renderReading } from './reading.mjs';

function decode(value) { try { return decodeURIComponent(value || ''); } catch { return ''; } }

export function renderExplore(unit) {
  const root = node('div', 'explore-reading');
  const parts = location.hash.replace(/^#study\//, '#').split('/');
  const itemKey = decode(parts[2]), blockKey = decode(parts[3]);
  const requested = unit.explore.find(item => item.key === itemKey);
  if (itemKey && (!requested || (blockKey && !requested.blocks.some(block => block.key === blockKey)))) {
    root.append(node('p', 'notice', 'That supporting passage is no longer here. Choose from the material below.'));
  }
  for (const item of unit.explore) {
    const section = node('section', 'explore-item'); section.dataset.exploreKey = item.key;
    const heading = studyText('h2', '', item.title);
    const reading = renderReading(item, { depth: 2, withVideo: false });
    for (const material of reading.querySelectorAll('[data-comment-target]')) {
      const block = material.closest('[data-block]');
      Object.assign(material.dataset, { commentTarget: 'explore', unitKey: unit.key,
        itemKey: item.key, blockKey: block.dataset.block, exploreRevision: item.revision });
    }
    section.append(heading, reading); root.append(section);
    if (itemKey && requested === item) {
      const target = blockKey && reading.querySelector(`[data-block="${CSS.escape(blockKey)}"]`);
      (target || section).dataset.exploreTarget = '';
    }
  }
  return root;
}
