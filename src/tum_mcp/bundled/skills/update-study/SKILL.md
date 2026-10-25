---
name: update-study
description: Refresh an existing TUM course project's sources, materials and AGENTS.md without losing edits. Use for upstream changes; website-only edits use prepare-study.
---

Read AGENTS.md and the existing `.study/state.json` binding; missing state requires
init-study with a course choice. Keep the course, semester and previous bindings.
Reuse known IDs. Read-content supplies provider guidance only where needed.

Start fresh metadata checks at the listing head. Resume a saved cursor only for
an unfinished scan with the same filters; an old pagination cursor is not a marker
for new items. Compare reliable upstream revisions, fetch changed/pending material,
and content-check sources lacking a reliable revision. Include teaching units,
announcements and relevant discussions. Do not reread verified unchanged files.

Follow [snapshot and sync semantics](../init-study/references/project.md), especially
complete versus partial coverage and metadata-only reuse. Merge fresh deltas into
the existing inventory programmatically; do not rewrite/reprint the whole state.
Run `tum-mcp study sync PROJECT --snapshot FILE`. Preserve conflicts and originals;
a failed/filtered scan does not prove withdrawal. Never alter campus websites.

Update only changed course facts outside AGENTS.md's managed block. Keep personal
notes and progress. If nothing changed, report that without rewriting material.
Report changes, pending/conflicted sources, coverage and stale site units. Reuse an
existing site check or run `tum-mcp study inspect PROJECT` once when needed.

Use prepare-study only when a site update is requested. Carry the checked scope,
revisions and delta into that phase; do not rediscover or refresh them again.
If access blocks one source, record the gap and continue available sources.
