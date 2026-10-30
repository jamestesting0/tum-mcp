---
name: prepare-study
description: Build or update a local TUM study website, or address its passage comments, with source-backed explanations, flashcards and practice; includes explicit synthetic demos.
---

For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. Legacy `.study/` remains readable until explicit
`study upgrade PROJECT`. The handbook's receipt describes local review, not live
freshness; verify affected facts against sources. Reuse context already read in this
request. Do not re-read the whole inventory for each authoring step.

Work in the course project bound by AGENTS.md and `.tum-mcp/state.json`. You author
`app/content.json` (`study/content.json` in a legacy project). `tum-mcp study build`
installs the shared course app, which owns layout, styling and interaction; read
[the course app](references/app.md) to see how your content appears. For an explicitly
requested synthetic preview, run `tum-mcp study demo PROJECT` in a separate directory.
Weekly sheets and guided solutions use prepare-exercises in the same app; exam
preparation (cheatsheet, exam patterns, practice exams) uses prepare-exams.

## Workflow

1. **Scope.** A missing binding goes through sync-course with a course choice. Work
   from local sources and fetch only missing material through read-content. Run
   sync-course once, and only when fresh upstream content was requested.
2. **Plan units.** Inspect the app folder and the affected source and unit IDs. Keep
   notes, edits, labels and stable IDs of unchanged units. Record each source's stated
   outcomes in the [coverage ledger](references/coverage.md) first, then plan units that
   teach them. Choose one lecture, week or topic organization that follows course
   dependencies, with at most one category level; use a flat list when sufficient.
3. **Author.** Shape each unit as a short lesson ([teaching](references/teaching.md))
   using the block types the schema offers ([content](references/content.md)). On a
   new site, prove one unit with the hardest required formats, then author the rest
   in batches. Never fill gaps with invented course facts.
4. **Review.** Check every changed explanation, answer and assumption against its
   source, run `tum-mcp study report PROJECT` and `tum-mcp study visuals PROJECT`, and pass
   the [review gate](references/review.md) for each batch, the last as carefully as the
   first. Then score the changed units with [review-course](../review-course/SKILL.md) and
   fix what it finds until the report's review and render sections pass. Schema and browser checks do not replace this review. Rebind source hashes only after you read the changed content.
5. **Build.** Run `tum-mcp study build PROJECT`. Do not author duplicate decks,
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
| New or changed explanations, cards or questions | [Teaching](references/teaching.md) |
| New or changed practice demands, options or feedback | [Practice](references/practice.md) |
| Fields, notation, block types or validation failures | [Content and build](references/content.md) |
| How content appears, or a course that needs an app change | [The course app](references/app.md) |
| Feedback left on the study site | [Passage comments](references/comments.md) |
| Choosing checks | [Verification](references/verification.md) |
| Reviewing a batch, choosing a representation, tracing an algorithm | [Review gate](references/review.md) |
| Wording of any explanation, card, question or feedback | [Writing](references/writing.md) |
| Drawing a graph, UML diagram or flowchart | [Diagrams](references/diagrams.md) |
| Drawing a plot | [Plots](references/plots.md) |
| Drawing a figure | [Figures](references/figures.md) |
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

For timestamped notes about the professor's additional explanations beyond slides,
use the optional prepare-lecture workflow when installed. Preserve existing
Lecture Notes while updating Study; do not duplicate or automatically author it.
