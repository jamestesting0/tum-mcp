---
name: review-course
description: Score how easy a local TUM course app's Study units and exercises are to learn from in five review passes (logic, text, visuals, interaction, intuition), save the scores with evidence, and fix what falls below the bar. Use after prepare-study or prepare-exercises, or when asked to review, rate or improve course content, its diagrams or its plots.
---

Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. Study content
lives in `app/content.json`, exercises in `app/exercises.json`. You score them in
`.tum-mcp/review.json`; code ties each score to the exact content it read, so an edited
unit or exercise needs a fresh review. Exam Prep keeps its own `study exam-report` review.

Score as the student meets the content, not from what you meant to write. When the host
can run a separate session or agent, let it score what you authored, because a judge
favours its own work; fix in the authoring session. Read the cited source pages again for
every item you score.

## Workflow

1. **List.** Run `tum-mcp study report PROJECT`. Its `review` section lists unreviewed
   and stale items with their current `revision` and the `visuals` each item draws;
   `render` lists items whose render check is missing, stale or failing. The `quality`
   and `coverage` sections are evidence for the scores, not a substitute for them.
2. **Render.** Run `tum-mcp study visuals PROJECT` (or `--unit KEY`, `--exercise SET/KEY`).
   It opens every lesson, practice question and exercise step at phone, narrow and
   desktop width, measures each drawn visual and writes contact sheets to
   `.tum-mcp/visuals/`. Fix every defect it reports in the content, never in the rule,
   until `render.passed` is true.
3. **Calibrate.** Run `tum-mcp study visuals PROJECT --gallery` and open the gallery
   sheets. Before the first item of a session, score three gallery pictures on the
   [visual rubric](references/visuals.md#rubric) without looking up their verdicts, then
   compare with [the gallery](references/visual-gallery.json). On any disagreement,
   re-read the rubric and the gallery's reasons before you score real content.
4. **Review in five passes.** Each pass reads the item for one thing, so nothing hides
   behind another:

   | Pass | What it checks | Guide | Scores |
   | --- | --- | --- | --- |
   | Logic | Facts, numbers, answers and conventions against the source | [logic](references/logic.md) | correctness, coverage |
   | Text | Every passage, read once as the student reads it | [text](references/text.md) | clarity, cognitive load |
   | Visuals | Every drawn visual, from the contact sheets and the render findings | [visuals](references/visuals.md) | each visual, representation |
   | Interaction | The item worked in the app at phone and desktop width | [interaction](references/interaction.md) | practice |
   | Intuition | Whether the student learns why, not only what | [intuition](references/intuition.md) | intuition |

5. **Score.** Give each of the seven dimensions 1, 2 or 3 using the
   [rubric](references/rubric.md), and each listed visual the six criteria of the visual
   rubric. A 3 means you checked it; when unsure, score lower. Every score below 3 gets a
   finding that names what the student meets and where (block title, visual key such as
   `block:3`, question or step key), precisely enough to fix.
6. **Save.** Write one review per item to `.tum-mcp/review.json` with the revision from
   the report, today's date and a score for every visual the report lists
   (`tum-mcp study schema review`). Keep reviews of items you did not re-read.
7. **Fix.** Revise each finding with prepare-study or prepare-exercises and their
   [review gate](../prepare-study/references/review.md); improve a visual below 3 with
   the [visual loop](references/visuals.md#improve). Build, render and report again.
   Edited items turn stale: re-read and re-score them, never copy the old score. Repeat
   until the report's `review.passed` and `render.passed` are true. A 1 is always fixed.
   A 2 may stay with `kept` only when the content cannot fix it (for example, the source
   gives no smaller example); say why.
8. **Report.** Give the averages, what you changed, what you kept and why, and any items
   you could not read. Scores describe this review, not mastery or exam readiness.

## Boundaries

Scores, findings, contact sheets and render results stay in `.tum-mcp/`; they are never
shown to students or published. Do not raise a score without re-reading the item, and do
not lower the bar to pass. A review does not authorize new sources: fetch missing material
through read-content, and record outcome gaps in the coverage ledger instead of guessing.
