import { h, replace } from '../ui/dom.js';

// The sign-in scene's mouse pointer (a person signing in); the guide itself uses the lens below.
export const POINTER = '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path d="M5 2.8 19 11.3l-6.1 1.4 3.7 7.1-2.8 1.5-3.7-7.2L5 18.4Z" fill="#101418" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
const GAP = 12;
const PAD = 6;
const DISC = 22;
const TRAVEL_MS = 640;
const EASE = 'cubic-bezier(.45, 0, .2, 1)';
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const sameBox = (a, b) => Boolean(a && b) && ['left', 'top', 'width', 'height'].every(key => Math.abs(a[key] - b[key]) <= 0.5);

// The tour's lens and callout over the live app. The layer shares the frame's coordinate space,
// so rectangles measured in the app document place it directly. The lens is one shape: it travels
// as a small accent disc, widens into the highlight around each control (dimming the rest) and
// stays wrapped around it, following it as the app moves. The dimming stays steady while the guide
// shows; after a click the lens glides on to whatever the click revealed.
export function createGuide({ topInset = () => 0 } = {}) {
  const ring = h('div.guide-ring');
  const label = h('strong');
  const line = h('span');
  const dots = h('span.guide-dots', { 'aria-hidden': 'true' });
  const callout = h('div.guide-callout', { role: 'status' }, h('div.guide-text', {}, label, line), dots);
  const element = h('div.guide', {}, ring, callout);
  let tip = { x: 0, y: 0 };
  let wrapped = false;
  let current = null;
  let stages = [];
  let follow = null;

  // Click beats default to a callout above the control, since what the click opens appears below it.
  // The callout never covers the app's own sticky bar; a control too tall for either side (a whole
  // map) gets the callout over its lower part, keeping its heading in view.
  function moveCallout({ captionBox, captionLimit }, beat) {
    const box = { width: callout.offsetWidth, height: callout.offsetHeight };
    const ceiling = GAP + topInset();
    const floor = (captionLimit ?? element.offsetHeight) - GAP - box.height;
    const above = captionBox.top - PAD - GAP - box.height;
    const below = captionBox.bottom + PAD + GAP;
    const fitsAbove = above >= ceiling && above <= floor;
    const fitsBelow = below >= ceiling && below <= floor;
    const prefer = beat.place ?? (beat.click ? 'above' : 'below');
    const top = fitsBelow && prefer === 'bottom' ? floor
      : fitsAbove && (prefer === 'above' || !fitsBelow) ? above
      : fitsBelow ? below : Math.max(ceiling, floor);
    const left = Math.min(Math.max(GAP, captionBox.left), element.offsetWidth - box.width - GAP);
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
    if (kind === 'disc') {
      return {
        transform: `translate(${at.x - DISC / 2}px, ${at.y - DISC / 2}px)`, width: `${DISC}px`, height: `${DISC}px`, borderRadius: `${DISC / 2}px`,
        backgroundColor: 'color-mix(in srgb, var(--accent) 26%, transparent)', boxShadow: '0 0 0 1.5px var(--accent), 0 0 0 100vmax var(--guide-dim)',
      };
    }
    const width = at.width + PAD * 2;
    const height = at.height + PAD * 2;
    return {
      transform: `translate(${at.left - PAD}px, ${at.top - PAD}px)`, width: `${width}px`, height: `${height}px`,
      borderRadius: `${Math.abs(width - height) < 4 ? Math.min(width, height) / 2 : 10}px`,
      backgroundColor: 'color-mix(in srgb, var(--accent) 6%, transparent)',
      boxShadow: '0 0 0 2px var(--accent), 0 0 0 100vmax var(--guide-dim)',
    };
  }

  // Sets the lens's shape with CSS transitions of `ms`; a new shape mid-way retargets from where
  // the lens is on screen, so it never jumps and nothing is left behind on the element.
  function apply(style, ms) {
    const time = reducedMotion.matches ? 0 : ms;
    const geometry = ['transform', 'width', 'height', 'border-radius', 'background-color', 'box-shadow'].map(name => `${name} ${time}ms ${EASE}`);
    ring.style.transition = [...(time ? geometry : []), 'opacity 140ms ease-out'].join(', ');
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
  function anchor(target, beat) {
    element.classList.toggle('is-unanchored', !target);
    if (!target) return;
    apply(shape('wrap', target.rect), 0);
    moveCallout(target, beat);
    tip = tipOf(target.rect);
  }

  function track(measure, beat, last) {
    const loop = () => {
      if (!follow) return;
      const target = measure();
      const same = target && last && sameBox(target.rect, last.rect)
        && sameBox(target.captionBox, last.captionBox) && target.captionLimit === last.captionLimit;
      if (target !== last && !same) { anchor(target, beat); last = target; }
      follow.frame = requestAnimationFrame(loop);
    };
    follow = { frame: requestAnimationFrame(loop) };
  }

  // Shrinks to a disc where it is, travels as a disc, then widens around the new control and
  // stays on it while the app moves.
  function aim(measure, beat, animate, writeCaption) {
    const target = measure();
    if (!target) { hide(); return 0; }
    const { rect } = target;
    const instant = !animate || reducedMotion.matches || !element.classList.contains('is-on')
      || element.classList.contains('is-lifting') || element.classList.contains('is-unanchored');
    stop();
    current = beat;
    element.classList.add('is-on');
    element.classList.remove('is-lifting');
    const settle = () => {
      const latest = measure();
      writeCaption?.();
      anchor(latest, beat);
      element.classList.remove('is-travelling');
      track(measure, beat, latest);
    };
    if (instant) {
      settle();
      wrapped = true;
      return 0;
    }
    element.classList.add('is-travelling');
    const to = tipOf(rect);
    const wrap = ms => apply(shape('wrap', measure()?.rect ?? rect), ms);
    if (wrapped) {
      apply(shape('disc', tip), 140);
      later(140, () => apply(shape('disc', to), 300));
      later(440, () => wrap(200));
      later(TRAVEL_MS, settle);
    } else {
      apply(shape('disc', to), 380);
      later(380, () => wrap(220));
      later(TRAVEL_MS, settle);
    }
    wrapped = true;
    tip = to;
    return TRAVEL_MS;
  }

  function place(measure, beat, { animate, index, count }) {
    return aim(measure, beat, animate, () => write(beat, index, count));
  }

  function lift() {
    if (element.classList.contains('is-on')) element.classList.add('is-lifting');
  }

  // After a click that revealed something (a new page's title, a menu, a panel), the lens glides on
  // to it, so the dimming never drops between steps and nothing is left covered.
  function retarget(measure, beat, animate) {
    return aim(measure, beat, animate);
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
    stop();
    wrapped = false;
    element.classList.remove('is-on', 'is-lifting', 'is-travelling', 'is-unanchored');
  }

  return { element, place, retarget, lift, press, hide };
}
