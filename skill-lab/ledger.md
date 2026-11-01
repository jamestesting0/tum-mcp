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
