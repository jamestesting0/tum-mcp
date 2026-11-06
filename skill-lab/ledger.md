# Skill lab ledger

One entry per round, added with `lab ledger add ROUND --decision FILE`. Entries are written in
general terms: no course text, quotes, names, links, local paths or personal data. Raw evidence
stays in the gitignored `.omo/skill-lab/`. Later rounds read this file first.

## pattern-pilot-3 (2026-11-01)

- scenario: exam-patterns; confirm: None
- author: codex:gpt-6.1-terra:xhigh; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness
Exam patterns taught forking methods as flat step lists with prose pitfalls; picked by human
review of the course app and the user's own revision notes.

### Edits
| File | Change | Observed difference | Verdict |
| --- | --- | --- | --- |
| prepare-exams patterns reference | Decision steps with cases, one guided example per case, practice per case, wrong/right/why pitfalls | Course A: every pattern gained a decision step, but each invented a degenerate input (an empty sample, a single object) to have one; which-case feedback for the wrong case only said it did not apply. Pitfalls showed real wrong and corrected lines. | confounded |
| prepare-exams patterns reference, revised after course A | Forks only where exam questions need different moves; no degenerate inputs; feedback names the deciding given | Course B: no degenerate cases and feedback named the givens, but both patterns used a first-step decision to merge separate methods under the pattern limit, leaving a vague "apply the selected operation" step. | confounded |
| review-course skill, profiles, rubric and gallery | Patterns scored as items with pattern checks and calibration cases | Course A's review: the reviewer flagged practice that reused the example setting, but missed the invented forks and the weak feedback, and left most dimensions unscored because browser checks cannot run in the trial sandbox. | no observed effect |
| review-course gallery, degenerate-fork case added after course A | One calibration case for an invented fork | Course B's review: the reviewer flagged the merged methods under fork placement but kept them to respect the pattern limit, and again left the dimensions that need a browser unscored. | confounded |
| prepare-exams and review-course, revised after course B | A pattern limit is met by covering fewer question families, never by merging methods; pattern questions before scoring; every dimension scored when a check cannot run; merged-methods calibration case | Not yet re-run. | confounded |
| lab variant install | The working-tree base now includes new untracked, non-ignored files | The first runs lacked two new app modules and a guide page, so the review could not render; the rerun install contained them. | helped |

### Lesson
Cue: a skill adds an optional structure with completeness rules. Lesson: in the prepare-exams
patterns reference, say when the structure is not used and name its misuses (invented
degenerate cases, merged methods); add each misuse as a review calibration case. Evidence: the
first two rows. Confidence: low, one run per course. Models: codex gpt-6.1-terra xhigh.

### Decision
Revised. Keep the decision-step design and ship the guidance revisions; re-test on a course with
several past papers, and in a trial host that can run the browser checks, before relying on the
review checks. Not committed yet.

## formula-meanings (2026-11-01)

- scenario: exam-patterns-quantum; confirm: None
- author: codex:gpt-6.1-terra:xhigh; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness
Formulas outside Study gave no way to recall what their variables mean; picked by human
review of the course app.

### Edits
| File | Change | Observed difference | Verdict |
| --- | --- | --- | --- |
| Schema, build and app (variable meanings) | Derivations and applied formulas carry `symbols`; applied and cheatsheet formulas require them; a meaning reaches every formula of its context; a click opens it | One trial on a formula-heavy course: every applied formula carried meanings; Study derivations marked only compound or earlier-defined variables (two to five per lesson); no renamed, echoed or unexplained prompts. | confounded |
| prepare-study variables reference, linked from the three prepare skills | When a variable needs a meaning, when to leave it, how to phrase it, once per context | Meanings were short and contextual; the same meaning was still written again on several formulas of one pattern, and bit-index meanings stayed generic. | confounded |
| review-course rubric, profiles and calibration | `clarity.symbols_recall`; a meaning shown on demand is the one explanation | The review scored every dimension, capping the browser-dependent ones at 2, where the previous run left them unscored. | helped |
| prepare-exams patterns reference (earlier revisions, first re-run) | No invented forks; one pattern per method under a pattern limit | Both patterns were single methods without decision steps; no invented degenerate cases. | confounded |
| LaTeX validation | Reject control characters, which single-backslash JSON escapes produce | The trial wrote four such strings before the check existed; the build had accepted them. Its own review repaired them. | not yet re-run |
| study report | `redeclared_meaning` prompt for a meaning written on several formulas of one context | Added after this run. | not yet re-run |

