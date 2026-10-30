// Draws the given blocks with the app's own renderer in place of the lesson, one section each,
// so blocks the app shows one at a time (practice questions) or never (the review gallery) are
// measured and photographed at the reading column's real width. The check loads this as a
// module script of the page, so it shares the page's modules instead of fetching them again.
import { renderBlockBody } from './reading.mjs';
import { studyText } from './dom.mjs';

window.__visualInject = items => {
  const first = document.querySelector('main [data-block-index]');
  const host = first ? first.closest('.read-section').parentElement : document.querySelector('main');
  host.replaceChildren(...items.map(({ id, title, block }) => {
    const section = document.createElement('section'), material = document.createElement('div');
    section.className = 'read-section'; section.dataset.visualId = id;
    material.className = 'reading-material';
    material.append(studyText('h2', '', title), renderBlockBody(block));
    section.append(material);
    return section;
  }));
};
