---
name: update-study
description: Refresh an existing single-course study project against connected Moodle, Artemis and Zulip sources. Use to find new or changed course information and update local materials and course knowledge without losing edits.
---

Inspect the current directory, AGENTS.md and `.study/state.json`. Require an
initialized course binding. Do not replace it with a new course or infer a new
semester from a similar title. Reuse source IDs, revisions and retrieval cursors.

Compare fresh metadata for the bound sources through read-content. Include
lecture units, slide revisions, announcements and discussion changes, not just new PDFs. Fetch changed/new
material. A source without a reliable revision needs a content check; the old
checked-at timestamp alone cannot prove it unchanged. Follow bounded batches.
Keep failed or incomplete source coverage explicit. Never treat an auth error,
partial page or outage as evidence that old resources were withdrawn.

Read [snapshot and reconciliation rules](../init-study/references/project.md). Run
`tum-mcp study sync PROJECT --snapshot FILE` after preparing the new snapshot.
The helper retains extra files and local edits, reports source/local conflicts,
and marks upstream withdrawals only after complete coverage. It does not delete
originals. Investigate conflicts before choosing which version should replace one.

Refresh course-specific AGENTS.md knowledge outside the managed block only where
verified facts changed. Preserve user goals, notes and learning progress. Record
which facts changed and their sources. Avoid reading every unchanged resource.

If study/ exists, report which units depend on changed sources. Use prepare-study
when the request includes updating the site. Do not silently leave old explanations
labelled current, or overwrite an edited renderer. Report source changes, retained
edits, incomplete checks and the next action. Campus websites remain read-only.
