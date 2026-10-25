# Verify a study site efficiently

Reuse known-good components. Spend review effort on changed content and behavior.
The goal is a polished first result, with evidence for its actual functionality.
Testing reduces defects; it cannot certify that an app has no bugs.

## 1. Establish the change boundary

Read the course AGENTS.md, source state and existing site before editing. Record
which unit keys, sources and renderer files change. Keep a short private check
record with the content generation, renderer file hashes, tested cases and result.
Reuse by unit revision and actual renderer hashes, not just timestamps or ownership
receipts. A new coverage timestamp alone does not invalidate an unchanged unit.
Do not put private course screenshots or materials in a public repository.

For a new site, use the bundled renderer and design tokens. First build one unit
that exercises the course's difficult formats. Inspect its real browser result
before generating the rest. Reuse that implementation rather than making separate
HTML or interactions for each unit. For an established site, preserve its theme
and edits; do not start a new design cycle.

## 2. Reject bad input before opening a browser

- Check the bound course and exact source versions. Build failures for stale or
  conflicted material require reviewing the affected explanation, not replacing
  hashes until the build passes. Partial access is not complete course coverage.
  A PDF/exercise list is not a full inventory: consult lecture units, announcements
  and discussions where relevant.
- Review every new or changed explanation, card and question against its sources.
  Check each answer and distractor independently. Schema-valid answers can still
  be wrong. Trace a worked example, boundary case or counterexample for each
  procedural or mathematical claim.
- Compare the same claim across prose, formula conditions, tables, cards and
  question feedback. Keep assumptions and terminology consistent. For example,
  BFS minimizes edge count; equal **positive** weights make that also minimum
  total cost. A formula in edge counts must not silently become a cost formula.
- Map each objective to an explanation and a meaningful assessment. Vary question
  difficulty and answer position as the material needs; avoid duplicated prompts,
  implausible distractors and a correct answer identifiable by its length.
- Run `tum-mcp study build PROJECT`. For edited JavaScript, also syntax-check the
  changed modules, for example `node --check PROJECT/study/app.mjs`. Do this
  before expensive browser checks. Preserve and report edited templates; a build
  retaining custom code does not prove compatibility with new data or block types.

## 3. Run a compact browser acceptance pass

Open the actual generated site with `tum-mcp study serve PROJECT`. Use an available
browser tool, or the existing Playwright runtime with discovered Chromium browsers
and the WSL bridge where applicable. Use a fresh, task-owned profile without campus
cookies. Test the generated files, not a mock HTML page built for screenshots.

Check every unit's Content, Flashcards and Practice views at a baseline viewport:
correct heading, nonempty content, expected sources, no script errors or failed
local assets. Derive selectors and expected text from content.json and semantic
roles. A guessed heading caused a false timeout in this implementation; fixed
sleeps and repeated retries do not repair an incorrect locator.

Choose the smallest set of units covering all used block types and the longest
real labels/questions. Check that set at phone (~390px) and desktop (~1440px), in
light and dark themes. Inspect both the top and a scrolled view. Add tablet, zoom
or another size when a changed breakpoint, dense table or long formula warrants it.
Check reduced motion and keyboard navigation once per shared renderer revision.

Exercise both branches of shared behavior: card hidden/revealed, Again/Got it,
wrong/correct answer, retry/advance, first/last diagram frame, focus/escape, normal/
blocked storage, reload and reset. Inspect the resulting UI, not just the click's
return value. This tests renderer behavior; source review still checks every
new or changed question. An accessibility scanner supplements visual and keyboard
checks. Automation must use the app's actual state rather than guessed delays.

## 4. Regressions learned from this implementation

