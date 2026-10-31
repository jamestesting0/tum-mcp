---
name: review-course
description: Score how easy a local TUM course app is to learn from, unit by unit, exercise by exercise and as a whole course (organization, redundancy, and how Study, Exercises, Exam and Lecture connect), save the scores with evidence, and fix what falls below the bar. Use after prepare-study or prepare-exercises, or when asked to review, rate or improve course content, its structure, its diagrams or its plots.
---

Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. Study content
lives in `app/content.json`, exercises in `app/exercises.json`. You score them in
`.tum-mcp/review.json`; code ties each item score to the exact content it read and the
course score to the course's structure, so edited content needs a fresh review. Exam
items keep their own `study exam-report` review; the course pass reads Exam
for how it connects to the rest.

Score as the student meets the content, not from what you meant to write. When the host
can run a separate session or agent, let it score what you authored, because a judge
favours its own work; fix in the authoring session. Look at the cited source pages again
for every item you score: the PDF page, or `tum-mcp study text` with `--images`, not only
their text.

## Workflow

1. **List.** Run `tum-mcp study report PROJECT`. Its `review` section lists unreviewed
   and stale items with their current `revision` and the `visuals` each item draws,
   reviews missing a dimension (`unscored_dimensions`) and the `course` review's status.
   `render` lists items whose render check is missing, stale or failing. The `quality`,
   `structure` and `coverage` sections are evidence for the scores, not a substitute.
2. **Render.** Run `tum-mcp study visuals PROJECT` (or `--unit KEY`, `--exercise SET/KEY`).
   It opens every lesson, practice question and exercise step at phone, narrow and
   desktop width, measures each drawn visual and writes contact sheets to
   `.tum-mcp/visuals/`. Fix every defect it reports in the content, never in the rule,
   until `render.passed` is true.
3. **Calibrate.** Before the first item of a session, score three pictures of the
   [visual gallery](references/visual-gallery.json) on the
   [visual rubric](references/visuals.md#rubric) (`tum-mcp study visuals PROJECT --gallery`
   draws them), and three cases of the [structure gallery](references/structure-gallery.md),
   before reading their verdicts. On any disagreement, re-read the criterion or check
   before you score real content.
4. **Review each item in six passes.** Read its [workspace profile](references/profiles.md)
   first: an exercise guide is not a second Study lesson. Each pass reads the item for one
   thing, so nothing hides behind another:

   | Pass | What it checks | Guide | Scores |
   | --- | --- | --- | --- |
   | Logic | Facts, numbers, answers and conventions against the source | [logic](references/logic.md) | correctness, coverage |
   | Text | Every passage, walked as a first encounter, then read once as the student reads it | [text](references/text.md) | clarity, cognitive load |
   | Visuals | Every drawn visual, from the contact sheets and the render findings | [visuals](references/visuals.md) | each visual, representation |
   | Interaction | The item worked in the app at phone and desktop width | [interaction](references/interaction.md) | practice |
   | Intuition | Whether the student learns why, not only what | [intuition](references/intuition.md) | intuition |
   | Structure | The outline's order, and what the page says twice | [structure](references/structure.md) | organization, redundancy |

5. **Review the course.** After the items, read the course map, walk it as a first-time
   reader and as a returning student, and score course organization, course redundancy
   and, when listed, integration ([course](references/course.md)).
6. **Score.** Give each dimension 1, 2 or 3 by its checks in the
   [rubric](references/rubric.md), and each listed visual the six criteria of the visual
   rubric. A 3 means every check holds and you checked it; when unsure, score lower.
   Every score below 3 gets a finding with its check id that names what the student meets
   and where (block title, visual key such as `block:3`, question or step key, unit or
   exercise), precisely enough to fix. Score each problem once, under the dimension the
   rubric's owner table names.
7. **Save.** Write one review per item and one course review to `.tum-mcp/review.json`
   with the revisions from the report, today's date, every dimension and a score for
   every listed visual (`tum-mcp study schema review`). Keep reviews of items you did not
   re-read.
8. **Fix.** Revise each finding with prepare-study, prepare-exercises or prepare-exams
   and their [review gate](../prepare-study/references/review.md); improve a visual below
   3 with the [visual loop](references/visuals.md#improve). For a reordering or a merge,
   draft the new outline beside the old one and compare both against the course checks
   before you move anything; keep unit keys so progress survives. Build, render and report
   again. Edited items and a changed structure turn stale: re-read and re-score them,
   never copy the old score. Repeat until the report's `review.passed` and
   `render.passed` are true. A 1 is always fixed. A 2 may stay with `kept` only when the
   content cannot fix it (for example, the source gives no smaller example); say why.
9. **Report.** Give the averages, the course scores, the most failed checks
   (`failed_checks`), what you changed, what you kept and why, and any items you could
   not read. Scores describe this review, not mastery or exam readiness.

## Boundaries

Scores, findings, contact sheets and render results stay in `.tum-mcp/`; they are never
shown to students or published. Do not raise a score without re-reading the item, and do
not lower the bar to pass. A review does not authorize new sources: fetch missing material
through read-content, and record outcome gaps in the coverage ledger instead of guessing.

For units with Explore or changed optional classifications, include the
[core-only counterfactual review](../prepare-study/references/explore.md#review-with-explore-closed).
Optional teaching is part of the unit's accuracy/visual review; it cannot supply core
prerequisites, trace requirements or assessment coverage. Classification changes stale
the course review separately from students' core progress.
