# Past papers, mock exams and practice

## Replay a past paper

A variant is replayable when every question has a stored statement and solution.
Prepare task-specific `guidance` for every current classified past question assigned
to a pattern: objectives, steps, useful hints, checks and explanations. The student
may leave that guidance closed. A whole
paper shows every question with its solution and marking points behind a disclosure,
so students check themselves; there is no scoring. Follow prepare-exercises'
[guidance](../../prepare-exercises/references/guidance.md) for useful steps and hints:
one step per subgoal, and each step's explanation shows the full working that reaches
its answer. Keep the printed statement and add the picture in a step.

## Write a mock exam

Read `exam-report --section blueprint` first: profile (duration, points, aids, format),
historical topic shares and question formats. Use `kind: "exam"` and set
`duration_minutes`; `instructions` says what to answer and how. The app already shows
the time, points and aids, so never repeat them there.
A mock exam simulates the real exam's timing and blueprint.
Design to that blueprint, then check:

1. **Coverage**: match the real exam's topic shares and question formats within the
   prepared scope. For part of the course, use that part's questions and share of the
   time; never add topics the request left out. A mock exam need not practise every
   cheatsheet idea.
2. **Novelty**: every question is a `variant` of past questions or targets `untested`
   core ideas. A variant names the questions it varies and what changed: a cue,
   constraint, representation, combination or reversal. Changing only numbers
   (`scale`) is weak practice; keep it rare.
3. **Length and difficulty**: per-question minutes add up to the duration; the points
   match the real exam; the difficulty mix resembles past papers.
4. **Answers**: solve every question yourself; marking criteria add up to its points.
   The first sentence says what the student produces; the solution uses only what
   the question shows; if it needs a class, method or value, put it in the question.
5. **Shown, not only told**: every question pairs its text with the code, diagram, UML
   diagram, formula, table or plot it is about, chosen as in prepare-exercises'
   [content](../../prepare-exercises/references/content.md#show-the-question-not-only-tell-it).
   A coding question shows the code or signatures it builds on.

`exam-report --section targets` flags similar statements, blueprint drift and
guided past questions that stay text only. The build rejects text-only practice
questions and copies of past statements, even with text or code added around them.

## Write additional practice

Use a separate set with `kind: "practice"` for important core cheatsheet ideas that
the patterns and their drills leave unpractised. With few past papers, the patterns train
only the moves those papers asked. Compare each pattern's family with the lectures: a
method taught for it that no paper asked yet (a second algorithm for the same task, the
reverse computation, a variant of a design pattern) gets a practice question too.
The set is untimed; omit `duration_minutes` and `instructions`. No blueprint or timing
check applies.
Keep the same question, novelty, marking and solution standards as mock exams.
`uncovered_core` counts practice across patterns, mock exams and practice sets, per whole
entry, so it cannot see an unpractised method inside a practised entry.
It is advisory. Other uncovered ideas are fine and never block readiness.

The app labels forecasts as AI-written practice, never as a prediction or a leak.
