import { h } from '../ui/dom.js';
import { stroke } from '../ui/icons.js';
import { createGuide } from './guide.js';

const THEME_KEY = 'study-space:theme';
const TRAVEL_MS = 640;
// Room kept under a walkthrough's control for the guide's callout.
const CALLOUT_ROOM = 96;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const frames = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

// The live study app runs in a same-origin srcdoc frame. Until the visitor clicks into it,
// the tour drives it and keeps keyboard focus on the page; once engaged, it is theirs.
export function createAppEmbed({ documentText, stage, onEngage }) {
  const frame = h('iframe.app-frame', { title: 'Graph Search study app, live', tabindex: '-1', loading: 'eager' });
  const guide = createGuide({ topInset: () => (loaded ? viewOf(win().document.scrollingElement).top : 0) });
  const shield = h('button.app-shield', { type: 'button', 'aria-label': 'Use the study app' });
  const resume = h('button.resume', { type: 'button' }, stroke('arrow', 16), h('span', { text: 'Resume tour' }));
  const element = h('div.app-slot', {}, frame, guide.element, shield, resume);
  let loaded = false;
  let requested = false;
  let engaged = false;
  let theme = 'light';
  let request = null;
  let quiet = false;
  let wanted = null;
  let applied = null;
  // While the tour page is away (Get started), no new beat starts; one in progress finishes.
  let suspended = false;
  let run = 0;
  // A newer scene, a hand-over or a refresh ends the previous scene's waits within a frame,
  // so the guide never trails the scroll by a pointer move or an app scroll.
  let wake = () => {};
  let superseded = new Promise(resolve => { wake = resolve; });
  function supersede() {
    run += 1;
    wake();
    superseded = new Promise(resolve => { wake = resolve; });
    return run;
  }
  const rest = ms => Promise.race([pause(ms), superseded]);
  let pressed = [];

  const win = () => frame.contentWindow;
  let outerFocus = null;
  document.addEventListener('focusin', event => { if (event.target !== frame) outerFocus = event.target; });
  const releaseFocus = () => {
    if (engaged || !loaded) return;
    win().document.activeElement?.blur?.();
    // The app moves focus into itself when the guide clicks (a panel's close button, a new page).
    // Focus goes back where the visitor last had it on the page (the playback bar, say), else the stage.
    if (document.activeElement !== frame && document.activeElement !== document.body) return;
    (outerFocus?.isConnected && outerFocus !== document.body ? outerFocus : stage).focus({ preventScroll: true });
  };

  // A target may list alternatives, such as a phone layout's version of a control; the first on screen wins.
  function match(target) {
    if (Array.isArray(target)) return target.reduce((found, option) => found ?? match(option), null);
    // Content of a closed <details> still reports boxes in WebKit; it is not on screen.
    const shown = item => item.getClientRects().length && !item.closest('details:not([open]) > :not(summary)');
    const candidates = [...win().document.querySelectorAll(target.css)].filter(shown);
    const matching = target.text ? candidates.filter(item => new RegExp(target.text).test(item.textContent.trim())) : candidates;
    return matching[target.nth ?? 0] ?? null;
  }

  function find(target, timeout = 900) {
    const found = match(target);
    if (found || !timeout) return Promise.resolve(found);
    return new Promise(resolve => {
      const watcher = new MutationObserver(() => {
        const item = match(target);
        if (item) { watcher.disconnect(); clearTimeout(timer); resolve(item); }
      });
      const timer = setTimeout(() => { watcher.disconnect(); resolve(null); }, timeout);
      watcher.observe(win().document.body, { childList: true, subtree: true, attributes: true });
    });
  }

  // scrollIntoView would also scroll the tour page; move only the app's own scroll container.
  function scroller(item) {
    let box = item.parentElement;
    while (box && !(box.scrollHeight > box.clientHeight && /auto|scroll/.test(win().getComputedStyle(box).overflowY))) box = box.parentElement;
    return box ?? win().document.scrollingElement;
  }

  // On phones the app's sidebar is a sticky top bar, so the page's view starts below it and a
  // target is never scrolled underneath it.
  function viewOf(box) {
    const doc = win().document;
    if (box !== doc.scrollingElement) return { top: box.getBoundingClientRect().top, height: box.clientHeight };
    const bar = doc.querySelector('.sidebar')?.getBoundingClientRect();
    const top = bar && bar.top <= 1 && bar.height < win().innerHeight / 3 && win().getComputedStyle(doc.querySelector('.sidebar')).position === 'sticky' ? bar.bottom : 0;
    return { top, height: win().innerHeight - top };
  }

  // The app's scroll containers use CSS smooth scrolling; every scroll the guide makes is
  // instant, so its own easing is the only motion and measurements see the final position.
  const jump = (box, top) => box.scrollTo({ top, behavior: 'instant' });

  function alignTop(item) {
    const box = scroller(item);
    jump(box, box.scrollTop + item.getBoundingClientRect().top - viewOf(box).top - 24);
  }

  // The guide scrolls the app itself with an eased curve of known length, the same in every
  // browser, so the next move starts as soon as the content settles.
  function glide(box, top, smooth, live) {
    const from = box.scrollTop;
    const to = Math.max(0, Math.min(top, box.scrollHeight - box.clientHeight));
    const distance = Math.abs(to - from);
    if (!smooth || distance < 2) { jump(box, to); return Promise.resolve(); }
    // Long distances take longer, so the app never races past (about 1.6 px per ms at most).
    const duration = Math.min(1100, Math.max(320 + distance * 0.35, distance / 1.6));
    const ease = x => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);
    return new Promise(resolve => {
      const start = performance.now();
      const step = now => {
        if (!live()) { resolve(); return; }
        const progress = Math.min(1, (now - start) / duration);
        jump(box, from + (to - from) * ease(progress));
        if (progress < 1) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });
  }

  // Keeps the target in the upper part of the view, leaving room for the callout below it.
  // While the content moves, the ring and callout lift away and the pointer rests in place.
  async function bringIntoView(item, smooth, live) {
    const box = scroller(item);
    // A scroll box inside the page (a map, a wide table) first shows the item within itself.
    if (box !== win().document.scrollingElement && box.parentElement) {
      const outer = scroller(box);
      if (outer !== box && outer.scrollHeight > outer.clientHeight + 1) {
        const inner = viewOf(box);
        const rect = item.getBoundingClientRect();
        const below = rect.bottom - (inner.top + inner.height);
        const above = rect.top - inner.top;
        if (above < 0 || below > 0) { guide.lift(); jump(box, box.scrollTop + (above < 0 ? above - 8 : below + 8)); }
        await bringIntoView(box, smooth, live);
        return;
      }
    }
    const view = viewOf(box);
    const rect = item.getBoundingClientRect();
    const offset = rect.top - view.top;
    // A control in the sticky top bar stays put whatever the page does.
    if (rect.bottom <= view.top && item.closest('.sidebar')) return;
    // A control of a walkthrough frames the whole walkthrough from its top: the visual that changes
    // and the step bar together, with room for the callout below the control.
    const walk = item.closest('.walk')?.getBoundingClientRect();
    const framed = walk
      ? walk.top >= view.top && rect.bottom + CALLOUT_ROOM <= view.top + view.height
      : offset >= view.height * 0.1 && offset + Math.min(rect.height, view.height * 0.4) <= view.height * 0.66;
    const want = framed ? box.scrollTop : box.scrollTop + (walk ? walk.top - view.top - 8 : offset - view.height * 0.24);
    const top = clearRow(box, view, want, rect);
    if (Math.abs(top - box.scrollTop) < 2) return;
    guide.lift();
    await glide(box, top, smooth, live);
  }

  // The view's top edge never cuts a row (a tab bar, a card's header) in half: the row shows whole
  // when the target still fits below it, else it scrolls out of view.
  function clearRow(box, view, top, target) {
    const end = box.scrollHeight - box.clientHeight;
    top = Math.max(0, Math.min(top, end));
    for (let pass = 0; pass < 3; pass += 1) {
      const line = view.top + top - box.scrollTop;
      const row = rowAt(line, view);
      if (!row) break;
      const above = Math.max(0, top - (line - row.top) - 8);
      const past = top + (row.bottom - line) + 1;
      // Near the page's end the row cannot scroll out, so it shows whole instead.
      top = past > end || target.bottom - (above - box.scrollTop) <= view.top + view.height ? above : past;
    }
    return top;
  }

  // The largest row the line crosses: an element short enough to be a row, or a line of text.
  function rowAt(line, view) {
    const doc = win().document;
    const crosses = rect => rect.top < line - 1 && rect.bottom > line + 1 && rect.height < view.height * 0.3;
    let row = null;
    const consider = rect => { if (crosses(rect) && (!row || rect.height > row.height)) row = rect; };
    for (const element of doc.querySelectorAll('main *')) consider(element.getBoundingClientRect());
    const texts = doc.createTreeWalker(doc.querySelector('main') ?? doc.body, NodeFilter.SHOW_TEXT);
    const range = doc.createRange();
    for (let text = texts.nextNode(); text; text = texts.nextNode()) {
      const parent = text.parentElement.getBoundingClientRect();
      if (parent.top > line || parent.bottom < line || !text.data.trim()) continue;
      range.selectNodeContents(text);
      for (const rect of range.getClientRects()) consider(rect);
    }
    return row;
  }

  // What the visitor sees as the control: a link's text rather than its tall tap area, and the
  // square around a small drawn control such as a step dot.
  function outline(item) {
    const rect = item.getBoundingClientRect();
    const style = win().getComputedStyle(item);
    const bare = !(item instanceof win().SVGElement) && style.backgroundColor === 'rgba(0, 0, 0, 0)' && Number.parseFloat(style.borderTopWidth) === 0;
    if (!bare) return rect;
    // WebKit misplaces text ranges inside buttons, so only links and similar elements hug their text.
    if (item.textContent.trim() && item.tagName !== 'BUTTON') {
      const range = win().document.createRange();
      range.selectNodeContents(item);
      const text = range.getBoundingClientRect();
      if (text.width && text.height) return text;
    }
    if (item.textContent.trim()) return rect;
    const side = Math.min(rect.width, rect.height);
    return new DOMRect(rect.left + (rect.width - side) / 2, rect.top + (rect.height - side) / 2, side, side);
  }

  // A real click starts with pointerdown, which also closes any open bubble the app shows. A toggle
  // already on stays on, since the app keeps toggle state when the visitor browses away and back.
  function click(hash, target, item) {
    const state = item.getAttribute('aria-pressed');
    if (state === 'true') return;
    if (item.tagName === 'SUMMARY' && item.parentElement.open) return;
    if (state === 'false') pressed.push({ hash, target });
    // The app toggles its menus' summaries on pointerdown as well; they get the click alone.
    if (item.tagName !== 'SUMMARY') item.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    item.click();
  }

  // Closes what the previous beat left open: bubbles close on pointerdown as a click elsewhere
  // would, and panels such as Recall's lesson panel (a dialog the app closes only on its close
  // button or a page change) are closed directly, so they never cover the next beat or scene.
  function dismiss() {
    const doc = win().document;
    doc.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    // The Ask agent panel stays open across its scene's beats; a rebuild closes it.
    doc.querySelectorAll('dialog[open]:not(.ask-panel)').forEach(dialog => dialog.close());
  }

  // Returns the app to the route's first view: dialogs closed, toggles the guide switched on
  // switched off, the visit's answers and scroll positions forgotten, the route rendered anew.
  async function rebuild(hash) {
    // A scene that ran the Ask agent demo changed the course in the frame; a fresh frame undoes it.
    if (win().__askDemo?.used) await reload();
    const w = win();
    const doc = w.document;
    doc.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    const savedTheme = w.localStorage.getItem(THEME_KEY);
    w.localStorage.clear();
    if (savedTheme) w.localStorage.setItem(THEME_KEY, savedTheme);
    // The app renders in its own hashchange handler, registered before this one.
    const rendered = new Promise(resolve => w.addEventListener('hashchange', resolve, { once: true }));
    if (w.location.hash === hash) w.dispatchEvent(new HashChangeEvent('hashchange'));
    else w.location.hash = hash;
    await rendered;
    await frames();
    unpress(hash);
    const main = doc.querySelector('main');
    if (main) jump(main, 0);
    jump(doc.scrollingElement, 0);
  }

  // A beat that switches pages names where its click leads. If the click could not happen (the
  // control is hidden in a phone layout, say), the guide goes there itself so the story stays whole.
  const sameRoute = (a, b) => a.replace(/^#study\//, '#') === b.replace(/^#study\//, '#');
  async function settleRoute(route) {
    if (!route) return;
    const w = win();
    await frames();
    if (!sameRoute(w.location.hash, route)) {
      const changed = new Promise(resolve => w.addEventListener('hashchange', resolve, { once: true }));
      w.location.hash = route;
      await changed;
      await frames();
    }
    unpress(route);
  }

  // The app keeps toggle state per page; toggles the guide switched on there earlier are
  // switched off whenever the guide arrives on that page again.
  function unpress(route) {
    for (const entry of pressed.filter(item => sameRoute(item.hash, route))) {
      const toggle = match(entry.target);
      if (toggle?.getAttribute('aria-pressed') === 'true') toggle.click();
    }
    pressed = pressed.filter(item => !sameRoute(item.hash, route));
  }

  // The app's content fades in after a page change; measure only once it has landed.
  async function landed() {
    const running = win().document.querySelector('main')?.getAnimations() ?? [];
    await Promise.all(running.map(animation => animation.finished.catch(() => {})));
  }

  // On a phone the sidebar, and the workspace switcher in it, sits behind the menu button. A beat
  // that opens the switcher taps that button first, as a visitor would, and closes it after the switch.
  let openedSidebar = false;
  const inSidebar = beat => beat.opens || [beat.target].flat(2).some(target => /^aside\b/.test(target?.css ?? ''));
  async function revealSidebar(beat, scene, animate, live) {
    const toggle = match({ css: 'button.outline-toggle' });
    if (!toggle || toggle.getAttribute('aria-expanded') === 'true') return null;
    if (animate) {
      guide.place(outline(toggle), beat, { animate, index: scene.beat, count: scene.beats.length, measure: () => (toggle.isConnected ? outline(toggle) : null) });
      await rest(TRAVEL_MS);
      if (!live()) return null;
      guide.press({ quiet: false });
    }
    toggle.click();
    openedSidebar = true;
    await frames();
    await pause(animate ? 280 : 0);
    return find(beat.target);
  }

  function closeSidebar() {
    if (!openedSidebar) return;
    openedSidebar = false;
    const toggle = match({ css: 'button.outline-toggle' });
    if (toggle?.getAttribute('aria-expanded') === 'true') toggle.click();
  }

  // A beat with `type` types its text into the field, as the visitor would; silent rebuilds fill it at once.
  // Typing follows the clock frame by frame, at about 30 characters a second.
  async function typeInto(item, text, animate, live) {
    const put = value => { item.value = value; item.dispatchEvent(new (win().Event)('input', { bubbles: true })); };
    if (!animate || reducedMotion.matches) { put(text); return; }
    const start = performance.now();
    for (let shown = 0; shown < text.length;) {
      await new Promise(requestAnimationFrame);
      if (!live()) return;
      const length = Math.min(text.length, Math.floor((performance.now() - start) / 34) + 1);
      if (length !== shown) { put(text.slice(0, length)); shown = length; }
    }
  }

  // Returns false when a newer scene took over before the beat finished.
  async function playBeat(scene, id, animate) {
    const beat = scene.beats[scene.beat];
    const live = () => id === run && !engaged;
    // Moving on closes the previous beat's bubble before anything is measured, as the next
    // click would; a bubble closing later would shift the layout under the ring.
    // A beat that opened a menu (the workspace switcher) leaves it open for the next beat to use.
    if (!scene.beats[scene.beat - 1]?.opens) dismiss();
    await landed();
    // `wait` gives a beat longer to find its control, such as the result of the agent's work.
    let item = await find(beat.target, beat.wait ?? (inSidebar(beat) ? 300 : 900));
    const revealed = !item && inSidebar(beat) && live();
    if (revealed) item = await revealSidebar(beat, scene, animate, live);
    if (!live()) return false;
    if (!item) { guide.hide(); await settleRoute(beat.route); closeSidebar(); return true; }
    await bringIntoView(item, animate && !reducedMotion.matches, live);
    if (!live()) return false;
    // In a walkthrough the click changes the visual above the control, so the callout goes below.
    guide.place(outline(item), item.closest('.walk') && !beat.place ? { ...beat, place: 'below' } : beat, { animate, index: scene.beat, count: scene.beats.length, measure: () => (item.isConnected ? outline(item) : null) });
    if (beat.type) {
      if (animate) await rest(TRAVEL_MS);
      if (!live()) return false;
      await typeInto(item, beat.type, animate, live);
      if (!live()) return false;
    }
    if (!beat.click) return true;
    if (animate) await rest(TRAVEL_MS);
    if (!live()) return false;
    guide.press({ quiet: !animate });
    // A click that changes page lets the old page fade out first, so the new one fades in from a dip, not a cut.
    if (beat.route && animate && !reducedMotion.matches) {
      await pause(240);
      await win().document.querySelector('main')?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 160, easing: 'ease-in', fill: 'forwards' }).finished;
      if (!live()) return false;
    }
    click(scene.hash, beat.target, item);
    if (beat.route) {
      await settleRoute(beat.route);
      closeSidebar();
      // A fade-out still holding means no page change happened; the page must not stay hidden.
      for (const held of win().document.querySelector('main')?.getAnimations() ?? []) if (held.effect?.getTiming().fill === 'forwards') held.cancel();
      if (!live()) return false;
      // The control the click used is gone with the old page; the ring moves to the new page's title.
      await landed();
      const heading = match({ css: 'main h1' }) ?? match({ css: 'main h2' });
      if (heading && live()) guide.follow(outline(heading), beat, () => (heading.isConnected ? outline(heading) : null), animate);
      return true;
    }
    if (!beat.after) {
      await frames();
      if (!live()) return false;
      // The lens stays on a control clicked in place.
      if (item.isConnected && beat.opens) guide.follow(outline(item), beat, () => (item.isConnected ? outline(item) : null), animate);
      return true;
    }
    const result = await find(beat.after, beat.wait ?? 1500);
    if (!live()) return false;
    // On a phone the switcher opens inside the revealed sidebar, so the lens stays on it and goes
    // straight to the workspace next, as on a desktop, rather than widening over the whole menu.
    if (result && !(revealed && beat.opens)) {
      if (animate) await rest(TRAVEL_MS / 2);
      if (!live()) return false;
      // What the click revealed may sit under the app's sticky bar or below the view.
      await bringIntoView(result, animate && !reducedMotion.matches, live);
      if (!live()) return false;
      guide.follow(outline(result), beat, () => (result.isConnected ? outline(result) : null), animate);
    }
    return true;
  }

  // A scene is one story step's route plus the guide beat the scroll asks for. The driver walks
  // towards it calmly: each forward beat plays to the end and stays on screen for a moment
  // before the next; going back, or more than two beats ahead, fades the app out, rebuilds the
  // state silently and fades it back in, so the visitor never sees the app rewind or race.
  // A new scene that starts on the page the app already shows simply carries on from there.
  const DWELL_MS = 900;
  const PASSING_MS = 320;
  const AHEAD = 2;
  // Clicks that open a menu or change page are one motion with the beat that follows: they
  // pause only briefly, and do not count when deciding whether the scroll has run far ahead.
  const passing = beat => Boolean(beat?.opens || beat?.route);
  const ahead = (beats, from, to) => beats.slice(from + 1, to + 1).filter(beat => !passing(beat)).length;
  let driving = false;
  let lastBeatAt = 0;
  // Resolves when the scroll asks for something else, so a step back never waits out a dwell.
  let announce = () => {};
  let changed = new Promise(resolve => { announce = resolve; });
  const renew = () => { changed = new Promise(resolve => { announce = resolve; }); };

  // Fades the app out around silent work. When the scroll has already asked for something
  // else, it stays faded so back-to-back rebuilds never flicker in and out.
  async function fade(work, goal) {
    const visible = !reducedMotion.matches && element.offsetParent && stage.querySelector('.bw.is-open');
    if (visible && !element.classList.contains('is-fading')) {
      element.style.setProperty('--app-backdrop', win().getComputedStyle(win().document.body).backgroundColor);
      element.classList.add('is-fading');
      await pause(180);
    }
    try {
      await work();
    } finally {
      if (wanted === goal || engaged) element.classList.remove('is-fading');
    }
  }

  async function unfade() {
    if (!element.classList.contains('is-fading')) return;
    element.classList.remove('is-fading');
    await pause(280);
  }

  async function rebuildTo(goal, id, beat) {
    guide.hide();
    quiet = true;
    try {
      await rebuild(goal.scene.start ?? goal.scene.hash);
      if (id !== run) return false;
      await replay({ ...goal.scene, beat }, id);
      if (id !== run) return false;
      if (beat >= 0 && !(await playBeat({ ...goal.scene, beat }, id, false))) return false;
    } finally {
      quiet = false;
      const demo = win().__askDemo;
      if (demo) demo.instant = false;
    }
    return id === run;
  }

  async function drive() {
    if (driving) return;
    driving = true;
    try {
      while (wanted && !engaged && !suspended) {
        const goal = wanted;
        const id = run;
        if (applied?.base === goal.base && applied.beat === goal.beat) break;
        renew();
        if (applied && applied.base !== goal.base && sameRoute(win().location.hash, goal.scene.start ?? goal.scene.hash)) {
          dismiss();
          guide.hide();
          applied = { base: goal.base, beat: -1 };
          continue;
        }
        const from = applied?.base === goal.base ? applied.beat : null;
        const beats = goal.scene.beats;
        if (from != null && goal.beat > from && ahead(beats, from, goal.beat) <= AHEAD) {
          const wait = (from >= 0 && passing(beats[from]) ? PASSING_MS : DWELL_MS) - (performance.now() - lastBeatAt);
          if (wait > 0) await Promise.race([rest(wait), changed]);
          if (id !== run || engaged) continue;
          if (wanted !== goal) continue;
          await unfade();
          const scene = { ...goal.scene, beat: from + 1 };
          applied = null;
          if (!(await playBeat(scene, id, true))) continue;
          applied = { base: goal.base, beat: scene.beat };
          lastBeatAt = performance.now();
          if (!scene.beats[scene.beat]?.opens) releaseFocus();
          continue;
        }
        // Arriving ahead of where the beats are, the app shows the beat before and then plays the last one.
        const landing = ahead(beats, from ?? -1, goal.beat) > AHEAD ? goal.beat - 1 : goal.beat;
        applied = null;
        let done = false;
        await fade(async () => { done = await rebuildTo(goal, id, landing); }, goal);
        if (!done) continue;
        applied = { base: goal.base, beat: landing };
        lastBeatAt = performance.now();
        if (!goal.scene.beats[landing]?.opens) releaseFocus();
      }
    } catch (error) {
      applied = null;
      reportError(error);
    } finally {
      driving = false;
      if (!wanted || engaged || (applied?.base === wanted.base && applied.beat === wanted.beat)) element.classList.remove('is-fading');
    }
  }

  // Rebuilds the beats before the current one without motion: their clicks and the pages they reach.
  async function replay(scene, id) {
    if (scene.scroll) {
      const anchor = await find({ css: scene.scroll });
      if (id !== run) return;
      if (anchor) alignTop(anchor);
    }
    const demo = win().__askDemo;
    if (demo) demo.instant = true;
    for (const beat of scene.beats.slice(0, Math.max(scene.beat, 0))) {
      if (!beat.click && !beat.type) continue;
      let item = await find(beat.target, beat.wait ?? (inSidebar(beat) ? 300 : 900));
      if (!item && inSidebar(beat)) item = await revealSidebar(beat, scene, false, () => id === run);
      if (id !== run) return;
      if (item && beat.type) await typeInto(item, beat.type, false, () => true);
      if (item && beat.click) click(scene.hash, beat.target, item);
      await settleRoute(beat.route);
      if (beat.route) closeSidebar();
      await frames();
    }
  }

  function present(scene) {
    const base = `${scene.key}|${scene.hash}|${scene.scroll ?? ''}`;
    if (wanted?.base === base && wanted.beat === scene.beat) return;
    wanted = { base, beat: scene.beat, scene };
    announce();
    drive();
  }

  function show(hash, { key = '', start = null, scroll = null, beats = [], beat = -1 } = {}) {
    if (!hash) return;
    request = { key, hash, start, scroll, beats, beat };
    if (!loaded) { load(); return; }
    if (!engaged) present(request);
  }

  function refresh() {
    wanted = null;
    applied = null;
    supersede();
    guide.hide();
    if (request && !engaged) present(request);
  }

  function applyTheme() {
    if (!loaded) return;
    const doc = win().document;
    if (doc.documentElement.dataset.theme === theme) return;
    win().localStorage.setItem(THEME_KEY, JSON.stringify(theme));
    doc.documentElement.dataset.theme = theme;
    if (request && !engaged) refresh();
    else win().dispatchEvent(new HashChangeEvent('hashchange'));
  }

  // Loads the app afresh in the frame, keeping the tour's own state.
  function reload() {
    return new Promise(resolve => {
      frame.addEventListener('load', () => { prepare(); resolve(); }, { once: true });
      frame.srcdoc = documentText();
    });
  }

  function onLoad() {
    prepare();
    if (request) present(request);
    else releaseFocus();
  }

  function prepare() {
    loaded = true;
    const doc = win().document;
    doc.head.append(Object.assign(doc.createElement('style'), { textContent: 'html, body, main, .sidebar-body { overscroll-behavior: contain; }' }));
    win().addEventListener('keydown', event => { if (event.key === 'Escape') disengage(); });
    // Only a real change of size moves the beat's measurements. A hidden page (Get started) shrinks
    // the frame to nothing and back, which must leave the app exactly where it was.
    let size = `${win().innerWidth}x${win().innerHeight}`;
    win().addEventListener('resize', () => {
      if (!win().innerWidth || !win().innerHeight) return;
      const next = `${win().innerWidth}x${win().innerHeight}`;
      if (next === size) return;
      size = next;
      if (applied?.beat >= 0 && !engaged) refresh();
    });
    // Registered after the app's own handler, so it animates the page the app just rendered.
    win().addEventListener('hashchange', () => {
      const main = doc.querySelector('main');
      main?.getAnimations().forEach(animation => animation.cancel());
      if (quiet || reducedMotion.matches) return;
      main?.animate(
        [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }],
        { duration: 360, easing: 'cubic-bezier(.2, .7, .2, 1)' },
      );
    });
    win().localStorage.setItem(THEME_KEY, JSON.stringify(theme));
    doc.documentElement.dataset.theme = theme;
  }

  function load() {
    if (requested) return;
    requested = true;
    frame.addEventListener('load', onLoad, { once: true });
    frame.srcdoc = documentText();
  }

  function engage(event) {
    if (engaged) return;
    engaged = true;
    supersede();
    guide.hide();
    stage.classList.add('is-engaged');
    frame.tabIndex = 0;
    onEngage?.(true);
    frame.focus();
    // A pointer click also activates what it landed on; a keyboard click (detail 0) only hands over focus.
    if (event?.detail > 0) {
      const box = frame.getBoundingClientRect();
      const scale = box.width / frame.offsetWidth;
      const target = win().document.elementFromPoint((event.clientX - box.left) / scale, (event.clientY - box.top) / scale);
      target?.closest('a, button, summary, label, input')?.click();
    }
  }

  function disengage() {
    if (!engaged) return;
    engaged = false;
    wanted = null;
    applied = null;
    stage.classList.remove('is-engaged');
    frame.tabIndex = -1;
    onEngage?.(false);
    stage.focus({ preventScroll: true });
  }

  shield.addEventListener('click', engage);
  resume.addEventListener('click', disengage);
  document.addEventListener('pointerdown', event => { if (engaged && !element.contains(event.target)) disengage(); });
  document.addEventListener('keydown', event => { if (engaged && event.key === 'Escape') disengage(); });

  return {
    element,
    load,
    show,
    setTheme(value) { theme = value; applyTheme(); },
    get engaged() { return engaged; },
    // The beat that has finished playing, for the player's clock to wait on.
    get shown() { return applied ? { key: applied.base.split('|')[0], beat: applied.beat } : null; },
    suspend() { suspended = true; },
    resume() { suspended = false; drive(); },
    disengage,
  };
}
