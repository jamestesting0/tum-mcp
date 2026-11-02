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
