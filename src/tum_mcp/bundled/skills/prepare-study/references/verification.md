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
| Course metadata, unit order or citations | Check outline/labels, affected links and previous/next navigation; these can change without unit revisions changing. |
| Shared renderer/state/layout or new block type | Read the relevant [regressions](regressions.md); check changed branches and every affected consumer, plus a working sibling. Recheck route discovery when routing changes. |
| Inventory-only update | Check sync/staleness and coverage disclosure; rebuild affected units, not unchanged teaching. |
| Skill prose | Validate links/metadata/instructions, not unrelated application suites. |

For a new/changed visual surface, select the smallest unit set covering its block
types and longest real labels/questions. Inspect phone (~390px)/desktop (~1440px),
light/dark, top/scrolled views. Add tablet/zoom when breakpoints or dense notation
change. Run keyboard/reduced-motion checks per changed renderer, not per question.

Exercise shared branches once with suitable data: card reveal/rating; wrong/correct
answer, retry/advance; diagram endpoints; focus/escape/skip link; storage failure,
reload and course-scoped reset. Independently review EVERY new/changed question's
meaning/options; repeating generic clicks for every question/theme proves less.
An accessibility scanner complements visual/keyboard checks, not subject review.

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
