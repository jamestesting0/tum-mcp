import { node } from './dom.mjs';
import { iconButton } from './navigation.mjs';

export function commentPopover(root, content, filter, signal, changed) {
  const element = node('div', 'comment-popover'); element.id = `passage-comments-${crypto.randomUUID()}`;
  element.popover = 'auto'; element.tabIndex = -1; element.dataset.commentUi = '';
  element.setAttribute('role', 'dialog'); element.setAttribute('aria-label', 'Comments');
  const header = node('div', 'comment-popover-header');
  const title = node('h2', '', 'Comments');
  const close = iconButton('Close comments', 'close', () => hide(true));
  header.append(title, filter, close); element.append(header, content); root.append(element);
  let anchor, trigger, frame, opened = false;
  const native = typeof element.showPopover === 'function'; if (!native) element.hidden = true;
  function position() {
    if (!opened) return;
    const rect = anchor?.(), viewport = visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const right = left + (viewport?.width || innerWidth), bottom = top + (viewport?.height || innerHeight);
    if (!rect || rect.bottom < top || rect.top > bottom || rect.right < left || rect.left > right) { hide(); return; }
    element.style.maxHeight = `${Math.max(44, Math.min(440, bottom - top - 24))}px`;
    element.style.maxWidth = `${Math.max(44, right - left - 24)}px`;
    const box = element.getBoundingClientRect(), gap = 12;
    let x = rect.left, y = rect.bottom + gap;
    if (rect.right + gap + box.width <= right - gap) { x = rect.right + gap; y = rect.top; }
    else if (rect.left - gap - box.width >= left + gap) { x = rect.left - gap - box.width; y = rect.top; }
    else if (y + box.height > bottom - gap && rect.top - gap - box.height >= top + gap) y = rect.top - gap - box.height;
    element.style.left = `${Math.max(left + gap, Math.min(x, right - box.width - gap))}px`;
    element.style.top = `${Math.max(top + gap, Math.min(y, bottom - box.height - gap))}px`;
  }
  function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(position); }
  function hide(restore = false) {
    if (!opened) return;
    opened = false; if (native) element.hidePopover(); else element.hidden = true;
    trigger?.setAttribute('aria-expanded', 'false'); changed(false);
    if (restore && trigger?.isConnected) trigger.focus({ preventScroll: true });
  }
  element.addEventListener('toggle', event => {
    if (event.newState === 'closed' && opened && !element.matches(':popover-open')) { opened = false; trigger?.setAttribute('aria-expanded', 'false'); changed(false); }
  });
  document.addEventListener('pointerdown', event => {
    if (!native && opened && !element.contains(event.target) && !trigger?.contains(event.target)) hide();
  }, { signal });
  document.addEventListener('scroll', event => { if (!element.contains(event.target)) schedule(); }, { signal, capture: true });
  window.addEventListener('resize', schedule, { signal });
  visualViewport?.addEventListener('resize', schedule, { signal });
  visualViewport?.addEventListener('scroll', schedule, { signal });
  const observer = new ResizeObserver(schedule); observer.observe(element);
  signal.addEventListener('abort', () => { hide(); observer.disconnect(); cancelAnimationFrame(frame); }, { once: true });
  return { element, get open() { return native ? element.matches(':popover-open') : opened; }, hide, position: schedule,
    show(source, getRect, focus = true) {
      trigger?.setAttribute('aria-expanded', 'false'); trigger = source; anchor = getRect;
      if (!(native ? element.matches(':popover-open') : opened)) { if (native) element.showPopover(); else element.hidden = false; opened = true; }
      trigger?.setAttribute('aria-expanded', 'true'); position(); changed(opened);
      if (opened && focus) element.focus({ preventScroll: true });
    },
  };
}
