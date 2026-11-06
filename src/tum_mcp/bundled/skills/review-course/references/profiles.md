# Workspace profiles

Read the shared [rubric](rubric.md), then apply the row for the artifact being reviewed.
Profiles change the evidence and checks, not the meaning of 1, 2 and 3. Equal scores
across different artifacts do not establish equal difficulty or learning value.

## Study

Use the ten item dimensions. Read as a student meeting the topic for the first time who
knows the teaching profile's prerequisites. Judge the explanation with Explore and
insights closed before reviewing optional teaching. Practice requires new application cases, not new wording for a worked
case; retrieval cards may recall definitions. Coverage follows assigned core outcomes,
not every page of a source. Judge derivation variable meanings by `clarity.symbols_recall`:
meanings where a reader would stop to recall a variable, none on the obvious ones.

## Exercises

Use the same ten dimensions, with these replacements for Study-specific checks:

| Dimension | Exercise evidence |
| --- | --- |
| Correctness | Compare the released statement, givens and each requested result against the source. Recompute solutions and Compare answers; state conventions before they matter. |
| Coverage | Map every original part, including secondary demands such as feasibility, to its answer. A matching part label alone is not completeness. |
| Practice | Hints offer a next move without giving the result. Steps give the student increasing responsibility where the task permits it. Compare answers precisely the step's demand; an authored transfer changes a meaningful condition. |
| Intuition | Judge the guide and solution: why each move is allowed, what choice it resolves and where its assumptions matter. Do not demand a lesson-style opening, a new worked example or a misconception for every released question. |
| Organization | Preserve original part order and put each guide immediately after its part and supporting blocks, using `part_blocks`. Check this with guides closed and open. Use prerequisites for earlier teaching instead of adding a second lesson. |
| Cohesion | Shared checks on the statement, each guide step and the solution: each step follows from the one before and says so where a student could not tell (`cohesion.linked`). |
| Clarity | Shared checks, plus `clarity.symbols_recall` on the Guide's and Solution's derivations: a variable the student must recall from the lecture or an earlier part opens its meaning in this exercise, with its value when the task gives one. |

Cognitive load, representation and redundancy retain their shared checks.
Statements keep every given and task verbatim, but omit the sheet's framing sentences
that contribute neither. `meta_reference` reads statements as well as guides and solutions.
Do not change a released case to satisfy `practice.new_case`: apply that check to authored
transfer practice, not the original problem. Do not penalize the same missing answer in
Practice and Coverage: a missing original demand belongs to Coverage; a Compare answer
that fails its step belongs to Practice.

Use existing check ids, with `correctness.statement_fidelity`, `practice.student_control`
and `intuition.method_choice` for these specific checks. A finding still belongs to one
dimension. If no guide or solution exists to judge, record the gap; never award an
automatic 3 because the Study check does not apply.

Judge repetition in the rendered view: a Guide answer and a full Solution must each
work when opened separately. An independent Exam drill shows its model answer and
optional worked solution in one panel, so repeating the same working there is a defect.

## Exam

Exam patterns are scored items (`exam/pattern/<key>`) with the ten dimensions. The
cheatsheet is one item (`exam/sheet`) read in the single `cheatsheet` pass on six
dimensions with the rubric's [Cheatsheet](rubric.md#cheatsheet) checks. Past papers and
practice exams are not items: use `study exam-report` as evidence and record their
findings in the course pass; do not invent item keys for them.

Read as a revising student who has studied the material. Exam stays concise and never
re-teaches: depth is one tap away through Recall, which must open the passage that
teaches each concept. Past papers and practice exams show no Recall before the attempt,
because recognising the pattern is the skill they practise.

- Cheatsheet: start from its packet (profile `exam-sheet`) and the coverage report's
  `cheatsheet` section. Open the cited source pages and look for
  exam-relevant material of any kind that no entry holds before judging the entries. A
  complete one-line fact needs no expansion; a method needs its steps, a formula its
  meanings, a comparison its table. A correct entry need not introduce its concept with a
  worked example.
