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

A request to cover a whole course or lecture range is complete only when the coverage report
shows no `not_inspected` source, `gap` or `partial` outcome, or unprepared item in that scope.
Otherwise report exactly what remains. A sync-only run records changed sources and pending
work; it does not author content.
