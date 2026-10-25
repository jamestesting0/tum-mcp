---
name: prepare-study
description: Build or update a local TUM study website from one course project, with explanations, flashcards and practice; includes explicit synthetic demos.
---

For an explicit synthetic preview, use `tum-mcp study demo PROJECT` in a separate
directory; no campus access is needed. Otherwise require AGENTS.md and
`.study/state.json`; initialize a missing binding through init-study with a course
choice. Work from local sources. Fetch only missing material through read-content;
run update-study once if fresh upstream content was requested and not already checked.

Inspect the existing study/ and affected source/unit IDs. Preserve its theme, notes
and edits; reuse unchanged units and stable IDs. Choose one lecture/week/topic
organization that fits course dependencies. Group related units with optional path
folders; avoid repeated week labels and needless nesting. Author formulas in LaTeX.
Never fill gaps with invented course facts.

Read only the contracts needed:
- [Teaching](references/teaching.md): new or changed explanations/assessments.
- [Content/build](references/content.md): first build, schema questions or new block types.
- [Design](references/design.md): new site or visual changes; reuse its tokens/renderer.
- [Verification](references/verification.md): select checks for this change.
  [Regression lookup](references/regressions.md) applies to changed shared behavior or failures.

Author study/content.json, not separate per-unit HTML. Build installs the bundled
renderer; do not read/recreate all its assets or add a framework. On a new site,
prove one unit with the hardest required formats before authoring the rest in batches.
Review each changed answer and its assumptions; semantic checks are not replaced by
schema or browser tests. Rebind source hashes only after reviewing their content.

Run `tum-mcp study build PROJECT`; investigate stale sources and preserved templates.
Verify the served app using the selected checks. Reuse evidence for unchanged inputs;
expand testing when shared code or formats change. Keep progress separate from content.

Keep the site local and credential-free; publication needs the user's request.
Report changed/reused units, relevant gaps, checks actually run and the preview.
Unrun checks are not passes; do not claim bug-free software, official exams, mastery
or certified STE compliance.
