import story from '../content/story.json';
import marks from 'virtual:marks';
import { createPlayer } from './player.js';
import { createStage } from './stage.js';
import { buildTimeline, locate } from './story/timeline.js';
import { clamp, h } from './ui/dom.js';
import { stroke } from './ui/icons.js';

const THEME_KEY = 'tum-mcp-walkthrough:theme';
const HOST_KEY = 'tum-mcp-walkthrough:host';
const root = document.documentElement;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const store = {
  get: key => { try { return localStorage.getItem(key); } catch { return null; } },
  set: (key, value) => { try { localStorage.setItem(key, value); } catch { /* storage unavailable: the choice lasts for this visit */ } },
};

const markFactory = {
  codex: () => h('span.mark-pair', { html: `<span class="mark-light">${marks.codexLight}</span><span class="mark-dark">${marks.codexDark}</span>` }),
  claude: () => h('span.mark', { html: marks.claude }),
  cursor: () => h('span.mark', { html: marks.cursor }),
  antigravity: () => h('span.mark', { html: marks.antigravity }),
  product: host => h('span.wb-letterpress', { html: marks.letterpress[host] ?? '' }),
};

const timeline = buildTimeline(story);
const appDocument = () => JSON.parse(document.getElementById('app-document').textContent);
const stageElement = document.querySelector('[data-stage]');
const stage = createStage({ root: stageElement, story, timeline, marks: markFactory, appDocument });

function systemTheme() { return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }
function applyTheme(theme) {
  root.dataset.theme = theme;
  const toggle = document.querySelector('[data-theme-toggle]');
  toggle.setAttribute('aria-label', theme === 'dark' ? 'Use light theme' : 'Use dark theme');
  toggle.replaceChildren(stroke(theme === 'dark' ? 'sun' : 'moon'));
  stage.embed.setTheme(theme);
}
applyTheme(store.get(THEME_KEY) ?? systemTheme());
document.querySelector('[data-theme-toggle]').addEventListener('click', () => {
  const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
  document.querySelector('[data-theme-toggle]').dataset.turning = '';
  store.set(THEME_KEY, next);
  applyTheme(next);
});

const tabs = [...document.querySelectorAll('[data-host-tab]')];
for (const tab of tabs) tab.querySelector('[data-mark]').replaceWith(markFactory[tab.dataset.hostTab]());
function selectHost(key, { focus = false } = {}) {
  for (const tab of tabs) {
    const selected = tab.dataset.hostTab === key;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  }
  store.set(HOST_KEY, key);
  stage.setHost(key);
  showHeroAgent(key);
}
// The headline names the agent picked in the switcher below it.
const heroMark = document.querySelector('[data-hero-mark]');
const heroName = document.querySelector('[data-hero-name]');
function showHeroAgent(key) {
  const label = story.hosts.find(host => host.key === key)?.label ?? '';
  if (heroName.textContent === label && heroMark.firstChild) return;
  const swap = () => { heroMark.replaceChildren(markFactory[key]()); heroName.textContent = label; };
  if (!heroMark.firstChild || reducedMotion.matches) { swap(); return; }
  const agent = heroName.parentElement;
  agent.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-0.12em)' }], { duration: 140, easing: 'ease-in' }).finished.then(() => {
    swap();
    agent.animate([{ opacity: 0, transform: 'translateY(0.12em)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.2, .7, .2, 1)' });
  });
}
for (const [index, tab] of tabs.entries()) {
  tab.addEventListener('click', () => selectHost(tab.dataset.hostTab));
  tab.addEventListener('keydown', event => {
    const move = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!move) return;
    event.preventDefault();
    selectHost(tabs[(index + move + tabs.length) % tabs.length].dataset.hostTab, { focus: true });
  });
}
const savedHost = store.get(HOST_KEY);
selectHost(story.hosts.some(host => host.key === savedHost) ? savedHost : story.hosts[0].key);

const track = document.querySelector('[data-track]');
const captionTitle = document.querySelector('[data-caption-title]');
const captionLine = document.querySelector('[data-caption-line]');
const segments = [...document.querySelectorAll('[data-chapter]')];
track.style.setProperty('--steps', String(timeline.total));
for (const [index, chapter] of timeline.chapters.entries()) {
  const anchor = document.getElementById(chapter.key);
  anchor.style.setProperty('--at', String(chapter.start / timeline.total));
  // Step weights follow play time, so a segment's width is its chapter's share of the tour.
  segments[index].style.flex = `${(timeline.chapters[index + 1]?.start ?? timeline.total) - chapter.start} 1 0`;
}