### Lesson
Cue: a skill asks authors for LaTeX inside JSON. Lesson: validate LaTeX strings for control
characters at build time, since single-backslash escapes pass every other check. Evidence: the
LaTeX validation row. Confidence: medium, four cases in one run. Models: codex gpt-6.1-terra
xhigh.

### Decision
Shipped to the working tree. Keep variable meanings as designed; re-test the report prompts and
the escape check on the next real course preparation, including an exercise sheet. Not
committed yet.

## cohesion-polish (2026-11-01)

- scenario: exercises-quantum; confirm: None
- author: codex:gpt-6.1-terra:xhigh; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness
Human review of the course app: misaligned derivations, repeated or wrong variable marks,
pitfalls without context, uneven control spacing, stale comments, and Study prose with abrupt
transitions; exercises were not yet piloted.

### Edits
| File | Change | Observed difference | Verdict |
| --- | --- | --- | --- |
| prepare-exams patterns reference and schema | Pitfalls need a `situation` | When the build rejected the four existing pitfalls, the trial gave each a specific task moment, naming the formula or state involved. | helped |
| Variables reference and schema (decorated forms, task quantities, generic meanings) | Decorated variables need their own meaning; lone letters count in tasks | The guided exercise defined its givens in a table and gave the polar-form variables specific meanings; no unexplained, generic or renamed prompts; one unexplained prompt left in a lesson. | confounded |
| Figures reference and app (LaTeX labels) | A math label is written as inline LaTeX and typeset | The new lesson's drawing labelled its point as LaTeX, rendered like the text. | helped |
| review-course rubric, profiles and calibration (Cohesion) | Tenth item dimension | Every item scored Cohesion 3 with evidence that describes order and placement, not a quoted transition; the review recorded no content finding on eight items. | not yet re-run |

### Lesson
Cue: a review scores its own course in the session that wrote it. Lesson: a 3 needs evidence
tied to each check and to a passage, or the review passes everything. Evidence: the Cohesion
row. Confidence: medium, every item in one run. Models: codex gpt-6.1-terra xhigh.

### Decision
Shipped to the working tree. Keep the situation field, LaTeX figure labels and variable rules;
an extra lesson the review adds for understanding is fine. Plan check-level review evidence
next and re-test Cohesion then. Not committed yet.

## review-rigor (2026-11-01)

- scenario: review-quantum; confirm: None
- author: codex:gpt-6.1-terra:xhigh; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness

One Codex gpt-6.1-terra xhigh review turn (4 min) on the cohesion-polish quantum course with seven planted defects found and undid 5 of 7: the wrong result, the meta line, the described pitfall, the dropped section opening and the misplaced section. It missed a paragraph whose point was moved to its end (cohesion.point_first) and a derivation whose variable meanings were removed. It never ran `study review-pack` and wrote no scorecard: because the browser interaction pass could not run in the sandbox, it left every item stale. `study visuals --exam` crashed on untitled Exam figures.

### Edits

- review-course: each pass starts from its review-pack, a fresh session gets the pack as its brief, and the scorecard is always saved; a pass that could not run in full is recorded and caps its dimensions at 2.
- study visuals: an untitled Exam visual is headed by its key (test added).
- lab calibrate: each defect is checked as undone (opening, order and meanings restored, or probe text gone), findings from before planting are ignored, and defects sit in separate blocks.
- Completion audit: per-check closest calls now require a quote, its exact content path and a reason; findings need a real check, location and fix, and item scores must equal their accepted findings' severities. Checks-passed counts exclude unexamined checks. Report-proven failures are prefilled; heuristic silence does not count as semantic success.
- The calibration catalogue now covers all ten dimensions. Rejected findings and findings for a different check cannot count as detection. The host broker allows only supported visual-check options and workspace-bound projects, with a bounded execution time.

