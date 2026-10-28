# Past papers and practice exams

## Replay a past paper

A variant is replayable when every question has a stored statement and solution.
Add `guidance` (objectives, steps with hints and checks, explanations) to the questions
worth practising step by step; the app then presents them like Exercises. Add `check`
and `marking` to support exam conditions with scoring. Follow prepare-exercises'
[guidance](../../prepare-exercises/references/guidance.md) for useful steps and hints.

## Write a forecast practice exam

Read `exam-report --section blueprint` first: profile (duration, points, aids, format),
historical topic shares and question formats. Design to that blueprint, then check:

1. **Coverage**: across all practice exams and pattern drills, every `core` concept is
   exercised (`exam-report` lists `uncovered_core`).
2. **Novelty**: every question is a `variant` of past questions or targets `untested`
   core ideas. A variant names the questions it varies and what changed: a cue,
   constraint, representation, combination or reversal. Changing only numbers
   (`scale`) is weak practice; keep it rare.
3. **Length and difficulty**: per-question minutes add up to the duration; the points
   match the real exam; the difficulty mix resembles past papers.
4. **Answers**: solve every question yourself; marking criteria add up to its points.
   Mark a criterion `auto` only when a deterministic check decides it.

`exam-report --section targets` flags gaps, similar statements and blueprint drift.
Near-verbatim copies of past statements are rejected by the build.

The app labels forecasts as AI-written practice, never as a prediction or a leak.
