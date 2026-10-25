---
name: prepare-study
description: Build or update a local TUM study website, or address its passage comments, with source-backed explanations, flashcards and practice; includes explicit synthetic demos.
---

Work in the course project bound by AGENTS.md and `.study/state.json`. For an explicit
synthetic preview only, run `tum-mcp study demo PROJECT` in a separate directory; it
needs no campus access.

## Workflow

1. **Scope.** A missing binding goes through sync-study with a course choice. Work from
   local sources. Fetch only missing material through read-content. Run sync-study
   once, and only when fresh upstream content was requested and not already checked.
2. **Plan units.** Inspect study/ and the affected source and unit IDs. Keep the theme,
   notes, edits, labels and stable IDs of unchanged units. Choose one lecture, week or
   topic organization that follows course dependencies. For a single course, use
   at most one category level followed by topics; use a flat list when sufficient.
   Do not copy the multi-area demo's deeper tree into an ordinary course. Preserve
   existing IDs/progress when flattening labels; avoid repeated week labels.
3. **Author.** Write study/content.json, not per-unit HTML. Shape each unit as a short
   lesson ([teaching](references/teaching.md)). On a new site, prove one unit with the
   hardest required formats, then author the rest in batches. Author display formulas
   in LaTeX and inline variables/short expressions with `\( ... \)` in prose, tables,
   glossary entries, cards and questions; keep code literal.
   Every multiple-choice question has exactly four options: one correct answer and
   three plausible distractors, each with specific feedback. Never fill gaps with
   invented course facts.
4. **Review.** Check every changed explanation, answer and assumption against its
   source. Schema and browser checks do not replace this review. Rebind source hashes
   only after you read the changed content.
5. **Build.** Run `tum-mcp study build PROJECT`. It installs the bundled renderer:
   course home, Content/Flashcards/Practice per unit, and Revision with a review mode
   for missed items. Reuse the pooled cards and questions; do not author duplicate
   decks, recreate the shell or add a framework. Investigate stale sources and
   preserved custom templates.
6. **Verify.** Select checks by what changed ([verification](references/verification.md)).
   Reuse evidence for unchanged inputs; expand testing when shared code or formats
   change. Keep progress separate from content. For a component preview, cover all
   existing block types and the demanding formats it needs. Use the primary reading
   font consistently; check formulas at narrow widths, category collapse and
   question-review dialogs when those shared surfaces change.
7. **Publication.** Build automatically updates a configured GitHub study site.
   Reuse its report; resume pending or failed deployment through publish-study
   before calling the hosted update complete. Do not create another repository
   or upload the course project. A local-only project stays local.
8. **Report.** Name changed and reused units, relevant gaps, checks actually run and
   `tum-mcp study` to launch from the course project folder. Unrun checks are not
   passes. Do not claim bug-free software,
   official exam coverage, mastery or certified STE compliance.

## References

Read only what the change needs.

| Need | Read |
| --- | --- |
| New or changed explanations, cards or questions | [Teaching](references/teaching.md) |
| First build, schema fields or new block types | [Content and build](references/content.md) |
| New site, visual or renderer change | [Design](references/design.md), then the affected rows of [components](references/components.md) |
| Feedback left on the study site | [Passage comments](references/comments.md) |
| Choosing checks | [Verification](references/verification.md); [regressions](references/regressions.md) for changed shared behavior or a failure |

## Boundaries

Keep the site credential-free. First publication needs the user's request and
publish-study; saved publication settings authorize later build updates. When
category audio is also requested, finish the affected course content first, then
continue with audio-notes and pass the current content, changed unit IDs and source
review gaps. Audio outputs belong under audio/. A website-only request never triggers
narration or external speech generation.