### Lesson

The render broker works: the trial ran `study visuals` on the host and fixed its own label overlaps from the result. A review skill that makes its record depend on checks the host cannot run gets no record at all; the record must be saved with the gap named.

### Decision

Keep the implementation and its regression gates. The pilot corrected 5 of 7 seeded defects,
but it produced no current verified scorecard; this measures corrections, not validated
reviewer recall. The post-pilot skill changes have not had a second model trial under the
one-pilot budget. No claim of improved reviewer accuracy is established. Interaction review
still needs a browser session. The MCP spike was omitted in favor of the smaller lab-only
shim broker, whose actual host render execution was demonstrated by this trial.

## cheatsheet-coverage (2026-11-02)

- scenario: cheatsheet-fai; confirm: None
- author: codex:gpt-6.1-terra:xhigh; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es); resumed from pattern-pilot-3/fixed-1@5 (FAI)

### Weakness

One Codex gpt-6.1-terra xhigh trial (two turns, about 7 minutes) wrote a twelve-entry sheet for
two topics with section paths, two `workflow_from` methods and ten exam requirements, then ran
`study review-pack --item exam/sheet --pass cheatsheet` and saved a scored sheet review with one
accepted representation finding. Every requirement came from the past exam: the report listed
17 content sources without requirements, and the review still scored coverage 3. Pitfalls and
details typed mathematics as characters (Greek letters, ≥, m−1), two displayed formulas wrote
quotients with a slash, one line repeated its own formula, and meaning lists that named a
variable as bare LaTeX (`\lambda` instead of `\(\lambda\)`) showed the raw command in the app.
The entries were formula-led, which fits these statistics topics; a significance entry that
reads naturally as a two-by-two decision table stayed a line, and the review did not flag it.

### Edits

- Coverage: `unrecorded_sources` is an invariant on the sheet's coverage, raised while any
  current content source has no exam requirement; the sheet cannot score coverage 3 with it open.
  The cheatsheet guide says a request limited to one past exam or some topics still reads the
  lecture material, and an unrelated source gets one `out_of_scope` requirement with a reason.
- `exam-report` and the sheet's review pack report typed mathematics (`sheet_plain_math`,
  invariant), slash quotients in displayed formulas (`slash_quotient`, fix or keep; units and
  derivatives excluded) and a line repeating its formula (`line_repeats_formula`).
- App: meaning-list symbols render as mathematics whether written `\(\lambda\)` or `\lambda`,
  in cheatsheet entries and Study formula blocks (browser regression added).
- Notation: a slash inside a fraction avoids nesting another fraction.

### Lesson

The new review route works end to end: the trial found the pass, saved a verified sheet review
and used sections and `workflow_from` unprompted. Advisory report lines were read but not acted
on; a coverage gap must be an invariant to change a score.

### Decision

Keep the implementation and the post-pilot gates. Representation diversity on non-formula
material is not yet shown by a trial: this course's sampled topics were formula-led. The
post-pilot fixes have tests and a rebuilt view of the trial's sheet but no second paid trial.
No lecture trial was run, by the user's choice.

## cheatsheet-coverage-2 and cheatsheet-coverage-3 (2026-11-02)

- scenarios: cheatsheet-fai-2 (resumed from pattern-pilot-3/fixed-1@5), cheatsheet-fai-fresh (empty folder)
- author: codex:gpt-6.1-terra:xhigh; base: WORKTREE + 0 patch(es)

### Weakness

