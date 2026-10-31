# Separate core teaching from Explore

Explore retains useful context outside the required learning path. Classify passages,
not whole slide decks or titles. Read the course outcomes, relevant exercise/exam tasks
and downstream lessons before deciding. History, biographies and origins can be core
in a course that teaches or assesses them. Difficulty does not make a proof optional.

| Evidence or purpose | Destination |
| --- | --- |
| Stated learning outcome, assessed fact or prerequisite for a task | Content |
| Definition, notation, assumption, mechanism, necessary motivation, essential example or counterexample | Content |
| Historical detour, biography, application or further reading with no required dependency | Explore, with source evidence and a reason |
| Mixed essential explanation and digression | Split coherently; keep sufficient explanation in Content |
| Uncertain relevance or conflicting evidence | Keep core provisionally and record the uncertainty |
| Missing source | Record pending/unknown; do not fabricate optional reading |
| Logistics, deadlines or administrative instructions | Course handbook/workflow |

Source-explicit optionality is strong evidence, but required task dependencies take
precedence. Absence from past exams does not establish optionality. Never invent goals
or change an unresolved core outcome's role merely to clear a gap. Retain its stable
coverage key and record a source-based reason for any reviewed reclassification.
Optional describes this prepared learning path; do not claim exam irrelevance without
authoritative course evidence.

## Record the decision

Use the existing private coverage ledger. Core outcomes keep `role: core` (the default)
and `units`. An enrichment entry has `role: enrichment`, `classification` with
`basis: source_optional` or `reviewed_enrichment` and a specific `reason`, plus the
existing source and locator. Prepared enrichment (`covered`/`partial`) uses
`explore: [{"unit": "UNIT", "item": "ITEM"}]`, never core `units`. The item must cite
that source. Gaps/out-of-scope entries need a note and no prepared references.
Every authored Explore item needs at least one matching prepared enrichment record.
Keep unknown sources unknown and update only inspected entries.

The report separates core `outcome_gaps` and `enrichment_gaps`. `core_complete` is a
qualified core-preparation statement; unqualified `complete` also requires no tracked
optional gaps. Missing records and unavailable exercise work still prevent full
completion. Optional backlog stays in the private agent report and is not shown on the
learner overview. Pending records never create an empty Explore tab. Classification
reasons stay private.

## Author an item

`Unit.explore` is absent or an empty list when unnecessary. Otherwise each item has a
stable `key`, `title`, its own nonempty versioned `sources` and nonempty `blocks`.
Use existing block types and notation rules. Every block needs a stable key unique
within the item; heading levels start at 1 independently for each item. Limits are
20 items per unit and 40 blocks per item. Cite only the item's declared sources;
do not add optional sources to `Unit.sources` just for the renderer.

There are no Explore objectives, cards, questions, minutes or completion marks.
Core definitions supply global `{{term}}` links; an Explore-only definition cannot
supply a core term or prerequisite. Avoid duplicating the core explanation or adding
trivia to fill the tab. Explore edits preserve core progress, but stale source hashes
still block builds and optional teaching/visual reviews become stale.

## Review with Explore closed

Could the student skip every Explore passage and still understand Content and solve
the course tasks? Read Content, core cards/questions and linked Exercises/Exam
with Explore closed. Every needed term, convention, example and inference must be
available in core. Repair a dependency before approving the split. Then review Explore
for accuracy, citations, readability and visuals to the same standard as other reading.
Check the classification rationale and remaining optional backlog as a separate pass;
schema validation cannot establish educational relevance.

## Verify the student path

The tab appears only where authored items exist, after Practice. Start directly with
the reading, without an extra Optional label or introductory banner. The normal path remains Content → Flashcards → Practice → next
topic/Revision, and Start/Continue remembers the last core view. Explore returns to
Content and has no Video Notes player. Optional-only media is excluded from default
audio/video lessons. A unit/item/block link is `#UNIT/explore/ITEM/BLOCK`;
missing targets show an unavailable notice rather than another activity.

Verify source links, scoped comments, headings/Contents, keyboard tabs and narrow/wide
layouts. Do not move existing core comments to similar optional text; preserve them in
their original scope if a separately authorized rewrite moves a passage.
