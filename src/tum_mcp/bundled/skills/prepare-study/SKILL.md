---
name: prepare-study
description: Build or update a local TUM study website, or address its passage comments, with source-backed explanations, flashcards and practice; includes explicit synthetic demos.
---

When `tum-mcp study status PROJECT` reports `course_memory: true`, use
the installed `course-memory` skill for relationships and scoped source updates.
When disabled, leave retained graph files unused and follow the ordinary workflow.


For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. The handbook's receipt describes local review, not live
freshness; verify affected facts against sources. Reuse context already read in this
request. Do not re-read the whole inventory for each authoring step. Look at every slide
or sheet page you rely on: `tum-mcp study text` finds and quotes it but drops figures and
scrambles tables and formulas. Open the PDF page if your tools display PDFs; otherwise
add `--images` and open the image.

Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. You author
`app/study/course.json` and one file per unit, `app/study/units/<key>.json`; edit them with
your edit tools. `tum-mcp study build`
installs the shared course app, which owns layout, styling and interaction; read
[the course app](references/app.md) to see how your content appears. For an explicitly
requested synthetic preview, run `tum-mcp study demo PROJECT` in a separate directory.
Weekly sheets and guided solutions use prepare-exercises in the same app; exam
preparation (cheatsheet, exam patterns, practice exams) uses prepare-exams.

**Maths.** Everything a student reads that is mathematics is LaTeX in `\( ... \)`, one
span per expression (JSON doubles each backslash). `study lint` reports `plain_math` and
`math_word`, and readiness waits until both are gone:

| Write | Not |
| --- | --- |
| `\(X = \{1, 2\}\)`, `\(Z = \emptyset\)` | X={1,2}, Z=∅ |
| `\(P(a)\)`, `\(\neg P \lor Q\)`, `\(P \leftrightarrow Q\)` | P(a), ¬P ∨ Q, P↔Q |
| `\(0.6 \cdot 200 + 0.4 \cdot (-300) = 0\)`, one span | 0.6·200 + …, or `\(0.6\)`·200 |
| `\(P(A = \mathrm{true} \mid \mathrm{warning})\)` | `\(P(A=true \mid warning)\)` |
| `\(\frac{0.4}{0.4 + 0.1} = 0.8\)` in a worked step | 0.4/(0.4+0.1) = 0.8 |

## Workflow

1. **Scope.** A missing binding goes through sync-course with the requested course
   and semester. Work from local sources and fetch only missing material through read-content. Run
   sync-course once, and only when fresh upstream content was requested.
2. **Plan units.** Inspect the app folder and the affected source and unit IDs. Keep
   notes, edits, labels and stable IDs of unchanged units. Record each source's stated
   outcomes in the [coverage ledger](references/coverage.md) first, then plan units that
   teach them. Classify supporting passages with [Explore](references/explore.md);
   keep essential understanding and task dependencies in Content. Read
   `study report PROJECT --section coverage`: its `study_preparation` separates core
   gaps, optional backlog and sources without recorded outcomes. Keep this ledger current as each batch is reviewed; never
   infer preparation from a unit count or the student's browser progress.
   Choose one lecture, week or topic organization that follows course
   dependencies, with one category level (a second only for a large group); use a flat
   list when sufficient. Each unit uses only what earlier units teach. Study teaches a
   student who meets the topic for the first time: write or update the course's
   teaching profile, then a teaching plan for each new or restructured unit, and check
   it before writing ([planning](references/planning.md)): each unit's structured plan in
   `.tum-mcp/plans/study/<key>.json` is ready with every other requested unit's plan
   before one batch plan check. Repair pending plans together and submit them in one
   check, rather than checking each lesson as you finish it. Each passes before authoring
   ([draft checks](references/loop.md)).