| Failure to prevent | Required behavior and check |
| --- | --- |
| New unit opens halfway down on mobile | Scroll to the end, change units, and verify the new title and beginning are visible. Check document scroll on phones and the main pane on desktop. |
| Broken tab relationships | Every aria-controls target exists, including inactive panels. Exactly one panel is shown. Arrow keys, Home/End and roving tabindex select and focus the correct tab. |
| Skip link changes the course route | From a nonfirst unit, activate the skip link. It focuses main content without resetting the unit or view. |
| Focus disappears after replacing content | Next/previous/retry leaves focus at the new prompt or legend. Focus mode retains navigation; Escape restores the outline/control. |
| Theme flash or color-dependent instructions | Theme colors change immediately. Descriptions say highlighted/active or explain state, rather than dark/green. Check both themes and use text alongside color. |
| Wide content breaks the page | The document has no horizontal overflow. Tables, formulas, code and diagrams use labelled keyboard-scrollable regions when needed. Keep graph labels legible; use boxes for long names. Inspect real notation at a narrow width. |
| Long names stretch the outline | Test an unbroken technical identifier as both course and unit title. Check the desktop sidebar and mobile outline summary, not only document width or the main heading. |
| Storage warning hidden in closed settings | Block storage and perform a rating/answer. Studying still works in memory and a visible warning explains that progress cannot be saved, including on mobile. |
| Unrelated changes reset progress | Adding a source binding keeps the course namespace. Unchanged units keep progress. Revised units have separate progress; old answers must not certify revised questions. Reload and check persistence. |
| Answer leaks or the app advances early | Card fronts hide answers/sources/ratings until reveal. Checking an answer retains feedback. Advance is explicit; retry clears the attempt and restores focus. |
| Plausible but incorrect diagram trace | Independently compute the traversal/state. Check frontier order, discovery versus processing, directed edges and endpoints. First/last controls are bounded; nothing autoplays. |
| Answer keys conceal bad teaching | Verify each option under its stated assumptions. Compare explanations, formulas, cards and tables. Browser selection tests do not establish subject accuracy. |
| Updates overwrite edits or reuse stale teaching | In a disposable copy, change a managed source or renderer. The update preserves it and reports a conflict. Changed sources invalidate dependent units. Do not copy new hashes onto unreviewed content. |
| Admin copy distracts from learning | Visible text serves study or navigation. Keep course/coverage details in concise disclosures and storage errors conditional. Remove technical banners, duplicated labels and boilerplate tips. |
| Screenshot passes despite broken behavior | Verify keyboard, feedback, persistence and navigation on the served app. Record errors and assertions; a render, click or build alone is not a functional pass. |
| Verification costs more than implementation | Reuse the renderer, data-derived selectors and revision-stamped evidence. Do not multiply every question by every viewport/theme or recapture unchanged units after a local fix. |

## 5. Repeat only what a change can invalidate

| Change | Checks to rerun |
| --- | --- |
| Explanation/card/question data | Review changed teaching and citations; validate/build; inspect affected units and the relevant interaction. Include a narrow check for changed length or notation. |
| New block type or custom renderer | Check schema and safe rendering, keyboard/text fallback, both themes and narrow/wide layouts. Cover each new state and an existing block. |
| Routing, focus, persistence or shared layout | Run the shared acceptance pass and relevant regressions across all consumers. Recheck unit/view discovery for the whole site. |
| Source inventory only | Verify reconciliation and staleness. Regenerate affected learning units; reuse browser evidence for unchanged units and renderer hashes. |
| Skill prose only | Check instructions, links and machine-consumed metadata. Do not rerun application suites merely because guidance changed. |

After a failure, inspect the first useful error, current DOM and relevant source.
Fix the cause, then rerun the failing check and its neighboring behavior. Repeated
identical failures call for a different diagnosis, not an unchanged retry loop.
Inspect available tool APIs once; switch to a supported path when one is unavailable.
Reuse tooling: broad OS app/process discovery, browser reinstallation and framework
setup are unnecessary for ordinary local web QA. Stop only the servers and browser
sessions created for this task.

Honor required project/platform/release gates. Report what passed on which
revision, what was retained, coverage gaps and any unresolved failure. A skipped
or unavailable check is not a pass. When GitHub checks are required, wait for all
required jobs on the exact latest revision before describing it as verified.
