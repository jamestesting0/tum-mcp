---
name: review-course
description: Review and improve prepared Study, Exercises, Exam patterns, audio revision, concept videos, exercise walkthroughs and course structure. Save source-bound scores with actual evidence, fix findings and re-review. Media needs real listening/playback; source and media scores stay separate.
---

When `tum-mcp study status PROJECT` reports `course_memory: true`, use
the installed `course-memory` skill for relationships and scoped source updates.
When disabled, leave retained graph files unused and follow the ordinary workflow.


Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. Study content
lives in `app/content.json`, exercises in `app/exercises.json`, Exam patterns in
`app/exam.json`. You score them in `.tum-mcp/review.json`; code ties each item score to
the exact content it read and the course score to the course's structure, so edited
content needs a fresh review. The cheatsheet, past papers and practice exams keep
`study exam-report` as evidence; the course pass reads them for how Exam connects to the rest.

Score as the student meets the content, not from what you meant to write. A judge favours
its own work, so each pass runs in a session that did not write the content (a subagent, a
new session) wherever the host allows; the authoring session only verifies and fixes. Look at the cited source pages again
for every item you score: the PDF page, or `tum-mcp study text` with `--images`, not only
their text.

## Workflow

1. **List.** Run `tum-mcp study report PROJECT`. Its `review` section lists unreviewed
   and stale items with their current `revision` and the `visuals` each item draws,
   reviews missing a dimension (`unscored_dimensions`) and the `course` review's status.
   `render` lists items whose render check is missing, stale or failing. The `quality`,
   `structure` and `coverage` sections are evidence for the scores, not a substitute.
   `review.media` discovers optional published/pending/broken media and required
   evidence. Apply [media](references/media.md) for audio and both video sources,
   not the ten-dimension page rubric or a Practice requirement.
2. **Render.** Run `tum-mcp study visuals PROJECT` (or `--unit KEY`, `--exercise SET/KEY`).
   It opens every lesson, practice question and exercise step at desktop width (add
   `--phone` for phone and narrow widths only when the user asks), measures each drawn visual and writes contact sheets to
   `.tum-mcp/visuals/`. Fix every defect it reports in the content, never in the rule,
   until `render.passed` is true.
3. **Calibrate.** Before the first item of a session, score three pictures of the
   [visual gallery](references/visual-gallery.json) on the
   [visual rubric](references/visuals.md#rubric) (`tum-mcp study visuals PROJECT --gallery`
   draws them), and three cases of the [structure gallery](references/structure-gallery.md)
   (two of its Exam pattern cases before you score patterns), before reading their
   verdicts. On any disagreement, re-read the criterion or check before you score real
   content.
   For media, use the actual [media pairs](references/media-gallery.md); missing
   sound/video perception remains an incomplete review, never a perfect score.