3. **Author.** Read [teaching](references/teaching.md) and
   [writing](references/writing.md) before writing a new or restructured unit. Teach each
   unit as its plan decided, with the moves that fit each idea and the block types the
   schema offers ([content](references/content.md)). Use `tum-mcp study schema --example list`
   to list block examples and `tum-mcp study schema --example KIND` to print one.
   Draft the heading outline first: major topics,
   their cases/examples, and any necessary detail. Set levels by those relationships
   rather than making every passage a level-1 section. Place an unframed opening under
   its topic heading; a self-contained opening needs no extra framing just to clear a flag.
   On a new site, prove one unit
   with the hardest required formats and `study visuals PROJECT --unit UNIT`, then author
   the rest in batches. Record changed
   decisions in the plan. Before writing options, solve each [practice question](references/practice.md)
   and check that the shortest valid solution exercises every action in its objective.
   Use familiar words for incidental jargon or give it an [in-place gloss](references/writing.md#explain-difficult-words-in-place).
   Never fill gaps with invented course facts. Write an answer key for every trace or
   computed result first, and run
   `tum-mcp study lint PROJECT --item study/<key>` after each unit.
4. **Check, then ask.** Finish Phase A of the [draft checks](references/loop.md) for each
   batch: build, `tum-mcp study visuals PROJECT` and `--interact`. Review the core path with
   Explore closed before approving a split, the last batch as carefully as the first. Then
   ask before the review loop (Phase B, run by [review-course](../review-course/SKILL.md)),
   unless the request already asks for review. If another batch or workspace remains in
   scope, continue drafting it first. Code checks do not replace the loop's fresh
   checkers, and the session that wrote a unit never scores it. Rebind source hashes only
   after you read the changed content.
5. **Build.** Use the Phase A build. Do not author duplicate decks,
   hand-copy the app, add a framework or edit generated `data.mjs`. Investigate stale
   sources and preserved custom templates.
6. **Verify.** Select checks by what changed ([verification](references/verification.md))
   and reuse evidence for unchanged inputs.
7. **Publication.** Build updates a configured GitHub study site automatically. Reuse
   its report; resume pending or failed deployment through publish-course before
   calling the hosted update complete. A local-only project stays local.
8. **Report.** Name changed and reused units, relevant gaps, checks actually run and
   `tum-mcp study` to launch from the course project folder. A whole-course request is
   finished only when the coverage report shows nothing uncovered in scope; otherwise
   list what remains. Unrun checks are not passes. Do not claim bug-free software,
   official exam coverage or mastery.

## References

Read only what the change needs.

| Need | Read |
| --- | --- |
| Teaching profile, unit plans and the plan check | [Planning](references/planning.md) |
| New or changed explanations, cards or questions | [Teaching](references/teaching.md) |
| New or changed practice demands, options or feedback | [Practice](references/practice.md) |
| Fields, notation, block types or validation failures | [Content and build](references/content.md) |
| How content appears, or a course that needs an app change | [The course app](references/app.md) |
| Feedback left on the study site | [Passage comments](references/comments.md) |
| Choosing checks | [Verification](references/verification.md) |
| Plans, the plan gate, answer keys, lint and the review loop | [Draft checks](references/loop.md) |
| Choosing a representation, tracing an algorithm step by step | [Representations](references/representations.md) |
| Wording of any explanation, card, question or feedback | [Writing](references/writing.md) |
| Which variables in a derivation get a clickable meaning | [Variable meanings](references/variables.md) |
| Drawing a graph, UML diagram or flowchart | [Diagrams](references/diagrams.md) |
| Drawing a plot | [Plots](references/plots.md) |
| Drawing a figure | [Figures](references/figures.md) |
| Supporting material, optionality and classification review | [Explore](references/explore.md) |
| Source outcomes, course state and completion | [Coverage ledger](references/coverage.md) |

## Boundaries

Keep the site credential-free. First publication needs the user's request and
publish-course; saved publication settings authorize later build updates. When
category audio is also requested, finish the affected course content first, then
use the optional audio-notes workflow (`tum-mcp install audio-notes` if missing)
and pass the current content, changed unit IDs and source review gaps. Audio
outputs belong under audio/. A website-only request never triggers narration or
external speech generation. Explainer videos work the same way through the optional
video-notes workflow (`tum-mcp install video-notes`): finish content first, pass the
changed unit IDs, and keep videos under videos/.

For concise lecture notes and highlights of substantial explanations worth watching, use
the optional prepare-lecture workflow when installed. Preserve existing
Lecture while updating Study; do not duplicate or automatically author it.
