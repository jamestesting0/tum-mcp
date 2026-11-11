import { h, replace } from '../ui/dom.js';

// The sign-in scene's mouse pointer (a person signing in); the guide itself uses the lens below.
export const POINTER = '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path d="M5 2.8 19 11.3l-6.1 1.4 3.7 7.1-2.8 1.5-3.7-7.2L5 18.4Z" fill="#101418" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
const GAP = 12;
const PAD = 6;
const SWAP_MS = 170;
const DISC = 22;
const EASE = 'cubic-bezier(.45, 0, .2, 1)';
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

// The tour's lens and callout over the live app. The layer shares the frame's coordinate space,
// so rectangles measured in the app document place it directly. The lens is one shape: it travels
// as a small accent disc, widens into the highlight around each control (dimming the rest) and
// stays wrapped around it, following it as the app moves. The dimming stays steady while the guide
// shows; after a click the lens glides on to whatever the click revealed.
export function createGuide() {
  const ring = h('div.guide-ring');
  const label = h('strong');
  const line = h('span');
  const dots = h('span.guide-dots', { 'aria-hidden': 'true' });
  const callout = h('div.guide-callout', { role: 'status' }, h('div.guide-text', {}, label, line), dots);
  const element = h('div.guide', {}, ring, callout);
  let swaps = 0;
  let tip = { x: 0, y: 0 };
  let wrapped = false;
  let current = null;
  let stages = [];
  let follow = null;

  // Click beats default to a callout above the control, since what the click opens appears below it.
  function moveCallout(rect, beat) {
    const box = { width: callout.offsetWidth, height: callout.offsetHeight };
    const above = rect.top - PAD - GAP - box.height;
    const below = rect.bottom + PAD + GAP;
    const fitsAbove = above >= GAP;
    const fitsBelow = below + box.height <= element.offsetHeight - GAP;
    const prefer = beat.place ?? (beat.click ? 'above' : 'below');
    const top = prefer === 'above' ? (fitsAbove || !fitsBelow ? Math.max(GAP, above) : below) : (fitsBelow || !fitsAbove ? below : above);
    const left = Math.min(Math.max(GAP, rect.left), element.offsetWidth - box.width - GAP);
    callout.style.transform = `translate(${left}px, ${top}px)`;
  }

  function write(beat, index, count) {
    label.textContent = beat.label;
    line.textContent = beat.line;
    replace(dots, count > 1 ? Array.from({ length: count }, (_, i) => h('i', { class: i === index ? 'is-current' : '' })) : null);
  }

  // The lens shrinks to and grows from a control's centre.
  const tipOf = rect => ({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });

  // The lens as a disc at a point, or wrapped around a control with the page dimmed.
  function shape(kind, at) {
    const css = getComputedStyle(element);
    const accent = css.getPropertyValue('--accent').trim();
    if (kind === 'disc') {
      return {
        transform: `translate(${at.x - DISC / 2}px, ${at.y - DISC / 2}px)`, width: `${DISC}px`, height: `${DISC}px`, borderRadius: `${DISC / 2}px`,
        backgroundColor: `color-mix(in srgb, ${accent} 26%, transparent)`, boxShadow: `0 0 0 1.5px ${accent}, 0 0 0 100vmax ${css.getPropertyValue('--guide-dim').trim()}`,
      };
    }
    const width = at.width + PAD * 2;
    const height = at.height + PAD * 2;
    return {
      transform: `translate(${at.left - PAD}px, ${at.top - PAD}px)`, width: `${width}px`, height: `${height}px`,
      borderRadius: `${Math.abs(width - height) < 4 ? Math.min(width, height) / 2 : 10}px`,
      backgroundColor: `color-mix(in srgb, ${accent} 6%, transparent)`,
      boxShadow: `0 0 0 2px ${accent}, 0 0 0 100vmax ${css.getPropertyValue('--guide-dim').trim()}`,
    };
  }

  // Sets the lens's shape with CSS transitions of `ms`; a new shape mid-way retargets from where
  // the lens is on screen, so it never jumps and nothing is left behind on the element.
  function apply(style, ms) {
    const time = reducedMotion.matches ? 0 : ms;
    const geometry = ['transform', 'width', 'height', 'border-radius', 'background-color', 'box-shadow'].map(name => `${name} ${time}ms ${EASE}`);
    ring.style.transition = [...(time ? geometry : []), 'opacity 280ms ease-in-out'].join(', ');
    Object.assign(ring.style, style);
  }
  function later(ms, work) { stages.push(setTimeout(work, reducedMotion.matches ? 0 : ms)); }
  function stop() {
    for (const timer of stages) clearTimeout(timer);
    stages = [];
    cancelAnimationFrame(follow?.frame ?? 0);
    follow = null;
  }

  // While wrapped, the lens and callout stay on the control as the app scrolls or reflows.
  function track(measure, beat) {
    let last = measure();
    const loop = () => {
      if (!follow) return;
      const rect = measure();
      if (rect && (rect.width || rect.height) && (Math.abs(rect.left - last.left) > 0.5 || Math.abs(rect.top - last.top) > 0.5 || Math.abs(rect.width - last.width) > 0.5 || Math.abs(rect.height - last.height) > 0.5)) {
        last = rect;
        apply(shape('wrap', rect), 0);
        callout.classList.add('is-tracking');
        moveCallout(rect, beat);
        tip = tipOf(rect);
      } else callout.classList.remove('is-tracking');
      follow.frame = requestAnimationFrame(loop);
    };
    follow = { frame: requestAnimationFrame(loop) };
  }

  // Shrinks to a disc where it is, travels as a disc, then widens around the new control and
  // stays on it while the app moves.
  function travel(rect, measure, animate) {
    const to = tipOf(rect);
    const settle = () => { const now = measure() ?? rect; apply(shape('wrap', now), 0); track(measure, current); };
    if (!animate) { apply(shape('wrap', rect), 0); track(measure, current); }
    else if (wrapped) {
      apply(shape('disc', tip), 140);
      later(140, () => apply(shape('disc', to), 300));
      later(440, () => apply(shape('wrap', measure() ?? rect), 200));
      later(640, settle);
    } else {
      apply(shape('disc', to), 380);
      later(380, () => apply(shape('wrap', measure() ?? rect), 220));
      later(600, settle);
    }
    wrapped = true;
    tip = to;
  }

  function place(rect, beat, { animate, index, count, measure = () => rect }) {
    const appearing = !element.classList.contains('is-on');
    const lifted = element.classList.contains('is-lifting');
    const instant = !animate || appearing;
    stop();
    current = beat;
    element.classList.toggle('is-instant', !animate || appearing);
    callout.classList.toggle('is-snap', lifted);
    element.classList.remove('is-lifting');
    element.classList.add('is-on');
    travel(rect, measure, !instant);

    const token = ++swaps;
    const changed = label.textContent !== beat.label || line.textContent !== beat.line;
    if (instant || !changed) {
      callout.classList.remove('is-swapping');
      write(beat, index, count);
      moveCallout(rect, beat);
    } else {
      callout.classList.add('is-swapping');
      setTimeout(() => {
        if (token !== swaps) return;
        write(beat, index, count);
        moveCallout(measure() ?? rect, beat);
        callout.classList.remove('is-swapping');
      }, SWAP_MS);
    }
    requestAnimationFrame(() => requestAnimationFrame(() => {
      element.classList.remove('is-instant');
      callout.classList.remove('is-snap');
    }));
  }

  function lift() {
    if (element.classList.contains('is-on')) element.classList.add('is-lifting');
  }

  // After a click that revealed something (a new page's title, a menu, a panel), the lens glides on
  // to it, so the dimming never drops between steps and nothing is left covered.
  function follow_(rect, beat, measure = () => rect, animate = true) {
    stop();
    travel(rect, measure, animate && !reducedMotion.matches);
    moveCallout(rect, beat);
  }

  // A click briefly brightens the lens's fill, without moving it. A click that changes page then
  // gathers the lens into a disc, so it never frames the old page as it fades.
  function press({ quiet = false } = {}) {
    if (quiet || reducedMotion.matches) return;
    const accent = getComputedStyle(element).getPropertyValue('--accent').trim();
    ring.animate([{}, { backgroundColor: `color-mix(in srgb, ${accent} 22%, transparent)`, offset: 0.35 }, {}], { duration: 460, easing: 'ease-in-out' });
    if (!current?.route) return;
    later(120, () => { stop(); wrapped = false; apply(shape('disc', tip), 240); });
  }

  function hide() {
    swaps += 1;
    stop();
    wrapped = false;
    element.classList.remove('is-on', 'is-lifting');
  }

  return { element, place, follow: follow_, lift, press, hide };
}