- Pattern: before scoring, answer: does a listed exam question need each decision step and
  each case (`cognitive_load.moves_fit`)? Do the cases share the steps around them, or is
  each a different method that needs its own pattern (`organization.fork_placement`)? Does
  every which-case feedback name the given that decides it (`practice.case_feedback`)? Does
  each step or case that uses a formula, rule or code show it under `apply`, and is each
  pitfall the actual wrong working in the task moment where it happens, with its rule
  (`representation.shown_not_described`)? Does every applied formula open its variables'
  meanings in this pattern, without the text restating them (`clarity.symbols_recall`)?
- Pattern: score it with this table; the shared checks apply unless a row replaces them.

  | Dimension | Pattern evidence |
  | --- | --- |
  | Correctness | Recompute every example, part and Practise answer; each case's move is valid for its condition; cases never overlap (`correctness.cases_exclusive`); pitfall lines are really wrong and right, and sourced. |
  | Coverage | Every listed past instance and example needs only the listed cases (`coverage.cases_complete`). |
  | Clarity | Cues name what the question shows, never the concept; each case reads as a visible condition and one move (`clarity.case_observable`); every applied formula's variables open their meaning in this pattern, and every cheatsheet formula lists its variables' general meanings (`clarity.symbols_recall`, strict). |
  | Cohesion | Only `cohesion.one_term` and no unexplained jump between steps; no linking sentences. |
  | Cognitive load | Workflow steps, cases and pitfall lines stay one line each; no case the exams do not need. |
  | Representation | Every step or case whose move uses a formula, rule or code shows it under `apply`, written as the answer uses it; pitfalls show the wrong working or code itself, in the task moment where it happens (`representation.shown_not_described`). |
  | Practice | Which-case feedback names what decides each case (`practice.case_feedback`); Practise items are new settings and neighbours need different cases (`practice.interleaved`). |
  | Intuition | Each step and case says why its move fits; each pitfall names the rule its wrong line breaks; conditions are checked where the method has them (`intuition.reasons`, `intuition.limits`). |
  | Organization | Lookups stay in the cheatsheet, forks are decision steps, different first moves are separate patterns (`organization.fork_placement`); examples are shaped like the exam's questions (`organization.example_shape`). |
  | Redundancy | Cases, reasons and pitfalls do not restate each other or the cheatsheet (`redundancy.said_once`, `redundancy.exam_compresses`). |
- Past paper or mock: every demand has an answer; points reconcile; official, authored
  and inferred marking remain distinct. Compare coverage with the available blueprint,
  recording missing evidence rather than presenting historical frequency as a prediction.

## Lecture

Each note and highlight is a separate `lecture-entry` item. Record its findings
against that item and check the recording/transcript evidence before judging fidelity.

- Check claims, limiting conditions and timestamps against the supplied recording evidence.
- Each note's title and context let a student who missed the lecture see what the remark
  answers. Context unsupported by the evidence, or a message that only makes sense with the
  lecture in mind, is a finding against that entry.
- Preserve useful explanations beyond the slides, without copying an entire Study lesson.
- Check processed and missing intervals; a complete-looking passage does not prove full
  recording coverage.
- Judge structure and visuals with the shared checks. Do not require quizzes, flashcards,
  invented prediction prompts or a rearranged recording to satisfy Study's teaching moves.
- Check visual value: where the lecturer's board, slide figure or demonstration carries
  the explanation (a spatial picture, notation, a circuit, hardware), the section shows a
  legible, source-backed visual near the passage: a course-material figure cited by page,
  a captured frame, or a drawn diagram that is not presented as a capture. A text-only
  section is fine when a picture would add nothing; a missing central visual is a
  `representation.shape_fits` finding.

Synthetic template examples can test whether a check is usable. They cannot validate
recording fidelity, real-exam representativeness or learning outcomes.

## Audio and Video Notes

Use the separate [media profile and evidence contract](media.md): eight dimensions
for hands-free audio, ten for concept or Exercise video, never Practice. The actual
source variant selects the profile. Page reviews and media reviews have distinct
revisions and averages. Technical success is not listening/playback evidence.
