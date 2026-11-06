// The interaction smoke: on the open page, use every stepping and help control the way a
// student would and report each one that does not respond. Returns the problems found and
// how many controls were exercised. Runs in the app page; never edits content.
async ({ query }) => {
  const problems = [], frame = () => new Promise(resolve => requestAnimationFrame(() => resolve()));
  let used = 0;
  const say = (control, problem) => problems.push({ control, problem });
  const visible = element => Boolean(element && element.getClientRects().length && !element.closest('[hidden]'));
  const label = element => (element.closest('section')?.querySelector('h2, h3, h4')?.textContent || '').trim().slice(0, 60);

  function inspectReading(root) {
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

  inspectReading(document.querySelector('main') || document.body);

  for (const walk of document.querySelectorAll('.walk')) {
    used++;
    const name = `walkthrough '${label(walk)}'`, next = walk.querySelector('[aria-label="Next step"]');
    const runs = [...walk.querySelectorAll('.segmented .segment')];
    for (const run of runs.length ? runs : [null]) {
      if (run) { run.click(); await frame(); }
      walk.querySelector('.walk-dot')?.click(); await frame();
      const seen = new Set([walk.querySelector('.walk-card').innerText]);
      let guard = 0;
      while (!next.disabled && guard++ < 60) {
        next.click(); await frame();
        const text = walk.querySelector('.walk-card').innerText;
        if (seen.has(text)) { say(name, 'Next did not change the step card'); break; }
        seen.add(text);
      }
      const dots = walk.querySelectorAll('.walk-dot').length;
      if (dots !== seen.size) say(name, `${seen.size} steps reached but ${dots} dots shown`);
    }
    const all = walk.querySelector('.walk-toggle');
    all.click(); await frame();
    if (!visible(walk.querySelector('.walk-trace'))) say(name, 'All steps did not show the trace');
    all.click(); await frame();
    if (!visible(walk.querySelector('.walk-card'))) say(name, 'Step through did not bring back the step card');
  }
  for (const controls of document.querySelectorAll('.diagram-controls:not(.walk-controls), .code-walk-controls')) {
    if (!visible(controls)) continue;
    used++;
    const next = controls.querySelector('[aria-label="Next step"], [aria-label="Next stop"]');
    const counter = controls.querySelector('.small, .code-walk-count');
    let guard = 0, before = counter?.textContent;
    while (next && !next.disabled && guard++ < 120) {
      next.click(); await frame();
      if (counter && counter.textContent === before) { say(`stepper '${label(controls)}'`, 'Next did not advance'); break; }
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
      inspectReading(panel);
      const action = panel.querySelector('.exercise-actions .primary');
      if (action && /Compare/.test(action.textContent)) {
        action.click(); await frame();
        if (!panel.querySelector('.feedback')) say(name, 'Compare showed no answer');
        else inspectReading(panel.querySelector('.feedback'));
      }
      segment.click(); await frame();
      if (!panel.hidden) say(name, `choosing the open ${segment.textContent} again did not close it`);
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
