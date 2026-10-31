# Course pass

Review the course as a whole once its items are reviewed: the order of the units, the
groups in the outline, what repeats across units and workspaces, and how Study,
Exercises, Exam and Lecture send the student to each other. This pass scores
course Organization, course Redundancy and, when the report lists it, Integration.

## Evidence

1. `tum-mcp study report PROJECT --section structure` prints the course map:
   - every unit in course order with its group (`path`), its sections, the terms it
     defines, the units it `builds_on` (the homes of the terms it marks), its linked
     Lecture entries, the exercises that require it and the Exam concepts that cite it;
   - every exercise with the unit and block it requires;
   - Exam topics in order, and each lecture with whether a unit links it;
   - `flags` for forward terms, odd groups, order clashes, repeated passages and
     practice, and missing links.

   `builds_on` is only as complete as the `{{term}}` marks: a dependency you find by
   reading still counts, and an unlinked one is an `organization.links_back` finding.
2. `--section review` lists `course.status`, the structure `revision` to save and the
   `dimensions` to score. The review turns stale when units, groups, titles, defined
   terms or links change, not when a passage is reworded; the flags are recomputed on
   every report. When enabled Course Memory supplies `knowledge_revision`, review
   those relationships and save that field alongside the native `revision`. Changes
   stale the optional binding; disabling memory leaves native review unaffected.
3. Read the item reviews you just saved: their Organization and Redundancy findings
   often repeat across units and point at a course-level cause.

## Procedure

1. **Outline.** Read the unit titles and groups alone. Say what the course teaches and in
   what order. Check each group against the course's `organization`; a lone unit beside
   larger topic groups, a catch-all, a folder around the whole course or a second level
   for a small group is a finding.
2. **First-time reader.** Walk Study in course order as a student who knows only what the
   earlier units taught. At every unit, look up its `builds_on` and the results, methods
   and symbols it uses; anything a later unit teaches is a finding. Check that the
   introduction and the first unit tell the student where the course goes.
3. **One home per idea.** For every `near_duplicate_passage` flag, and for each idea the
   item reviews found repeated, decide which unit is its home; every other place should
   link to it (`{{term}}` or a prerequisite block) or practise it in a new form. A
   cheatsheet line or concept detail that copies Study instead of compressing it is a
   finding. Spaced practice, interleaving and a later unit that takes the idea further
   are not.
4. **Returning student.** Enter from three exercise steps and two Exam patterns spread
   over the course (those that exist), as a student who forgot the lesson. From each,
   reach the passage that teaches what it needs and come back: through the prerequisite
   block, the concept's units or a marked term. A missing link, a link to a passage that does not
   teach what the step uses, or a different symbol or convention is a finding.
5. **Climb.** For two outcomes, compare their Study question, exercise step and exam
   pattern. Each should ask for more transfer than the last; the same question in two
   workspaces is a finding.
6. **Backbone.** Exercise sets and Exam topics should follow the order of the units
   they need; check every `order_mismatch` flag and say whether the course has a reason.

## Save

Write the course review under `course` in `.tum-mcp/review.json` with the structure
`revision` from the report, today's date and a score for every listed dimension
(`tum-mcp study schema review`). Every finding names its check and the units, exercises,
concepts or lectures where it shows: "`integration.prerequisite_links`:
exercises/sheet-3/heaps needs the sift-down step, but its prerequisite links
study/priority-queues without a block; link `#sift-down`."

## Optional boundary

Read [Explore classification](../../prepare-study/references/explore.md) and the local
ledger rationale/locator. Read Content, cards/questions and linked tasks with Explore
closed; flag any required dependency missing from core. Check optional backlog without
merging it into core gaps. Explore structure and classification changes stale the
course review even when saved core progress remains valid.
