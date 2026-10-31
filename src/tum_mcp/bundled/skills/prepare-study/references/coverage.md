# Coverage ledger

`.tum-mcp/coverage.json` records, per course source, what it asks students to learn or do
and what is prepared for it. `tum-mcp study schema coverage` prints the contract; the build
checks every reference; `tum-mcp study report PROJECT --section coverage` lists what is
missing. Edit it programmatically by source key and keep entries you did not review.

## Before authoring

For each lecture in scope, record its stated learning outcomes verbatim with a locator
(the outcomes slide, or its section headings when none are stated). Plan units from these
outcomes, not from outcomes you invent for a unit. For each exercise sheet or exam, record
every problem as an item: `prepared` with its exercise key, `pending`, `not_inspected`,
`unavailable` or `out_of_scope`.

## Course state

`status` records what the evidence says: availability (released, announced, provisional,
unavailable, unknown), whether it was taught (yes, no, unknown), the source's semester,
the evidence and the date checked. A file on Moodle is not proof that it was taught, and a
calendar date is not proof of coverage; leave `unknown` until a schedule, announcement or
the user says otherwise. Never infer a student's own progress.

## While authoring

Mark each outcome `covered` (with the units that teach and practise it), `partial`, `gap` or
`out_of_scope` (with a reason). When an exercise or exam question needs knowledge Study does
not teach well enough, either improve that Study block in the same run (when Study is in
scope) and link it as the prerequisite's `block`, or record the gap with its note.

## Completion

The report's `study_preparation.pending` and the generated Study overview derive the
same known core gaps from the ledger. The private report also has `unrecorded` for
current content sources without an outcome record. Missing records
do not prove that a source is unprepared: inspect the source and existing units before
recording outcomes. Never create placeholder lessons just to make the queue disappear.
Exercise/exam items and withdrawn sources do not enter this Study queue.

After each reviewed batch, update only the affected source outcomes and their stable
unit references, retain remaining gaps with their reasons, run the coverage report and
rebuild. Verify that newly covered outcomes leave the queue while unrelated pending
and unknown work remains. Report scoped remaining work explicitly; do not silently
mark it out of scope to claim completion. The queue describes authored preparation,
not what the student has read or mastered.

A request to cover a whole course or lecture range is complete only when the coverage report
shows no `not_inspected` source, `gap` or `partial` outcome, or unprepared item in that scope.
Otherwise report exactly what remains. A sync-only run records changed sources and pending
work; it does not author content.

## Optional preparation

Follow [Explore](explore.md) for passage classification and enrichment references.
`pending` and `outcome_gaps` stay core-only; `enrichmentPending` and `enrichment_gaps`
track reviewed optional work separately. `core_complete` does not mean all sources
are prepared; unqualified `complete` remains conservative. No ledger record means
unknown, never evidence that a lecture is optional. Retain stable outcome keys and
review the source-based reason before changing a core entry's role.

Unknown coverage and optional backlog remain authoring state. The learner app and
static export include only the core `pending` list, without panels for `unrecorded`
or `enrichmentPending`. Removing those panels does not resolve any gaps or make
unknown sources complete; use the local report when deciding what remains to prepare.