const finish = document.querySelector('[data-finish]');
const caption = document.querySelector('.caption');
let page = 'tour';
let frame = 0;
let lastStep = -1;

// The scroll chooses the scene; each scene plays by itself at a fixed pace (story/play.js).
// Scrolling ahead queues scenes, which then follow one another a little faster; when more than
// JUMP_MS of scenes are waiting, or on any step back, the scene shows finished behind a short fade.
const DWELL_MS = 160;
const CATCH_UP = 1.6;
const JUMP_MS = 8000;
// The visitor's scroll is a second clock: a scene never plays behind where the scroll has reached
// in it, easing toward it over FOLLOW_MS.
const FOLLOW_MS = 260;
const BACK_GRACE = 0.08;
const STAY_MS = 450;
const BEAT_GRACE = 0.035;
const seen = new Set();
const beatShown = new Map();
const scene = { index: -1, ms: 0, waited: 0, entered: 0, entry: 0, manual: false };
let goal = { step: timeline.steps[0], t: 0, position: 0, started: false };
let lastTick = 0;
let lastDraw = '';

const duration = index => stage.plan(timeline.steps[index]).duration;

// A scene's own part of its step: up to its first guide beat, or the whole step. Self-play and the
// visitor's scroll share this one mapping, so when a scene ends the scroll is at the end of its part.
const contentEnd = step => {
  const beats = step.app ? step.guide ?? [] : [];
  return beats.length ? Math.max(0.05, beats[0].at - 0.012) : 0.994;
};
const positionY = position => {
  const box = track.getBoundingClientRect();
  return box.top + scrollY + (position / timeline.total) * Math.max(1, box.height - innerHeight);
};
// Self-play scrolls the page through its own scene as it plays, so no dead stretch is left to scroll
// before the next scene. It only moves forward, stops at the scene's end, pauses while the visitor
// scrolls, and stays off for a scene the visitor has scrolled back in or paused Play in.
const AUTO_IDLE_MS = 700;
let lastInput = 0;
let autoY = null;
let lastY = 0;
const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);
addEventListener('wheel', event => { lastInput = performance.now(); if (event.deltaY < 0) scene.manual = true; }, { passive: true });
addEventListener('touchmove', () => { lastInput = performance.now(); }, { passive: true });
addEventListener('keydown', event => { if (SCROLL_KEYS.has(event.key)) lastInput = performance.now(); });

function measure() {
  const box = track.getBoundingClientRect();
  const position = clamp(-box.top / Math.max(1, box.height - innerHeight)) * timeline.total;
  const { step, t } = locate(timeline, Math.min(position, timeline.total - 1e-6));
  // The first scene waits until the stage is mostly on screen.
  // Self-scroll waits until the stage is pinned, so the landing view never scrolls away by itself.
  goal = { step, t, position, started: box.top < innerHeight * 0.45, pinned: box.top <= 1 };
}

// Milliseconds of unseen scenes queued between the one playing and `target`. The scene on stage
// always plays out (faster while the visitor is ahead), so a long one such as the login is never cut.
function waiting(target) {
  let total = 0;
  for (let index = scene.index + 1; index < target; index += 1) if (!seen.has(index)) total += duration(index);
  return total;
}

// A skip or a step back dims the stage first, swaps the scene while it is dim, then brightens it,
// so the change never shows as a cut.
let switching = false;
// Every scene plays again whenever it comes back on stage. Entered from its end (scrolling back),
// only the scroll made after entering speeds it up, so the replay is not skipped.
function apply(index) {
  const back = index < scene.index;
  scene.index = index;
  scene.ms = reducedMotion.matches ? duration(index) : 0;
  scene.waited = 0;
  scene.entered = performance.now();
  scene.entry = back && goal.step.index === index ? goal.t : 0;
  scene.manual = false;
}
function enter(index, fade) {
  if (switching) return;
  // A neighbouring step swaps at once, like turning a page; only a longer jump dips softly.
  if (!fade || Math.abs(index - scene.index) <= 1 || reducedMotion.matches || scene.index < 0) { apply(index); return; }
  switching = true;
  stageElement.animate([{ opacity: 1 }, { opacity: 0.6 }], { duration: 110, easing: 'ease-in', fill: 'forwards' }).finished.then(() => {
    measure();
    apply(goal.step.index);
    switching = false;
    for (const animation of stageElement.getAnimations()) animation.cancel();
    stageElement.animate([{ opacity: 0.6 }, { opacity: 1 }], { duration: 220, easing: 'cubic-bezier(.2, .7, .2, 1)' });
    update();
  });
}

