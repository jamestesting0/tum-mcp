// The interaction smoke: on the open page, use every stepping and help control the way a
// student would and report each one that does not respond. Returns the problems found and
// how many controls were exercised. Runs in the app page; never edits content.
async ({ query, study, exercise }) => {
  const problems = [], frame = () => new Promise(resolve => requestAnimationFrame(() => resolve()));
  let used = 0;
  const say = (control, problem) => problems.push({ control, problem });
  const visible = element => Boolean(element && element.getClientRects().length && !element.closest('[hidden]'));
  const label = element => (element.closest('section')?.querySelector('h2, h3, h4')?.textContent || '').trim().slice(0, 60);
  const formulaBox = '.inline-math, .equation, .derivation-left, .derivation-relation, .derivation-right, .derivation-whole, .tex, math';
  const checked = new WeakSet();
  const scrolls = (mode, extent, client) => mode === 'scroll' || (mode === 'auto' && extent > client);
  const mathVisible = element => visible(element)
    && !element.closest('[inert], .katex-mathml, details:not([open]) > :not(summary)')
    && getComputedStyle(element).visibility === 'visible';
  const mathText = value => typeof value === 'string' ? /\\\(|<math[\s>]/.test(value)
    : value !== null && typeof value === 'object' && Object.values(value).some(mathText);
  const data = study || exercise ? (await import(new URL('data.mjs', location.href).href)).default : null;
  const steps = exercise && data.exercises.sets.flatMap(set => set.exercises)
    .find(item => item.key === exercise).steps;
  const guideMath = mathText(steps || null);

  function layoutOf(element, cache) {
    if (cache.has(element)) return cache.get(element);
    const style = getComputedStyle(element), box = element.getBoundingClientRect();
    // An SVG foreignObject has a viewport in screen coordinates, but no HTML client box.
    const svg = element.localName === 'foreignObject';
    const scaleX = element.offsetWidth ? box.width / element.offsetWidth : 1;
    const scaleY = element.offsetHeight ? box.height / element.offsetHeight : 1;
    const left = box.left + (element.clientLeft || 0) * scaleX;
    const top = box.top + (element.clientTop || 0) * scaleY;
    const layout = { left, top, scaleX, scaleY,
      width: svg ? box.width : element.clientWidth * scaleX,
      height: svg ? box.height : element.clientHeight * scaleY,
      overflowX: svg ? 'clip' : style.overflowX, overflowY: svg ? 'clip' : style.overflowY };
    cache.set(element, layout);
    return layout;
  }

  function mathIssue(formula, cache) {
    const marks = [...formula.querySelectorAll('.katex-html > .katex-base, math')].filter(mathVisible);
    if (!marks.length) marks.push(...[...formula.querySelectorAll('.katex-html')].filter(mathVisible));
    if (!marks.length && formula.matches('math')) marks.push(formula);
    for (const mark of marks) {
      const box = mark.getBoundingClientRect().toJSON();
      for (let node = mark; node && node !== document.body; node = node.parentElement) {
        const region = layoutOf(node, cache);
        const own = formula.contains(node);
        for (const [axis, start, end, size, position, extent, offset, scale] of [
          ['X', 'left', 'right', 'width', 'scrollLeft', 'scrollWidth', 'clientWidth', region.scaleX],
          ['Y', 'top', 'bottom', 'height', 'scrollTop', 'scrollHeight', 'clientHeight', region.scaleY],
        ]) {
          const mode = region['overflow' + axis];
          if (mode === 'visible' || (!node[offset] && !node[extent] && node.localName !== 'foreignObject')) continue;
          const scrolling = scrolls(mode, node[extent], node[offset]);
          if (own && scrolling) return 'has its own scrollbar';
          const shift = scrolling ? node[position] * scale : 0;
          const span = scrolling ? node[extent] * scale : region[size];
          const min = region[start] - shift;
          if (box[start] < min - 2 || box[end] > min + span + 2) return 'is clipped';
          if (scrolling) {
            const length = Math.min(box[end] - box[start], region[size]);
            box[start] = Math.max(region[start], Math.min(box[start], region[start] + region[size] - length));
            box[end] = box[start] + length;
          }
        }
      }
      if (box.left < -2 || box.right > document.documentElement.clientWidth + 2)
        return 'extends beyond the reading viewport';
    }
    return '';
  }

  async function inspectMath(root, context) {
    if (!root || (!study && !exercise)) return;
    if (document.fonts.status === 'loading') { await document.fonts.ready; await frame(); }
    const cache = new Map(), suspects = [];
    for (const formula of root.querySelectorAll(formulaBox)) {
      if (checked.has(formula) || !mathVisible(formula) || formula.parentElement.closest(formulaBox)) continue;
      checked.add(formula);
      if (mathIssue(formula, cache)) suspects.push(formula);
    }
    for (const formula of suspects) {
      // The native display equation fits when it nears the viewport. Retry a suspect after that layout.
      formula.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      await frame(); await frame();
      const issue = mathIssue(formula, new Map());
      if (!issue) continue;
      const ink = [...formula.querySelectorAll('.katex-html')].map(node => node.textContent).join(' ') || formula.textContent;
      const excerpt = ink.replace(/\s+/g, ' ').trim().slice(0, 72);
      const heading = label(formula);
      say('math', `${context}${heading ? ` · ${heading}` : ''}: formula "${excerpt}" ${issue}`);
    }
  }

  async function inspectDetails(root, context) {
    if (!study && !exercise) return;
    for (const details of root.querySelectorAll('details')) {
      if (details.open || !mathVisible(details) || !details.querySelector(formulaBox)) continue;
      details.open = true;
      await frame();
      await inspectMath(details, context);
      // A nested answer may also start closed. Keep its parent open until it is checked.
      await inspectDetails(details, context);
      details.open = false;
    }
  }

  async function inspectReading(root, context = 'Lesson or statement') {
    await inspectMath(root, context);
    await inspectDetails(root, context);
    for (const region of root.querySelectorAll('.equation, .derivation, .code-region, .term-bubble')) {
      if (!visible(region) || region.scrollWidth <= region.clientWidth + 2) continue;
      const overflow = getComputedStyle(region).overflowX;
      if (overflow === 'hidden' || overflow === 'clip') say('reading', 'Clipped content in ' + (label(region) || region.className));
    }
    for (const term of root.querySelectorAll('button.term')) {
      if (!visible(term)) continue;
      used++;
      term.scrollIntoView({ block: 'center', inline: 'nearest' });
      term.click();
      const bubble = term.parentElement.querySelector('.term-bubble');
      if (!bubble?.textContent.trim()) say('term', 'The term opened without a meaning');
      await inspectMath(bubble, `${context} · term`);
      if (term.closest('.annotation-tip') && bubble) {
        const box = bubble.getBoundingClientRect();
        if (box.left < 0 || box.right > innerWidth || box.top < 0 || box.bottom > innerHeight) {
          say('term', 'The annotation extends beyond the viewport');
        }
      }
      term.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      if (term.getAttribute('aria-expanded') === 'true') say('term', 'Escape did not close the meaning');
    }
  }

  await inspectReading(document.querySelector('main') || document.body);

  for (const walk of document.querySelectorAll('.walk')) {
    used++;
    const name = `walkthrough '${label(walk)}'`, next = walk.querySelector('[aria-label="Next step"]');
    const runs = [...walk.querySelectorAll('.segmented .segment')];
    for (const run of runs.length ? runs : [null]) {
      if (run) { run.click(); await frame(); }
      walk.querySelector('.walk-dot')?.click(); await frame();
      await inspectMath(walk, name);
      const first = walk.querySelector('.walk-card').innerText, seen = new Set([first]);
      let guard = 0;
      while (!next.disabled && guard++ < 60) {
        next.click(); await frame();
        await inspectMath(walk, name);
        const text = walk.querySelector('.walk-card').innerText;
        if (text === first && seen.size > 1) break;
        if (seen.has(text)) { say(name, 'Next did not change the step card'); break; }
        seen.add(text);
      }
      const dots = walk.querySelectorAll('.walk-dot').length;
      if (dots !== seen.size) say(name, `${seen.size} steps reached but ${dots} dots shown`);
      const all = walk.querySelector('.walk-toggle');
      all.click(); await frame();
      if (!visible(walk.querySelector('.walk-trace'))) say(name, 'All steps did not show the trace');
      await inspectMath(walk, `${name} · all steps`);
      all.click(); await frame();
      if (!visible(walk.querySelector('.walk-card'))) say(name, 'Step through did not bring back the step card');
    }
  }
  for (const controls of document.querySelectorAll('.diagram-controls:not(.walk-controls), .code-walk-controls')) {
    if (!visible(controls)) continue;
    used++;
    const next = controls.querySelector('[aria-label="Next step"], [aria-label="Next stop"]');
    const counter = controls.querySelector('.small, .code-walk-count');
    let guard = 0, before = counter?.textContent;
    const first = before;
    while (next && !next.disabled && guard++ < 120) {
      next.click(); await frame();
      await inspectMath(controls.parentElement, 'Stepper');
      if (counter && counter.textContent === before) { say(`stepper '${label(controls)}'`, 'Next did not advance'); break; }
      if (counter && counter.textContent === first) break;
      before = counter?.textContent;
    }
  }
  for (const pill of document.querySelectorAll('.pill-panel')) {
    if (!visible(pill)) continue;
    used++;
    const panel = pill.querySelector('.pill-content'), name = `pill '${label(pill)}'`;
    for (const segment of pill.querySelectorAll(':scope > .segmented .segment')) {
      segment.click(); await frame();
      if (panel.hidden || !panel.textContent.trim()) say(name, `${segment.textContent} opened an empty panel`);
      const guide = panel.querySelector('.exercise-step');
      const counter = guide?.querySelector('.step-count'), first = counter?.textContent;
      let remaining = guideMath ? steps.length : 1;
      do {
        const context = `${name} · ${segment.textContent}${counter ? ` · ${counter.textContent}` : ''}`;
        await inspectReading(panel, context);
        if (guideMath) {
          const hint = guide?.querySelector('.exercise-actions .secondary');
          while (visible(hint)) {
            const hints = guide.querySelector('.exercise-hints'), count = hints.childElementCount;
            hint.click();
            if (hints.childElementCount <= count) { say(name, 'Hint did not reveal its text'); break; }
            await inspectMath(hints, `${context} · hint`);
          }
        }
        const action = panel.querySelector('.exercise-actions .primary');
        if (action?.textContent === 'Compare') {
          action.click(); await frame();
          const feedback = panel.querySelector('.feedback');
          if (!feedback) say(name, 'Compare showed no answer');
          else await inspectReading(feedback, `${context} · answer`);
        } else if (guideMath && action?.textContent === 'Check') {
          for (const choice of guide.querySelectorAll('input[type="radio"]')) {
            choice.click(); action.click();
            await inspectReading(guide.querySelector('.exercise-feedback'), `${context} · feedback`);
            if (action.textContent !== 'Check') break;
          }
        }
        const next = guide?.querySelector('.step-navigation [aria-label="Next step"]');
        if (!guideMath || !next || next.disabled) break;
        const previous = counter.textContent;
        next.click(); await frame(); await frame();
        if (counter.textContent === previous) { say(name, 'Guide did not advance to the next step'); break; }
      } while (--remaining && counter.textContent !== first);
      segment.click(); await frame();
      if (!panel.hidden) say(name, `choosing the open ${segment.textContent} again did not close it`);
    }
  }
  if (study) {
    const unit = data.units.find(item => item.key === study);
    const tab = async view => {
      document.querySelector(`[role="tab"][aria-controls="panel-${view}"]`).click();
      await frame();
    };
    if (mathText(unit.explore)) {
      await tab('explore');
      await inspectReading(document.querySelector('#panel-explore'), 'Explore');
    }
    if (mathText(unit.flashcards)) {
      await tab('flashcards');
      for (const [index, card] of unit.flashcards.entries()) {
        if (mathText(card)) {
          const deck = document.querySelector('#panel-flashcards'), context = `Flashcard ${index + 1}`;
          await inspectMath(deck, context);
          deck.querySelector('[data-card-action="flip"]').click(); await frame();
          await inspectMath(deck, `${context} · answer`);
        }
        document.querySelector('#panel-flashcards [data-card-action="next"]').click();
      }
    }
    if (mathText(unit.questions)) {
      await tab('practice');
      for (const [index, question] of unit.questions.entries()) {
        const panel = document.querySelector('#panel-practice'), context = `Practice question ${index + 1}`;
        if (mathText(question)) {
          panel.querySelector('.card-actions .secondary')?.click();
          await inspectReading(panel, context);
          panel.querySelector(`input[value="${CSS.escape(question.correct)}"]`).click();
          panel.querySelector('button[type="submit"]').click(); await frame();
          await inspectReading(panel, `${context} · feedback`);
        }
        panel.querySelector('.practice-navigation [aria-label="Next question"]').click();
      }
    }
  }
  for (const action of document.querySelectorAll('.exam-guided-step .exercise-actions .primary')) {
    if (!/Compare/.test(action.textContent)) continue;
    used++;
    action.click(); await frame();
    if (!action.closest('.exam-guided-step').querySelector('.feedback')) say('worked practice', 'Compare showed no answer');
  }
  if (query) {
    used++;
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true }));
    await frame();
    const input = document.querySelector('dialog.search-dialog[open] .search-input');
    if (!input) say('search', '"/" did not open search');
    else {
      input.value = query; input.dispatchEvent(new Event('input'));
      await frame();
      if (!document.querySelector('.search-result')) say('search', `no result for "${query}"`);
      input.closest('dialog').close();
    }
  }
  return { problems, used };
}
