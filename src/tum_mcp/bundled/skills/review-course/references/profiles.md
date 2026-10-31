# Workspace profiles

Read the shared [rubric](rubric.md), then apply the row for the artifact being reviewed.
Profiles change the evidence and checks, not the meaning of 1, 2 and 3. Equal scores
across different artifacts do not establish equal difficulty or learning value.

## Study

Use the nine item dimensions. Judge the explanation with Explore closed before reviewing
optional teaching. Practice requires new application cases, not new wording for a worked
case; retrieval cards may recall definitions. Coverage follows assigned core outcomes,
not every page of a source.

## Exercises

Use the same nine dimensions, with these replacements for Study-specific checks:

| Dimension | Exercise evidence |
| --- | --- |
| Correctness | Compare the released statement, givens and each requested result against the source. Recompute solutions and Compare answers; state conventions before they matter. |
| Coverage | Map every original part, including secondary demands such as feasibility, to its answer. A matching part label alone is not completeness. |
| Practice | Hints offer a next move without giving the result. Steps give the student increasing responsibility where the task permits it. Compare answers precisely the step's demand; an authored transfer changes a meaningful condition. |
| Intuition | Judge the guide and solution: why each move is allowed, what choice it resolves and where its assumptions matter. Do not demand a lesson-style opening, a new worked example or a misconception for every released question. |
| Organization | Preserve original part order and put each guide immediately after its part and supporting blocks, using `part_blocks`. Check this with guides closed and open. Use prerequisites for earlier teaching instead of adding a second lesson. |

Clarity, cognitive load, representation and redundancy retain their shared checks.
Do not change a released case to satisfy `practice.new_case`: apply that check to authored
transfer practice, not the original problem. Do not penalize the same missing answer in
Practice and Coverage: a missing original demand belongs to Coverage; a Compare answer
that fails its step belongs to Practice.

Use existing check ids, with `correctness.statement_fidelity`, `practice.student_control`
and `intuition.method_choice` for these specific checks. A finding still belongs to one
dimension. If no guide or solution exists to judge, record the gap; never award an
automatic 3 because the Study check does not apply.

## Exam

The current scorecard accepts Study and Exercises items, not Exam items. Use
`study exam-report` as evidence and record artifact-specific findings in the course pass;
do not invent item keys or fold these into Study averages.

- Cheatsheet: compressed but sufficient conditions, readable formulas and useful retrieval
  cues; a correct entry need not introduce its concept with a worked example.
- Pattern: cues distinguish when the method applies; workflow explains choices and limits;
  its example and new-case practice exercise the same method without copying the case.
- Past paper or mock: every demand has an answer; points reconcile; official, authored
  and inferred marking remain distinct. Compare coverage with the available blueprint,
  recording missing evidence rather than presenting historical frequency as a prediction.

## Lecture

The current scorecard has no Lecture item scores. Record findings in the course pass
and check the recording/transcript evidence before judging fidelity.

- Check claims, limiting conditions and timestamps against the supplied recording evidence.
- Preserve useful explanations beyond the slides, without copying an entire Study lesson.
- Check processed and missing intervals; a complete-looking passage does not prove full
  recording coverage.
- Judge structure and visuals with the shared checks. Do not require quizzes, flashcards,
  invented prediction prompts or a rearranged recording to satisfy Study's lesson shape.

Synthetic template examples can test whether a check is usable. They cannot validate
recording fidelity, real-exam representativeness or learning outcomes.
