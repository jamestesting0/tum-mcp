---
name: review-course
description: Score how easy a local TUM course app's Study units and exercises are to learn from, save the scores with evidence, and fix what falls below the bar. Use after prepare-study or prepare-exercises, or when asked to review, rate or improve course content.
---

Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. Study content
lives in `app/content.json`, exercises in `app/exercises.json`. You score them in
`.tum-mcp/review.json`; code ties each score to the exact content it read, so an edited
unit or exercise needs a fresh review. Exam Prep keeps its own `study exam-report` review.

Score as the student meets the content, not from what you meant to write. When the host
can run a separate session or agent, let it score what you authored; fix in the
authoring session. Read the cited source pages again for every item you score.

## Workflow

1. **List.** Run `tum-mcp study report PROJECT`. Its `review` section lists unreviewed
   and stale items with their current `revision`; `quality` and `coverage` are evidence
   for the scores, not a substitute for them.
2. **Read.** Open each listed item in the app (`tum-mcp study serve PROJECT`) at phone
   and desktop width when the host can render pages. Work it as a student: read the
   lesson, step through every trace, answer each question and step before opening
   Compare or the solution, and recompute every number with code.
3. **Score.** Give each of the six dimensions 1, 2 or 3 using the [rubric](references/rubric.md).
   A 3 means you checked it; when unsure, score lower. Every score below 3 gets a
   finding that names what the student meets and where (block title, question or step
   key), precisely enough to fix.
4. **Save.** Write one review per item to `.tum-mcp/review.json` with the revision from
   the report and today's date (`tum-mcp study schema review`). Keep reviews of items
   you did not re-read.
5. **Fix.** Revise each finding with prepare-study or prepare-exercises and their
   [review gate](../prepare-study/references/review.md), build, then run the report
   again. Edited items turn stale: re-read and re-score them, never copy the old score.
   Repeat until the report's `review.passed` is true. A 1 is always fixed. A 2 may stay
   with `kept` only when the content cannot fix it (for example, the source gives no
   smaller example); say why.
6. **Report.** Give the averages, what you changed, what you kept and why, and any items
   you could not read. Scores describe this review, not mastery or exam readiness.

## Boundaries

Scores and findings stay in `.tum-mcp/`; they are never shown to students or published.
Do not raise a score without re-reading the item, and do not lower the bar to pass.
A review does not authorize new sources: fetch missing material through read-content,
and record outcome gaps in the coverage ledger instead of guessing.