function tick(now) {
  frame = 0;
  if (page !== 'tour') return;
  measure();
  const elapsed = lastTick ? Math.min(64, now - lastTick) : 0;
  lastTick = now;
  const target = goal.step.index;
  if (scene.index < 0) enter(target, false);
  // Stepping back one scene needs the scroll clearly inside it and the current scene on stage for a
  // moment, so quick back-and-forth at a boundary holds instead of flickering.
  else if (target < scene.index && (scene.index - target > 1 || (goal.position < timeline.steps[scene.index].start - BACK_GRACE && now - scene.entered > STAY_MS))) enter(target, true);
  else if (target > scene.index && waiting(target) > JUMP_MS) {
    for (let index = scene.index; index < target; index += 1) seen.add(index);
    enter(target, true);
  } else if (target > scene.index && scene.ms >= duration(scene.index)) {
    scene.waited += elapsed;
    if (scene.waited >= DWELL_MS) {
      // Scenes already watched are not replayed on the way; the stage fades past them.
      let next = scene.index + 1;
      while (next < target && seen.has(next)) next += 1;
      enter(next, next !== scene.index + 1);
    }
  }
  const total = duration(scene.index);
  if (scene.ms < total && goal.started) {
    let next = scene.ms + elapsed * (target > scene.index ? CATCH_UP : 1);
    const step = timeline.steps[scene.index];
    const span = Math.max(0.05, contentEnd(step) - scene.entry);
    const reached = target > scene.index ? total : Math.min(total, (Math.max(0, goal.t - scene.entry) / span) * total);
    if (reached > next) next += (reached - next) * Math.min(1, elapsed / FOLLOW_MS);
    scene.ms = Math.min(total, next);
  }
  // A scroll back the page did not make, or a pause, turns self-scroll off for this scene.
  if (scrollY < lastY - 2 && (autoY == null || Math.abs(scrollY - autoY) > 3)) scene.manual = true;
  const own = timeline.steps[scene.index];
  if (goal.pinned && total > 0 && !player.playing && !scene.manual && target === scene.index && now - lastInput > AUTO_IDLE_MS) {
    const end = contentEnd(own);
    const want = own.start + own.weight * (scene.entry + Math.max(0, end - scene.entry) * Math.min(1, scene.ms / total));
    if (want > goal.position + 0.0004) {
      autoY = positionY(want);
      scrollTo({ top: autoY, behavior: 'instant' });
    }
  }
  lastY = scrollY;
  if (scene.ms >= total) seen.add(scene.index);
  draw();
  if (scene.ms < total || target !== scene.index) frame = requestAnimationFrame(tick);
  else lastTick = 0;
}

function update() {
  lastDraw = '';
  lastTick = 0;
  frame ||= requestAnimationFrame(tick);
}

// The beat on screen follows the scroll, and a beat the visitor has just passed stays until
// they scroll back clearly past it. A scene the visitor has scrolled beyond shows its last beat.
function beatFor(step) {
  const beats = step.app ? step.guide ?? [] : [];
  if (!beats.length) return -1;
  let beat;
  if (goal.step.index > step.index) beat = beats.length - 1;
  else {
    beat = beats.findLastIndex(item => goal.t >= item.at);
    const previous = beatShown.get(step.index) ?? -1;
    if (beat < previous && goal.t > beats[previous].at - BEAT_GRACE) beat = previous;
  }
  beatShown.set(step.index, beat);
  return beat;
}

