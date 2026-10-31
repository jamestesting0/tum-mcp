# Review gate and representations

Shared by prepare-study, prepare-exercises and prepare-exams. A build checks the schema;
`tum-mcp study report PROJECT` (and `study exam-report` for Exam) derives review flags
and the coverage of the course sources. Revise each flagged item or keep it with a reason
in your report. Neither a pass nor an empty flag list proves the teaching is good, so finish
with this gate.

## Review gate

1. Read each item as the student sees it: prompt, blocks and check together. A table or
   diagram that invites an answer belongs to the step whose Compare answers it.
2. Recompute every number with code, including feedback, explanations and related items.
3. State the conventions an answer depends on (tie-breaks, child order, goal test, indexing)
   before the task, or accept and explain each valid alternative.
4. Every wrong option's feedback names the mistake that leads to it.
5. Show each idea in the shape it has (table below); prose says only what the picture cannot,
   and never describes an object the student could simply see. Teach each idea in full in
   one unit; elsewhere mark it `{{term}}` or link its block, add a one-line reminder where a
   first-time reader would otherwise have to go back, and revisit it to take it further or
   to practise it in a new situation. Give a worked case once, as steps, a derivation or a
   table, not twice. Insert a section where it belongs in the
   lesson shape; a section appended on a later pass leaves the lesson out of order
   (`study report` flags it as `source_order`).
6. Review the last batch to the same depth as the first, against the source's own outcomes.
7. Resolve or justify every flag from `study report`. Restructure, never justify,
   `long_section`, `dense_paragraph`, `prose_calculation`, `plain_math`,
   `meta_reference`, `restated_context`, `dense_statement`, `forward_term`,
   `compressed_working` and `described_object`: each means a wall of text, mathematics typed
   as characters, a sentence about the material, a fact said twice, a term used before it
   is taught, results without their working or an object described instead of shown.
   Read `dense_introduction`, `unexplained_identity`, `example_without_rule` and
   `tall_inline_math` in place and fix them unless the passage already orients the reader
   and unpacks its notation ([teaching](teaching.md#notation-at-the-point-of-use)), the
   topic has no reusable rule or the object reads well inline. Write as in [writing](writing.md).
8. Walk each new or changed lesson and its exercise once as a first-time reader, as in
   review-course's [text pass](../../review-course/references/text.md): what the reader
   knows so far, which new terms and symbols each section adds, where a step is missing
   and where a reminder would spare a return trip.
9. After the build, run `tum-mcp study visuals PROJECT` and fix every defect it reports in
   the content (an edge through a node, clashing labels, text under 12 px, a drawing that
   differs from its block). Open the contact sheets in `.tum-mcp/visuals/` and look at each
   visual at phone and desktop width.
10. Score the batch with [review-course](../../review-course/SKILL.md); its scorecard turns
   stale when an item changes, and its course review when units, groups or links change,
   so the review follows the content.

## Choose the representation

| The idea is | Show it as |
| --- | --- |
| A term students must learn | A `definition` block; mark later mentions `{{term}}` |
| An algorithm or process over time | A diagram whose frames carry `state` rows (queue, domains, values) and a reason in each caption, or a trace table with one row per step |
| Parallel cases (games, environments, designs) | A table with one row per case, or a list |
| A rule or value that depends on two inputs | A decision matrix: one input down the side, the other across the top, the result in each cell |
| Something with a physical or spatial shape (an arm and its angles, rooms, a map, a mechanism) | A `figure` drawn as in [figures](figures.md), or an image |
| A hard argument or a multi-part explanation | Numbered `steps`, one claim each |
| A calculation or definition with symbols | A formula block with every symbol explained |
| A calculation the student should redo, or a derivation | A `derivation`: one transformation per line with its reason, a labelled group per requested result |
| A transformation of a state over several steps (a gate on a qubit, a row reduction, a Bayes update) | A `derivation` with `walkthrough`, each line's `visual` drawing the state it reaches |
| A worked case of a reusable rule | The worked case, then the rule as a formula block with conditions and when to use it, then a second case |
| A matrix, vector or state named in the text | The object itself in LaTeX (inline up to 2x2, else a formula block), never a description of its entries |
| Classes, relations, interactions, behaviour over events | A UML class, sequence or state diagram, written as in [diagrams](diagrams.md) |
| An algorithm whose branches or loops are the point | A flowchart (`uml`, `diagram: flowchart`); a straight procedure stays numbered steps |
| A network, map, chain over time or concept map | A `diagram` arranged on a lattice as in [diagrams](diagrams.md) |
| A hierarchy (files, objects, recursion) | A tree |
| Code to read, trace, fix or write | Code, with a walkthrough when it is read part by part |
| A relation between quantities, a distribution, growth or decay | A plot with the marks of [plots](plots.md) |

## Algorithm traces

Use one small instance. Each frame does one operation and its caption says why it is
allowed or chosen. `state` rows show the data the student would otherwise track mentally;
the app marks what changed since the previous frame. Include a real failure and its undo
when the procedure backtracks. Let the student predict the next state in an Exercises step
(a table or graph check), not in the lesson.

## Help before the answer

A hint ladder goes from a pointer to the relevant idea, to the first operation worked, to
Compare. Split a step whose answer has many parts, or add the middle hint. A Study question
may carry one `hint` that recalls the idea without naming the option.

## Referenced material

When a statement relies on a slide, figure or earlier result, check that the cited edition
matches, then redraw what the student needs beside the statement and cite it with `pages`.
If the source is missing or another edition, record the gap instead of guessing.

## Explore classification pass

For changed optional material or classification, apply the counterfactual in
[Explore](explore.md#review-with-explore-closed): attempt the core path and its linked
tasks with Explore closed. Check the source/locator and private classification reason,
then review optional accuracy and visuals. Keep optional gaps separate from core gaps;
never use reclassification to make an unresolved core outcome appear prepared.