4. **Review each item in six passes.** Read its [workspace profile](references/profiles.md)
   first: an exercise guide is not a second Study lesson. Read the course's teaching profile
   and the unit's plan in `.tum-mcp/plans/` too; their decisions are the item's own
   checklist. Each pass reads the item for one thing, so nothing hides behind another, and
   starts from `tum-mcp study review-pack PROJECT --item ITEM --pass NAME`: its checks in full,
   the item's passages and the report prompts already raised. A fresh session gets the pack
   as its brief; it is what findings quote. Hunt for what fails: for every
   check, find the passage most likely to fail it. A failure is a finding with its check,
   the passage quoted word for word from the pack, its `location` (the pack's path), why it
   fails and the `fix`. For every check without an accepted finding, save a `closest_calls`
   entry keyed by that check: `quote`, `location` and `reason` explaining the borderline
   judgement (or why the check does not apply). A dimension with no failure also quotes its
   weakest passage under `evidence`. Report-proven failures arrive prefilled; an absent
   heuristic warning does not prove a semantic check passes. Record each pass under `passes`
   as `fresh` or `same` (its session).

   | Pass | What it checks | Guide | Scores |
   | --- | --- | --- | --- |
   | Logic | Facts, numbers, answers and conventions against the source | [logic](references/logic.md) | correctness, coverage |
   | Text | Every passage, walked as a first encounter, then read once as the student reads it | [text](references/text.md) | clarity, cohesion, cognitive load |
   | Visuals | Every drawn visual, from the contact sheets and the render findings | [visuals](references/visuals.md) | each visual, representation |
   | Interaction | The item worked in the app at desktop width | [interaction](references/interaction.md) | practice |
   | Intuition | Whether the student learns why, not only what | [intuition](references/intuition.md) | intuition |
   | Structure | The outline's order, and what the page says twice | [structure](references/structure.md) | organization, redundancy |
   | Cheatsheet | `exam/sheet` only, in place of the six: entries against the sources and the ledger's exam requirements | [profile](references/profiles.md#exam) | its six dimensions |

5. **Review the course.** After the items, read the course map, walk it as a first-time
   reader and as a returning student, and score course organization, course redundancy
   and, when listed, integration ([course](references/course.md)).
6. **Score.** Scores follow from the findings: a dimension with an accepted finding scores 2,
   or 1 when it blocks learning (the finding's `score`, [rubric](references/rubric.md));
   the scorecard enforces the lowest accepted finding's score. One without scores 3 with
   its closest call under `evidence`. Score each listed visual on the six criteria of the
   visual rubric. When unsure, keep the finding. Score every dimension even when a render or
   browser check cannot run: judge from the data and the build, cap only the dimension that
   check judges (no browser: practice; no render: representation) at 2 and name it. Text,
   logic and the cheatsheet are read from the data and need no app session.
   For an Exam pattern, first answer the questions in its [profile](references/profiles.md#exam).
   Every score below 3 gets a finding with its check id that names what the student meets
   and where (block title, visual key such as `block:3`, question or step key, unit or
   exercise), precisely enough to fix. Score each problem once, under the dimension the
   rubric's owner table names.
7. **Save.** Write one review per item and one course review to `.tum-mcp/review.json`
   with the revisions from the report, today's date, every dimension, every pass, the
   findings with their quotes, a score for every listed visual and each report prompt you
   keep with its reason under `prompts` (`tum-mcp study schema review`). Keep reviews of
   items you did not re-read. Save even when a pass could not run in full (no browser, no
   second session): record the pass, cap the dimensions the missing check judges at 2 and
   name what you could not check in the finding. Items you read are never left stale or unreviewed.
8. **Verify and fix.** In the authoring session, accept each finding or reject it with
   `status: rejected` and the reason the content is right; a rejected finding does not
   count. When a prose finding (clarity, cohesion, intuition) is rejected and the host allows,
   a second fresh session reads those checks again and its accepted findings count too.
   In skill-lab comparisons, use the other host for that review (Claude for Codex and vice
   versa), so the same model does not repeat its own blind spots.
   Revise each accepted finding with prepare-study, prepare-exercises or prepare-exams
   and their [review gate](../prepare-study/references/review.md); improve a visual below
   3 with the [visual loop](references/visuals.md#improve). For a reordering or a merge,
   draft the new outline beside the old one and compare both against the course checks
   before you move anything; keep unit keys so progress survives. Build, render only the edited items
   (`--unit`, `--exercise`, `--exam`) and report again. Edited items and a changed structure turn stale: re-read and re-score them,
   never copy the old score. Repeat until the report's `review.passed` and
   `render.passed` are true. A quote not found in the item (`unquoted`), a pass not run
   (`missing_passes`), an unexamined check or invalid location (`missing_checks`), a report
   prompt neither fixed nor kept (`open_prompts`), or a 3
   without its closest call or with an open invariant flag (`unevidenced`,
   `flag_conflicts`) keeps it from passing. A 1 is always fixed. A 2 may
   stay with `kept` only when the content cannot fix it (for example, the source gives no
   smaller example); say why.
9. **Report.** Give the averages, the course scores, the checks passed per dimension
   (`checks_passed`), the most failed checks (`failed_checks`), how many findings you
   rejected, what you changed, what you kept and why, and any items you could
   not read. Scores describe this review, not mastery or exam readiness.

## Boundaries

Scores, findings, contact sheets and render results stay in `.tum-mcp/`; they are never
shown to students or published. Do not raise a score without re-reading the item, and do
not lower the bar to pass. A review does not authorize new sources: fetch missing material
through read-content, and record outcome gaps in the coverage ledger instead of guessing.
Media also needs re-hearing/re-watching changed artifacts. Report separate modality
averages and incomplete perception honestly; script or ASR review cannot supply it.

For units with Explore or changed optional classifications, include the
[core-only counterfactual review](../prepare-study/references/explore.md#review-with-explore-closed).
Optional teaching is part of the unit's accuracy/visual review; it cannot supply core
prerequisites, trace requirements or assessment coverage. Classification changes stale
the course review separately from students' core progress.