function draw() {
  const step = timeline.steps[scene.index];
  const beat = beatFor(step);
  // A finished scene keys as finished: its last frame may round to the same millisecond as the one before.
  const played = scene.ms >= duration(scene.index) ? 'done' : Math.round(scene.ms);
  const key = `${step.index}|${played}|${beat}|${goal.position.toFixed(4)}`;
  if (key === lastDraw) return;
  lastDraw = key;
  // Moving on to another scene hands the app back to the tour, so the guide picks up again.
  if (step.index !== lastStep && stage.embed.engaged) stage.embed.disengage();
  lastStep = step.index;
  stage.render(step, scene.ms, beat);
  if (captionTitle.textContent !== step.caption.title) {
    captionTitle.textContent = step.caption.title;
    if (!reducedMotion.matches) caption.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.2, .7, .2, 1)' });
  }
  if (captionLine.textContent !== step.caption.line) captionLine.textContent = step.caption.line;
  // At the end of the story, once its last beat is on screen, the way on rises in over the last frame.
  const lastBeat = (step.guide?.length ?? 0) - 1;
  const ending = scene.index === timeline.steps.length - 1 && beat === lastBeat && goal.position > timeline.total - 0.12;
  if (finish.classList.contains('is-visible') !== ending) {
    finish.classList.toggle('is-visible', ending);
    finish.tabIndex = ending ? 0 : -1;
    finish.setAttribute('aria-hidden', String(!ending));
  }
  // The playback bar follows the scroll exactly, so it never jumps when the stage changes scene.
  const position = goal.position;
  for (const [index, segment] of segments.entries()) {
    const chapter = timeline.chapters[index];
    const end = timeline.chapters[index + 1]?.start ?? timeline.total;
    segment.style.setProperty('--fill', String(clamp((position - chapter.start) / (end - chapter.start))));
    if (index === goal.step.chapterIndex) segment.setAttribute('aria-current', 'step');
    else segment.removeAttribute('aria-current');
  }
  player.show(position, goal.step);
}

// Play: the clock may move only as far as the stage has shown. It waits at each guide beat until
// the beat before has finished and stayed a moment, and at each step's end until the scene and
// its last beat are done, so nothing is skipped or rushed however slow the app is.
const HOLD_MS = 1400;
const PASSING_HOLD_MS = 250;
const END_HOLD_MS = 2000;
let held = { key: '', beat: -2, at: 0 };
function beatHeld(step, index, hold) {
  const shown = stage.embed.shown;
  const now = performance.now();
  if (shown && (shown.key !== held.key || shown.beat !== held.beat)) held = { ...shown, at: now };
  return Boolean(shown) && shown.key === step.key && shown.beat >= index && (shown.beat > index || now - held.at >= hold);
}
function sceneDone(step) {
  return scene.index === step.index && scene.ms >= duration(step.index) && !switching;
}
function limit(position) {
  const { step, t } = locate(timeline, Math.min(position, timeline.total - 1e-6));
  const beats = step.app ? step.guide ?? [] : [];
  const next = beats.findIndex(beat => beat.at > t + 1e-9);
  // Waiting stops a few pixels short, so a rounded scroll position never shows the next beat early.
  const stop = (next >= 0 ? step.start + step.weight * beats[next].at : step.start + step.weight) - 0.006;
  let ready;
  if (next === 0) ready = sceneDone(step);
  else if (next > 0) ready = beatHeld(step, next - 1, beats[next - 1].opens || beats[next - 1].route ? PASSING_HOLD_MS : HOLD_MS);
  else ready = sceneDone(step) && (!beats.length || beatHeld(step, beats.length - 1, END_HOLD_MS));
  return ready ? Infinity : Math.max(position, stop);
}
const lastStepIndex = timeline.steps.length - 1;
const player = createPlayer({
  timeline,
  button: document.querySelector('[data-play]'),
  bar: document.querySelector('[data-bar]'),
  status: document.querySelector('[data-player-status]'),
  positionY,
  current: () => { measure(); return goal.position; },
  limit,
  ended: position => position >= timeline.total - 2e-6 && limit(position) === Infinity && scene.index === lastStepIndex,
  // A pause hands the page back to the visitor: no self-scroll for the scene on stage.
  onPause: () => { scene.manual = true; },
  // Watching again replays every scene rather than showing them finished.
  onRestart: () => { seen.clear(); beatShown.clear(); },
});
// Handing the app over, leaving the tour page or opening the disclaimer pauses the tour.
document.addEventListener('pointerdown', event => { if (event.target.closest('.app-shield')) player.pause(); }, true);
// Two pages in one file: the story and Get started. A view transition carries the clicked
// button into the new page's heading; without view transitions, the pages simply swap.
const pages = { tour: document.querySelector('[data-page="tour"]'), start: document.querySelector('[data-page="start"]') };
const startHeading = document.getElementById('start-title');
const pageFor = hash => (hash === '#get-started' ? 'start' : 'tour');
let tourScroll = 0;
// On Get started, the header's Get started button becomes the way back, in the same place.
const cta = document.querySelector('[data-cta]');
const ctaLabel = cta.querySelector('[data-cta-label]');
function setCta(name) {
  const back = name === 'start';
  if (cta.classList.contains('is-back') === back) return;
  cta.classList.toggle('is-back', back);
  cta.dataset.pageLink = back ? '#tour' : '#get-started';
  ctaLabel.textContent = back ? 'Back to tour' : 'Get started';
  cta.classList.remove('is-swapping');
  if (!reducedMotion.matches) { void cta.offsetWidth; cta.classList.add('is-swapping'); }
}
function swap(name) {
  if (page === 'tour') tourScroll = scrollY;
  page = name;
  setCta(name);
  pages.tour.hidden = name !== 'tour';
  pages.start.hidden = name !== 'start';
  pages.tour.inert = name !== 'tour';
  if (name === 'tour') stage.embed.resume(); else stage.embed.suspend();
  root.dataset.page = name;
  scrollTo({ top: name === 'tour' ? tourScroll : 0, behavior: 'instant' });
  if (name === 'tour') update(); else startHeading.focus({ preventScroll: true });
}
function go(name, source = null) {
  if (name === page) return;
  player.pause();
  if (stage.embed.engaged) stage.embed.disengage();
  root.dataset.direction = name === 'start' ? 'forward' : 'back';
  if (!document.startViewTransition || reducedMotion.matches) { swap(name); return; }
  const morph = name === 'start' && source;
  if (morph) source.style.viewTransitionName = 'page-cta';
  const transition = document.startViewTransition(() => {
    if (morph) { source.style.viewTransitionName = ''; startHeading.style.viewTransitionName = 'page-cta'; }
    swap(name);
  });
  transition.finished.finally(() => { startHeading.style.viewTransitionName = ''; });
}
for (const link of document.querySelectorAll('[data-page-link]')) {
  link.addEventListener('click', event => {
    const target = link.dataset.pageLink;
    if (pageFor(target) === page) return;
    history.pushState(null, '', target);
    go(pageFor(target), link);
  });
}
// The page restores the story's scroll position itself when the visitor comes back.
history.scrollRestoration = 'manual';
addEventListener('popstate', () => go(pageFor(location.hash)));
if (pageFor(location.hash) === 'start') swap('start');

