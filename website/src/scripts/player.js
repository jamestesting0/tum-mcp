import { locate } from './story/timeline.js';
import { clamp } from './ui/dom.js';

// Play runs the tour hands-free: one clock moves the tour position at the pace the step weights
// encode and scrolls the page to match, so a pause leaves the page exactly where the tour is.
// The clock never runs ahead of the stage: `limit(position)` says how far it may go now.
// Anything the visitor does to move the page pauses it at once; only the button, K or Space plays.
const SECONDS_PER_UNIT = 6;
const ICONS = {
  play: '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M5 2.9v10.2c0 .6.7 1 1.2.7l8-5.1c.5-.3.5-1 0-1.4l-8-5.1C5.7 1.9 5 2.3 5 2.9Z"/></svg>',
  pause: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect fill="currentColor" x="3.5" y="2.5" width="3" height="11" rx="1"/><rect fill="currentColor" x="9.5" y="2.5" width="3" height="11" rx="1"/></svg>',
  replay: '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M2.8 8a5.2 5.2 0 1 0 1.6-3.8M2.8 2.2v3h3"/></svg>',
};
const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);

export function createPlayer({ timeline, button, bar, status, positionY, current, limit, ended, onPause, onRestart }) {
  let playing = false;
  let position = 0;
  let last = 0;
  let frame = 0;
  let expectedY = null;
  let quietUntil = 0;
  let state = '';
  const segments = [...bar.querySelectorAll('[data-chapter]')];
  const tip = bar.querySelector('[data-bar-tip]');
  const knob = bar.querySelector('[data-bar-knob]');

  function setIcon(name) {
    if (state === name) return;
    const first = !state;
    state = name;
    button.innerHTML = ICONS[name];
    if (!first) button.firstElementChild.classList.add('icon-in');
    button.setAttribute('aria-label', { play: 'Play tour', pause: 'Pause tour', replay: 'Replay tour' }[name]);
    button.setAttribute('aria-pressed', String(name === 'pause'));
  }

  function scrollToPosition(value) {
    expectedY = positionY(value);
    scrollTo({ top: expectedY, behavior: 'instant' });
  }

  function step(now) {
    frame = 0;
    if (!playing) return;
    const elapsed = last ? Math.min(64, now - last) : 0;
    last = now;
    if (ended(position)) { stop('replay'); return; }
    position = Math.min(limit(position), position + elapsed / 1000 / SECONDS_PER_UNIT, timeline.total - 1e-6);
    scrollToPosition(position);
    frame = requestAnimationFrame(step);
  }

  function play() {
    if (playing) return;
    position = current();
    if (ended(position) || position >= timeline.total - 1e-3) { position = 0; onRestart?.(); }
    playing = true;
    last = 0;
    setIcon('pause');
    status.textContent = 'Playing';
    scrollToPosition(position);
    frame ||= requestAnimationFrame(step);
  }

  function stop(icon = 'play') {
    if (!playing && state === icon) return;
    playing = false;
    cancelAnimationFrame(frame);
    frame = 0;
    expectedY = null;
    setIcon(icon);
    status.textContent = icon === 'replay' ? 'Finished' : 'Paused';
    onPause?.();
  }
  const pause = () => { if (playing) stop('play'); };
  const toggle = () => (playing ? pause() : play());

  button.addEventListener('click', toggle);

  // The visitor taking the page pauses the tour: wheel, touch, scroll keys, or any scroll the
  // clock did not make (scrollbar, momentum, find-in-page).
  addEventListener('wheel', pause, { passive: true });
  addEventListener('touchstart', event => { if (!event.target.closest('.player')) pause(); }, { passive: true });
  addEventListener('scroll', () => {
    if (!playing || expectedY == null || performance.now() < quietUntil) return;
    if (Math.abs(scrollY - expectedY) > 3) pause();
  }, { passive: true });
  addEventListener('resize', () => { quietUntil = performance.now() + 250; });
  visualViewport?.addEventListener('resize', () => { quietUntil = performance.now() + 250; });
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
  addEventListener('keydown', event => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.target.closest?.('input, textarea, select, [contenteditable], dialog')) return;
    if (event.key === 'k' || event.key === 'K') { event.preventDefault(); toggle(); return; }
    if (event.target === bar || event.target === button) return;
    if (event.key === ' ' && playing) { event.preventDefault(); pause(); return; }
    if (SCROLL_KEYS.has(event.key)) pause();
  });

  // The bar: click or tap seeks to the scene under the pointer, drag previews and seeks on
  // release, arrows step through scenes and Page keys through chapters.
  const chapterEnd = index => timeline.chapters[index + 1]?.start ?? timeline.total;
  function positionAt(clientX) {
    const boxes = segments.map(segment => segment.getBoundingClientRect());
    let index = boxes.findIndex(box => clientX < box.right + 1.5);
    if (index < 0) index = boxes.length - 1;
    const box = boxes[index];
    const chapter = timeline.chapters[index];
    return chapter.start + clamp((clientX - box.left) / box.width) * (chapterEnd(index) - chapter.start);
  }
  // A click or drag lands exactly where it points; the bar glides there briefly so the jump reads.
  function seek(value, { exact = true } = {}) {
    const target = locate(timeline, Math.min(value, timeline.total - 1e-6)).step;
    position = exact ? Math.max(0, Math.min(value, timeline.total - 1e-4)) : target.start + Math.min(0.002, target.weight * 0.01);
    bar.classList.add('is-seeking');
    clearTimeout(seekTimer);
    seekTimer = setTimeout(() => bar.classList.remove('is-seeking'), 260);
    scrollToPosition(position);
    last = 0;
  }
  let seekTimer = 0;
  function xFor(value) {
    const index = Math.max(0, timeline.chapters.findLastIndex(chapter => value >= chapter.start));
    const chapter = timeline.chapters[index];
    const segment = segments[index];
    return segment.offsetLeft + clamp((value - chapter.start) / (chapterEnd(index) - chapter.start)) * segment.offsetWidth;
  }
  function showTip(value) {
    const { step: target } = locate(timeline, Math.min(value, timeline.total - 1e-6));
    if (tip.textContent !== target.caption.title) tip.textContent = target.caption.title;
    const x = xFor(value);
    const half = tip.offsetWidth / 2;
    bar.style.setProperty('--tip-x', `${clamp(x - half, 0, bar.offsetWidth - tip.offsetWidth)}px`);
    for (const [index, segment] of segments.entries()) segment.classList.toggle('is-hover', index === target.chapterIndex);
    bar.classList.add('is-tipping');
  }
  function hideTip() {
    bar.classList.remove('is-tipping');
    for (const segment of segments) segment.classList.remove('is-hover');
  }

  let scrub = null;
  bar.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    event.preventDefault();
    bar.setPointerCapture(event.pointerId);
    scrub = { id: event.pointerId, value: positionAt(event.clientX) };
    bar.classList.add('is-scrubbing');
    bar.style.setProperty('--knob-x', `${xFor(scrub.value)}px`);
    showTip(scrub.value);
  });
  bar.addEventListener('pointermove', event => {
    const value = positionAt(event.clientX);
    if (scrub?.id === event.pointerId) {
      scrub.value = value;
      bar.style.setProperty('--knob-x', `${xFor(value)}px`);
    }
    if (scrub || event.pointerType === 'mouse') showTip(value);
  });
  const release = event => {
    if (scrub?.id !== event.pointerId) return;
    const { value } = scrub;
    scrub = null;
    bar.classList.remove('is-scrubbing');
    hideTip();
    if (event.type === 'pointerup') seek(value);
  };
  bar.addEventListener('pointerup', release);
  bar.addEventListener('pointercancel', release);
  bar.addEventListener('pointerleave', event => { if (!scrub && event.pointerType === 'mouse') hideTip(); });
  bar.addEventListener('keydown', event => {
    const here = locate(timeline, Math.min(current(), timeline.total - 1e-6)).step;
    const chapter = here.chapterIndex;
    const steps = timeline.steps;
    const target = {
      ArrowRight: steps[here.index + 1]?.start, ArrowUp: steps[here.index + 1]?.start,
      ArrowLeft: steps[Math.max(0, here.index - 1)].start, ArrowDown: steps[Math.max(0, here.index - 1)].start,
      PageDown: timeline.chapters[chapter + 1]?.start, PageUp: timeline.chapters[Math.max(0, chapter - 1)].start,
      Home: 0, End: steps.at(-1).start,
    }[event.key];
    if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); toggle(); return; }
    if (target === undefined) return;
    event.preventDefault();
    seek(target, { exact: false });
  });

  // Names under the segments show while they fit; otherwise only the current chapter's name shows.
  function fit() {
    const labels = segments.map(segment => segment.querySelector('.seg-label').getBoundingClientRect());
    const tight = labels.some((box, index) => index && box.left < labels[index - 1].right + 10);
    bar.classList.toggle('is-tight', tight);
  }
  new ResizeObserver(fit).observe(bar);

  function show(value, step) {
    bar.style.setProperty('--knob-x', scrub ? bar.style.getPropertyValue('--knob-x') : `${xFor(value)}px`);
    bar.setAttribute('aria-valuenow', String(Math.round((value / timeline.total) * 100)));
    bar.setAttribute('aria-valuetext', `${timeline.chapters[step.chapterIndex].label}: ${step.caption.title}`);
    if (!playing && state === 'replay' && value < timeline.total - 0.2) setIcon('play');
  }

  setIcon('play');
  return { play, pause, show, seek, get playing() { return playing; } };
}
