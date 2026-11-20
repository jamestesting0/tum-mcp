# Review changed work at the right layer

Independently solve every changed task/check; verify hints, feedback, rubric and
solution against reviewed sources, including units, assumptions and alternative
valid approaches. Check original statement/subparts for missing information. A
schema pass does not verify subject matter. Use the component template only for
rendering coverage; its snippets are not a teaching-quality example.

Read each question's first sentence: a student must know what to produce from it.
Read every answer, hint, explanation and rubric next to only what the student has
seen at that step; anything it names must already be shown or introduced by the
prompt. For tables, independently verify every target cell. For graphs, verify
direction; when several paths or sets are correct, say so in the explanation.
For line graphs, verify scales/units and independently compute every target point;
try tap placement, coordinate editing, keyboard adjustment, clear and reload. A
matched finite point set does not prove the entire curve or a derivation is correct.
For code and long work, inspect indentation, notation, the project's files and rubric;
check that the files declare what the solved lines use, that the solved files change
only what the tasks ask for, and compare one alternative valid response and a flawed one
against the rubric. A project from Artemis passes `study lint` without `project_drift`.

Build the actual app. Exercise one representative changed response branch only
when it changes: work on paper → compare → continue (a choice: wrong → repair → change → check), and
the direct solution. A hint should help beyond the bare
statement while an independent learner incurs no compulsory step. Check new long
notation, tables and diagrams at desktop width. Drafts, navigation, storage and
comments are app behavior covered by the package's tests; report a suspected app
defect instead of changing installed files (see
[the course app](../../prepare-study/references/app.md)).

## Check the indexed answer

Suppose Sheet 1, Exercise 2, gives an edge of weight 3 from a node at distance 4
to a node already at distance 9. Part (a) asks for the candidate distance. Part
(b) asks whether to update and why. Under `app/exercises/`, index the item as
`exercises/sheet-1/relax-edge`. Retain both source questions in the statement.
Point `part_blocks` at their separate headings. Give each part its own guide
steps and labelled solution answer. The first guide shows the sum and states
the result. The second compares it with the old distance before deciding.

Point the sheet's parent coverage entry at `relax-edge` once. Use the indexed
item key in the item plan and the preparation demands. Map each demand to its
own part and guide. If part (a)'s first guide uses a numeric check, put
`steps[0].check.answer` in that demand's `values`. If part (b) asks only for a
justification, review the reasoning and leave its computed targets empty.
Register computed work in `.tum-mcp/checks/exercises/sheet-1/relax-edge.py`:

```python
import json

source_distance = 4
edge_weight = 3
candidate_distance = source_distance + edge_weight
print(json.dumps({"values": {"steps[0].check.answer": candidate_distance}}))
```

Run `tum-mcp study verify . --item exercises/sheet-1/relax-edge --json`.
Confirm that the requested target appears in `matched_values`. Compare
intermediate values as well when they determine a later step. A missing key
or `no_checks` result provides no evidence for a computed demand.

For a targeted authoring update, compare before/after IDs and unrelated objects;
Study and template assets should not change. Reuse passing evidence while inputs
remain unchanged. Report actual checks and gaps; do not claim retention, mastery,
official correctness or zero possible bugs from a browser walkthrough.
