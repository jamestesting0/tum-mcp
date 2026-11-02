import { node, append, studyText } from './dom.mjs';
import { symbolLatex, symbolMarks, texElement } from './mathml.mjs';

// A formula's variables open their meaning in place. A click on a marked variable shows its
// meaning; the formula is one focus stop whose Enter or Space lists every meaning, and screen
// readers get the same list as its description. The bubble floats above the page, so a
// scrolling formula never clips it.
let open = null;
let count = 0;

function close() {
  if (!open) return;
  open.bubble.remove(); open.anchor?.removeAttribute('data-open');
  open = null;
}
document.addEventListener('pointerdown', event => { if (open && !open.host.contains(event.target) && !open.bubble.contains(event.target)) close(); });
// The bubble follows its formula while the page scrolls and closes once the formula is gone.
let frame = 0;
function follow() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(() => {
    if (!open) return;
    const place = (open.anchor || open.host).getBoundingClientRect();
    if (place.bottom < 0 || place.top > innerHeight) close(); else position(open.bubble, place);
  });
}
document.addEventListener('scroll', follow, { capture: true, passive: true });
window.addEventListener('resize', follow);

function position(bubble, place) {
  const left = Math.max(8, Math.min(place.left, innerWidth - bubble.offsetWidth - 8));
  const below = place.bottom + 6, above = place.top - bubble.offsetHeight - 6;
  bubble.style.left = `${left}px`;
  bubble.style.top = `${below + bubble.offsetHeight > innerHeight - 8 && above > 8 ? above : below}px`;
}

function spoken(symbol) {
  return texElement(symbolLatex(symbol))?.querySelector('.katex-mathml')?.textContent.trim() || symbol;
}

function show(host, items, anchor) {
  const same = open && open.host === host && open.anchor === anchor;
  close();
  if (same) return;
  const bubble = node('div', 'term-bubble symbol-bubble'); bubble.setAttribute('role', 'status');
  // A clicked variable is already in view, so its bubble says only what it means; the list of
  // a whole formula names each variable to tell them apart.
  for (const item of items) {
    const row = node('p', 'symbol-row');
    if (!anchor) row.append(symbolName('span', 'symbol-name', item.symbol));
    bubble.append(append(row, studyText('span', 'symbol-meaning', item.meaning)));
  }
  document.body.append(bubble);
  position(bubble, (anchor || host).getBoundingClientRect());
  anchor?.setAttribute('data-open', '');
  open = { host, bubble, anchor };
}

// A variable is marked once per block, so a line lists every variable its LaTeX contains.
// A meaning list's variable, written \(\rho\) or \rho, set as mathematics.
export function symbolName(tag, className, symbol) {
  return append(node(tag, className), texElement(symbolLatex(symbol)) || node('code', '', symbol));
}
export function withMeanings(host, symbols, latex) {
  const names = symbols.map(item => item.symbol);
  const used = [...new Set(symbolMarks(latex, names).map(([, , index]) => index))]
    .sort((a, b) => a - b).map(index => symbols[index]).filter(Boolean);
  if (!used.length) return host;
  const description = node('span', 'visually-hidden', used.map(item => `${spoken(item.symbol)}: ${item.meaning}`).join('; '));
  description.id = `meanings-${++count}`;
  host.append(description);
  host.classList.add('has-meanings'); host.tabIndex = 0;
  host.setAttribute('aria-describedby', description.id);
  host.addEventListener('click', event => {
    const mark = event.target.closest('[data-v]');
    if (!mark || !host.contains(mark)) return;
    event.stopPropagation();
    show(host, [symbols[Number(mark.dataset.v)]], mark);
  });
  host.addEventListener('keydown', event => {
    if (event.target !== host) return;
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(host, used, null); }
    if (event.key === 'Escape' && open?.host === host) { event.preventDefault(); close(); }
  });
  host.addEventListener('focusout', event => { if (open?.host === host && !host.contains(event.relatedTarget)) close(); });
  return host;
}