Neither trial could test non-formula cheatsheet material. Both chose two non-statistics lectures
(search, constraint satisfaction, intelligent agents) and declined to author entries because only
text extracts of the slides were local: a resumed run has no original files (the lab removes each
run's downloads), and the fresh sync stored text records only. Following prepare-exams ("look at
every slide page you rely on"), the agent asked for the PDFs instead of writing from extracts.

### Decision

No skill change. Declining to author from unverifiable extracts is the intended behaviour. The lab
cannot yet supply original Moodle files to a Codex trial, so representation diversity on
non-formula material remains untested by a trial.

## cheatsheet-coverage-4 (2026-11-02)

- scenario: cheatsheet-fai-fresh (empty folder); author: codex:gpt-6.1-terra:xhigh; base: WORKTREE
- lab fix first: Codex trials get their Moodle download folder as an extra writable folder

### Weakness

The trial synced FAI, downloaded the lecture PDFs and wrote twelve entries on search and constraint
satisfaction in sections, then reviewed them (turns of 9, 25 and 37 minutes). Coverage now held:
56 exam requirements over 41 sources, 31 of them `out_of_scope` with reasons. Entries were mostly
text with two tables; a variable legend was written as a prose paragraph and table cells typed
variables as plain letters (`b,d`), and nothing flagged either. The review scored clarity,
representation and organization 2 only because it could not open the app interactively, not for
content: the save-with-gap rule capped content dimensions a browser check does not judge. The run
ended "failed" on a host websocket disconnect after the last turn's work was saved.

### Decision

Keep. Follow-ups (user): desktop-only checks by default; Study prose checks and variable meanings
for maths in cheatsheet details; a collapse control for long entries; only checks that need the
browser cap the dimensions they judge.

## pilot-terra-high (2026-11-05)

- scenario: workspace-sections; confirm: None
- author: codex:gpt-6.1-terra:high; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness
A cheap pilot (one Study lesson, one guided exercise, one cheatsheet section; 18 minutes)
of the per-item review-loop harness. The agent followed the draft checks, but: the plan gate
was self-checked yet recorded as fresh (`plan-record` defaulted to fresh) and no command could
check plans freshly; a definition taught only by restating itself passed the plan check; the
cheatsheet was never linted, and its lint failed on a course-wide coverage flag no scoped
draft can clear; the snapshot error hid its cause and the content contract described the
per-item layout wrongly, so the agent read the package source; the lab refused `--interact`;
text-only scenario questions and a visual-free guide raised nothing; a link-less two-entry
semester map took a full screen; the student message cited a skill file.

### Edits
| File | Change | Observed difference | Verdict |
| --- | --- | --- | --- |
| sync, lint, plans, report, exam map | Snapshot errors name the field; lint lists items and does not block on course-wide flags; definitions need an example; advisory text_only_question flag; map hidden without links | On the trial's course the new checks fire where the review later found problems | keep |
| review CLI, runner | `run-checker --plans`; `plan-record` defaults to same | Synthetic tests | keep |
| lab broker and shim | `--interact`, `--json` and a lab-chosen read-only checker on the host | The next round's trial ran every interaction check | keep |
| prepare skills, content contract | Sheet lint, per-item layout, plan gate commands, asking without citing files, derived outcome states | Not yet re-run | pending |

### Lesson
Cheap trials expose harness friction fast: every time the agent read the package source, a
message or contract was missing. Self-checks must be recorded as such by default.

### Decision
Keep all. Confidence: medium, one run; content edits not yet exercised by a new authoring trial.

## loop-terra-high (2026-11-05)

- scenario: workspace-sections-review; confirm: None
- author: codex:gpt-6.1-terra:high; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness
The review loop's first trial (two rounds, 6 minutes) on the pilot's course after its fixes.
Checkers were host subagents forked from the maker's session, so not fresh. The one-section
cheatsheet could never pass: a course-wide flag (sources without exam requirements) became a
coverage finding against the item. Seven `review fix` calls failed on a content error that
named the merged document path instead of the item file. Checkers passed the text-only
advisory flags without ruling on them. The last round's fixes ended unverified, so 1 of 3
items passed. The agent guessed lint arguments and `--help` went to the broker.

### Edits
| File | Change | Observed difference | Verdict |
| --- | --- | --- | --- |
| review loop, checks registry | Course-wide flags hold a separate `course` gate entry; sheet inventory check scoped to sources the sheet read; scorecard and status count fixes awaiting a check | On the trial's course the sheet's coverage now shows under `course`; status names the extend step | keep |
| content errors, lint, shim | Errors name the item file; lint all items or a bare key; help runs locally | Synthetic tests | keep |
| review-course skill, checker prompt | Forked subagents are not fresh; every report flag is a finding or ruled out in evidence | Not yet re-run | pending |

### Lesson
A scoped review must separate item quality from course-wide coverage, and a host's subagents
are fresh only if they start empty. The last round's fixes always end unverified; say so.

### Decision
Keep all. The loop itself worked end to end: packets, records, fixes, verification and the
gate behaved as designed; 11 findings opened, 5 verified, none rejected. Confidence: low, one run.

## loop-quality (2026-11-06)

- scenario: workspace-sections-review; confirm: None
- author: codex:gpt-6.1-terra:high; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness

The earlier two-round baseline passed informal definitions, prose-heavy explanation
and text-only practice. This candidate used the same saved starting point and model;
the baseline was not rerun.

### Edits

Per-concept teaching evidence, refined-definition flags, quoted verification of
rewritten passages and required advisory rulings were exercised by the candidate.
Its two rounds took 20.4 minutes, versus 6.2 for the saved baseline. The candidate
corrected both definitions to the precise conditional form, added a concrete test
instance and improved the opening. It recorded 29 findings versus 11 in the baseline,
but those totals do not measure recall. Invalid visual answers and queued broker
requests prevented an efficient, fully verified result. The gate stayed closed.

Post-trial corrections make missing question context non-waivable, flag run-together
labelled steps, demand source evidence for objectives, and show exchanges instead of
narrating them. A finding ruling must name its relevant check. The runner permits one
targeted answer repair, broker requests run independently, and plan errors name the
needed example link. A measured zero-gap definition transition was repaired.

### Lesson

A required ruling is insufficient when a checker can waive a true invariant.
Use code for reliable missing-context detection, require a relevant finding for a
finding ruling, and keep semantic checks critical of their own source interpretation.
One candidate is evidence of better corrections, not proof of general reviewer
accuracy or final content quality.

### Decision

Keep the harness corrections and their focused tests. The raw candidate is not
gate-passing: 18 fixes await fresh verification and other sheet gaps remain open.
Post-trial semantic guidance has not had a third model run. Preserve that limit
rather than calling this content ready to publish. No baseline rerun or release.

## search-quality (2026-11-06)

- scenario: search-sections-review; confirm: None
- author: codex:gpt-6.1-terra:high; probe judge: codex:gpt-6.1-sol:xhigh
- base: WORKTREE + 0 patch(es)

### Weakness

The conceptual pilot did not establish that harder procedural teaching would work.
This fresh authoring trial prepared one algorithmic lesson, one released exercise
and one sheet section, followed by at most two review rounds.

### Edits

The trial used codex gpt-6.1-terra high and took 33.5 minutes. Reviews caught incomplete
priority-frontier updates, cutoff rules, trace reasons, hints, citations and an
unsupported comparison of asymptotic bounds. Eleven findings were freshly verified;
22 late fixes were explicitly left unverified. The gate remained closed.

Independent keys compare 51 final lesson/exercise values and states successfully.
Installed-browser review at desktop and phone widths exercised trace navigation,
Guide and Solution without page errors or page-level overflow. Phone comparison
tables still had tall cells. The trial is not a mobile-quality pass.

The original walkthrough-inspection crash was reproduced from the saved authored
content and fixed by inspecting its stage. Browser tests cover that path, passage
spacing and the search glyph, whose missing shared styling was found visually.
Post-trial guidance prevents filler second calculations, glossary-style expansion
to satisfy retrieval coverage, and long conditions repeated inside compact cells.

### Lesson

A review loop can improve correctness while making teaching longer and less focused.
Evaluate its edits as content: a second example must add reasoning, and retrieval
coverage must not silently expand a narrowly requested lesson. Real rendering found
a crash and an icon defect that schema and semantic checks alone missed.

### Decision

Keep the concrete runtime fixes, gate protections and revised guidance. Do not claim
that a two-round budget makes the authored course ready: late fixes and phone-table
defects remain visible in the saved trial. The final rule revisions have focused
regression evidence, not another model trial. No baseline rerun or release.

## solo-four-spaces (2026-11-06)

- scenario: multi-course-workspaces; one solo candidate, no baseline rerun
- author and independent checkers: codex:gpt-6.1-terra:high
- base: WORKTREE; post-pilot repairs evaluated separately

### Weakness

The previous pilot did not establish quality across all four workspaces or across
different subject demands. This batch prepared three lessons, two released
exercises, two exam patterns and lecture notes.

### Observation

Authoring took about 40.1 minutes. The review turn reached its 45-minute deadline;
the recorded run failed after 85.7 minutes. No project gate passed. Reviews made
useful corrections but also repeated findings, demanded lesson-style teaching in
revision workflows, treated independent practice as guided practice and confused
new authored values with claims of source provenance.

Direct inspection found equation clipping missed by empty visual selections,
phone overflow from long inline mathematics, ineffective misconception examples,
an incomplete public event path, and audio decoding that rejected small accumulated
clock jitter. Runtime repairs have focused regressions and real-content evidence.
The decoder still rejects an actual missing-frame-sized PCM deficit.

The primary completed the selected lecture after the fix, compared the recovered
transcript with materials and inspected its meaningful source image. This is
ASR/material/image evidence, not independent source-audio listening.

### Edits and evidence

- Checkers now receive canonical workspace guidance with their packets. A focused
  fresh revision review accepted the concise workflow, independent drill and
  authored application values while retaining a useful reasoning finding.
- The first probe answer and its automatic repair failed evidence validation.
  Explicit manual recovery obtained the required concept-to-instance evidence;
  the validator was preserved. The prompt now names the required field directly.
- A fresh software review found further teaching defects, and one alleged plan
  ordering requirement unsupported by the saved plan. Primary corrections improve
  the example, practice and rendered explanation; they are not called freshly
  verified model verdicts.
- Organization checks no longer require duplicate course maps or extra lessons to
  fill a bounded single-unit group. Genuine missing coverage remains separate.
- Desktop and phone inspection exercised the actual learning controls. Formula
  clipping and page overflow are fixed; long code and indivisible calculations
  can still require local horizontal scrolling.

### Decision

Keep the surgical runtime repairs and refined guidance. Preserve the failed
original run and distinguish its results from primary repairs and focused probes.
This round does not establish reliable automatic convergence, student learning
gains, lower model cost or publication readiness. No commit, push or release.

### Final release correction pass (2026-11-06)

Reused the existing prepared items without regenerating a baseline. Eight fresh
packets recorded in the first bounded pass; the second recorded seven directly and
one after explicit recovery of a missing visual-note field through normal validation.
The correction pass found and fixed three protocol defects: named-list reordering
did not invalidate review evidence, accepted answers could leave an old refused
answer artifact behind, and the answer example omitted the note required for weak
visual scores. Targeted regressions reproduce each defect.

Removed internal per-finding fingerprint history from checker inputs while retaining
it in the ledger: 11.9% fewer serialized characters across 27 measured packets.
This is a size measurement, not a claimed timing improvement. Lecture notes can now
use the shared sourced SVG renderer without pretending an authored drawing is a
recording frame; source, SVG-safety and semantic-revision checks remain enforced.

Final primary corrections addressed coefficient feedback, redundant trace labels,
guide wording and structure, explicit state dispatch, and the illustrated search
comparison. Six keys verify 35 nonduplicated fields; removed duplicate columns remain
covered in the combined action/state checks. Desktop/phone inspection and native
authored-Java execution pass. These are primary repairs after review, not evidence
that the original author autonomously completed a satisfactory course or passed all
publication gates.

At the user's request, obsolete pilot caches were removed while concise results,
the active verification workspace and account profiles were preserved. Old-format
compatibility work was dropped. Installed consumer fixtures were ported to the
per-item layout; installation, browser journeys and lifecycle safeguards were kept.
