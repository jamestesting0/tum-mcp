# Visual pass

Score every drawn visual (diagram, UML diagram, flowchart, plot, figure, table) the way the
student sees it: from its desktop contact sheets (phone only when asked), with the render
findings and the cited source page beside it. Never score a visual from its JSON.
Formulas, derivations and code are absent from these contact sheets. Inspect their
affected passages and revealed answers in the built app; an empty sheet selection
does not establish that those blocks render correctly.
For Video Notes use [media evidence](media.md): entry/middle/exit samples plus
complete playback, with each `cXX/bXX/key` visual scored on these six criteria.
A right endpoint cannot repair an incorrect or missing intermediate construction.

## Evidence

1. `tum-mcp study visuals PROJECT` writes `.tum-mcp/visual-check.json` and the sheets
   `.tum-mcp/visuals/<item>-desktop-N.png`. Each picture carries
   its title, its key (`block:3`, `question:q1:0`, `statement:0`, `step:trace:1`) and the
   codes it was flagged with. A drawing that scrolls sideways appears twice: as the
   student first sees it and whole, captioned "whole drawing".
2. Include the solution, Compare and transfer-answer sheets. Open their controls in the app
   to check the surrounding context; an injected sheet checks the drawing, not its reveal.
3. Open every sheet of the item. Look
   at each picture for five seconds and say its message; then read its caption.
4. Open the cited source page. Fidelity can only be judged against it.

## Hard gates

The render check's defects decide a criterion before you look:

| Finding | Caps |
| --- | --- |
| `fidelity` (a drawn node, edge, arrow or label differs from the block, or the block was not drawn), `render_error` | Fidelity at 1 |
| `edge_through_node`, `coincident_edges` | Layout at 1 |
| `label_overlap`, `label_on_line`, `label_on_node`, `clipped_text`, `tiny_text` | Legibility at 1 |
| `tall_visual`, `tall_cell`, `table_scrolls` | Legibility at 2 |

The weakness is judging a changing explanation from only its endpoint.
Walkthroughs are photographed at their first and last steps. Inspect intermediate
states when the reasoning depends on them; endpoint captures alone cannot establish it.
A graph stage that still
scrolls at desktop appears under `notes` in the visuals summary. `scrolls` is a note,
not a defect: judge it under Legibility.

## Rubric

Six criteria, 1 to 3 each. A visual scores its weakest criterion, and the item's
Representation score never exceeds its weakest visual.

| Criterion | 3 means | 2 | 1 |
| --- | --- | --- | --- |
| Fidelity | Says exactly what the source says: every node, edge, direction, label and value; nothing invented or dropped; discrete things drawn discrete; real scales | A simplification the text does not mention | A wrong, invented or dropped element; a misleading scale |
| Form | The kind of block fits the idea, as in prepare-study's [representation table](../../prepare-study/references/representations.md#choose-the-representation); how it is arranged is Layout | A workable but weaker form, such as a table for a decision tree | A form that hides the idea, such as numbered steps for a network or a table of coordinates for a board |
| Layout | Reading order kept; main path straight; meaningful positions (map, timeline, ring) kept; no crossing or bend the structure does not force | One avoidable crossing, bend or detour | The structure cannot be followed |
| Legibility | Every label beside its own mark and clear of the others; readable text; the drawing fits the available column, or scrolls only because it cannot be narrower | Avoidable scrolling or crowded labels | A hard-gate finding |
| Focus | One message; a picture's caption states it, a table of cases may name what it lists; colour and frames mark only what the caption discusses | Two messages, a picture whose caption names it or explains its symbols instead of its point, or a caption whose point the picture does not show | No visible message |
| Convention | The notation's rules: UML arrowheads, multiplicities and compartments; flowchart decisions as questions with labelled exits; a probability mass function as stems; a log axis labelled with real values; axis titles with units | One rule broken without changing what the picture says | A rule broken so the picture says something else |

## Calibrate

`tum-mcp study visuals PROJECT --gallery` draws the [calibration gallery](visual-gallery.json)
with this app, each picture captioned with its key only. Use desktop captures; add phone
captures only when requested. Most verdicts come
from the course owner's own review; the rest follow a rule from prepare-study's guides, and
each entry says which. Score three pictures before opening the file, then compare your
score on the criterion each verdict names. A disagreement means you misread a criterion:
re-read its row and the gallery's reasons. Use the gallery's 1s and 3s as anchors while
scoring.

## Improve

For a visual below 3:

1. Write the finding: the criterion, what the student sees and where (key and width).
2. Choose a change that addresses the finding, using
   [diagrams](../../prepare-study/references/diagrams.md),
   [plots](../../prepare-study/references/plots.md) or [figures](../../prepare-study/references/figures.md).
   Keep the full teaching object and source meaning.
3. Build and render the changed visual. Compare it with the earlier evidence against
   the rubric. Try an alternative only when the result leaves the choice unresolved.
4. Stop when the criteria pass. Keep a remaining score-2 limitation only when it cannot
   be fixed within scope, and record the reason through the review workflow.
   Reuse passing evidence for unchanged inputs.

## Mistakes found in real courses

- A Bayesian network drawn in one row: edges bend around nodes and the network reads as
  a chain (gallery `bayes-row`).
- An action drawn as a state ("Continue") instead of a self-loop (`mdp-fake-state`).
- A class left out of a UML diagram to make it tidier (`composite-without-client`).
- A probability mass function drawn as a line; log values plotted on a linear axis
  (`pmf-line`, `growth-log-values`).
- A long method signature that makes a sequence diagram scroll on a desktop
  (`sequence-long-signature`).
- Three boxes with worded edges in one row: on a phone the row is wider than the screen
  (`mdp-row-on-phone`; the third box on the next row fits, `mdp-two-rows`).
- A caption that names the picture ("The network") instead of saying what it shows.
