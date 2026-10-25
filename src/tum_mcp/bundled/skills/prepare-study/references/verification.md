# Verification scope

Use the generated app, not mock HTML. Reuse tests according to what their inputs
can invalidate; fewer checks must not mean weaker evidence or unreviewed teaching.

## Cheap gates first

Review new/changed teaching with [teaching.md](teaching.md), then run study build.
For changed JavaScript, syntax-check those modules before opening a browser.
Resolve stale source dependencies and inspect preserved custom templates: a build
retaining custom code does not prove support for new data/block types.

## Select checks

| Change | Required coverage |
| --- | --- |
| New site | Prove one demanding unit, then baseline-check every unit's three views for expected heading/content/sources and script/asset errors. |
| Content-only edit | Review/build changed units; inspect the changed view. Add a narrow layout check for longer text or new notation. Reuse unchanged interaction tests. |
| Course metadata, unit order or citations | Check outline/labels, affected links and revision deck order; these can change without unit revisions changing. |
| Shared renderer/state/layout or new block type | Read the relevant [regressions](regressions.md); check changed branches and every affected consumer, plus a working sibling. Recheck route discovery when routing changes. Walk the student journey below. |
| Inventory-only update | Check sync/staleness and coverage disclosure; rebuild affected units, not unchanged teaching. |
| Skill prose | Validate links/metadata/instructions, not unrelated application suites. |

## Student journey

Component checks miss flow breaks, so walk the real path once on a phone (~390px,
touch) and once on desktop: home → Start/Continue → read Content → Next → rate
cards (each rating advances) → Next → check answers, Continue, reach End of set →
Next unit, then Revision → To review. Note every extra scroll or tap the flow needs.
Run it in Chromium, and once in WebKit (Safari's engine: system WebKit through
`Bun.WebView` on macOS, or Playwright webkit) for the card flip, sticky phone bar and
outline pick.

## Surfaces

For a new/changed visual surface, select the smallest unit set covering its block
types and longest real labels/questions. Inspect phone (~390px)/desktop (~1440px),
light/dark, top/scrolled views. Add tablet/zoom when breakpoints or dense notation
change. Run keyboard/reduced-motion checks per changed renderer, not per question.

Exercise shared branches once with suitable data: card reveal, rating advance and
last-card summary; wrong/correct answer, retry, Continue and End of set; card flip/arrow/1/2 shortcuts without hijacking tabs or inputs;
diagram endpoints; outline collapse/current folders/skip link; storage failure,
reload and course-scoped reset. Independently review EVERY new/changed question's
meaning/options; repeating generic clicks for every question/theme proves less.
An accessibility scanner complements visual/keyboard checks, not subject review.
For changed revision/state code, cover empty/one/multiple topics, same item key in
different topics, selection changes at the last item, reload and progress shared
with the original topic. For category selection, cover nested select/clear, partial
parent state and unrelated topics. Check both pooled views, without multiplying every item
by every viewport. Boundary controls need hover, keyboard-focus and touch checks.
For passage comments, cover save/cancel/edit/reload, quoted-text matching, changed
or ambiguous passages, browser/agent conflicts and retained drafts, resolution,
automatic external updates, unchanged conditional reads, stable row/focus/scroll,
explicit same-note conflict choices, safe unrelated-note rebasing, course identity,
write confinement and same-origin API checks. Check anchored popup geometry at
viewport edges/zoom, resizing/scroll dismissal, outside/Escape close and focus
return; current-item markers and popup shortcut isolation in both pooled views. Review notes as data. For table
layout changes, inspect short row labels, asymmetric prose and one unbroken token
at narrow/tablet/wide sizes, with local scroll and no page overflow.

## Evidence and failure handling

Use a real browser tool or the existing Playwright/discovered-Chromium runtime,
including its WSL bridge. Use task-owned profiles without campus cookies; derive
selectors/expectations from content and semantic roles, not guessed headings or sleeps.
Inspect resulting state and first useful error before retrying. Broaden diagnosis
for repeated identical failures; do not reinstall browsers/frameworks or enumerate
other apps to repair a locator.

Keep a short private record: tested unit revisions, ACTUAL renderer file hashes,
relevant course/order/citation inputs, cases/results and useful captures. Coverage
timestamps alone do not invalidate unchanged results. Recheck affected evidence
after fixes; do not rerun the whole matrix for each local edit or count screenshots
as a quality score. Stop only owned test processes. Honor required project/release
gates, including all required CI jobs on the exact latest pushed commit. Report
unrun checks/gaps honestly; neither a build nor testing certifies bug-free software.

## Component showcase checks

Include every supported block type: prose, labelled code, intrinsic tables, editable
formulas, graph traces and concept/process diagrams. Formula examples cover fractions,
sums, matrices and chained relations; preserve all terms at narrow and wide widths,
including when the outline changes. Use one primary typeface for headings and reading
text; code and math keep their functional fonts. Long revision outlines need nested
collapse and selection checks while closed. Review a wrong question in its modal and
close it back to the unchanged results row; unanswered solutions require Show answer.