// Start the tour glides down to the stage and starts hands-free play there.
document.querySelector('[data-start-tour]').addEventListener('click', () => {
  const top = positionY(0);
  if (reducedMotion.matches || Math.abs(scrollY - top) < 4) { player.play(); return; }
  let started = false;
  const begin = () => { if (started) return; started = true; player.play(); };
  addEventListener('scrollend', begin, { once: true });
  setTimeout(begin, 1200);
  scrollTo({ top, behavior: 'smooth' });
});

const disclaimer = document.querySelector('[data-disclaimer]');
document.querySelector('[data-disclaimer-close]').append(stroke('close', 16));
document.querySelector('[data-disclaimer-open]').addEventListener('click', () => { player.pause(); disclaimer.showModal(); });
document.querySelector('[data-disclaimer-close]').addEventListener('click', () => disclaimer.close());
disclaimer.addEventListener('click', event => { if (event.target === disclaimer) disclaimer.close(); });

const schedule = () => { frame ||= requestAnimationFrame(tick); };
addEventListener('scroll', schedule, { passive: true });
addEventListener('resize', schedule);
reducedMotion.addEventListener('change', update);
update();

// Copy buttons show a copy icon that turns into a check once the command is on the clipboard.
// Where the clipboard is blocked, the command is selected instead, ready for the visitor to copy.
for (const button of document.querySelectorAll('[data-copy]')) {
  const label = button.dataset.copyLabel ?? button.getAttribute('aria-label');
  button.querySelector('[data-copy-label]').append(stroke('copy', 16), stroke('check', 16));
  let timer = 0;
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.classList.add('is-copied');
      button.setAttribute('aria-label', 'Copied');
      clearTimeout(timer);
      timer = setTimeout(() => { button.classList.remove('is-copied'); button.setAttribute('aria-label', label); }, 1600);
    } catch {
      getSelection().selectAllChildren(button.closest('li')?.querySelector('code') ?? button.querySelector('code'));
    }
  });
}
