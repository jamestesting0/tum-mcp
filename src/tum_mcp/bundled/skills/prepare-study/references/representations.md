# Representations

Shared by prepare-study, prepare-exercises, prepare-exams and review-course. Pick the
shape each idea has; prose says only what the picture cannot.

## Choose the representation

| The idea is | Show it as |
| --- | --- |
| A term students must learn | A `definition` block; mark later mentions `{{term}}` |
| A reusable procedure or algorithm | Labelled steps with explicit repeat ranges, source-style pseudocode or a flowchart; preserve all branches and exits |
| A concrete run of an algorithm or process | A `walkthrough` over the graph, table, code, working, plot or figure it changes: each step an action with its `why`, the `state` rows the student would otherwise track; its "All steps" view is the trace table |
| Parallel cases (games, environments, designs) | A table with one row per case, or a list |
| A rule or value that depends on two inputs | A decision matrix: one input down the side, the other across the top, the result in each cell |
| Something with a physical or spatial shape (an arm and its angles, rooms, a map, a mechanism) | A `figure` drawn as in [figures](figures.md), or an image |
| A hard argument or a multi-part explanation | Numbered `steps`, one claim each |
| A calculation or definition with symbols | A formula block with every symbol explained |
| A calculation the student should redo, or a derivation | A `derivation`: one transformation per line with its reason, a labelled group per requested result |
| A transformation of a state over several steps (a gate on a qubit, a row reduction, a Bayes update) | A `walkthrough` with a formula stage (one line of working per step, the reason as its `why`), or a `derivation` with `walkthrough` when each line draws its own picture |
| Two methods or inputs on the same problem | A `walkthrough` with a `variant`: both runs on one stage, and the `contrast` where they part |
| A worked case of a reusable rule | The worked case, then the rule as a formula block with conditions and when to use it; another case only if it tests a new decision, condition or misconception |
| A matrix, vector or state named in the text | The object itself in LaTeX (inline up to 2x2, else a formula block), never a description of its entries |
| Classes, relations, interactions, behaviour over events | A UML class, sequence or state diagram, written as in [diagrams](diagrams.md) |
| An algorithm whose branches or loops are the point | A flowchart (`uml`, `diagram: flowchart`); a straight procedure stays numbered steps |
| A network, map, chain over time or concept map | A `diagram` arranged on a lattice as in [diagrams](diagrams.md) |
| A hierarchy (files, objects, recursion) | A tree |
| Code to read, trace, fix or write | Code, with a walkthrough when it is read part by part |
| A relation between quantities, a distribution, growth or decay | A plot with the marks of [plots](plots.md) |

Before keeping an example meant to expose a particular mistake, try that wrong
move. If it gives the same result, change the givens or narrow what the example
claims to teach. This improves the existing example without adding another one.

When extending a code example, trace the changed behavior from its public entry
through delegation to the handler and resulting state. A new event may need a
context method as well as interface and state methods; naming the new class alone
does not show how a caller reaches it.

## Algorithm traces

Give the reusable procedure separately from its worked trace. Use source-style
pseudocode, a flowchart or explicit numbered control flow when repetition or branches
matter. A trace of one successful input cannot supply a missing loop or failure exit.
Before declaring the draft ready, follow the published procedure on one ordinary
input and the relevant boundary case (an empty/exhausted search, initial success,
zero pivot or invalid precondition). Every transition must be licensed by an explicit
instruction. Use the procedure shown to the student when checking executable examples;
an independent hidden implementation does not check missing published instructions.
This is a small author dry run of the existing example, not another formal review.

A staged walkthrough shows the state of its picture, not only a new caption. On
graphs, set each step's `active`, `frontier`, `visited` and relevant `edges` from the
actual run; use the stage's node keys. Code marks its running `lines`, tables their
`shown` rows or changed `cells`, derivations their `shown` lines, plots their `series`
and SVG figures their `layers`. Clear marks that no longer apply when stepping back
or switching runs. Derive graph marks and displayed state from the same computed
trace, and include visual values in the answer key when computed. Do not invent a
changing highlight just to clear `static_walkthrough`. An intentionally fixed
picture belongs beside ordinary explanation, outside a staged walkthrough.

Use one small instance in a `walkthrough`. Each step does one operation: its `action` says
what, its `why` says why it is allowed or chosen, and `note` names the mistake a student
makes at that moment when there is a typical one. Group the steps by `subgoal` (start,
loop, stop). `state` rows show the data the student would otherwise track mentally; the app
marks what changed since the previous step. Include a real failure and its undo when the
procedure backtracks. A finished table of results without the steps is flagged
`static_trace`; a computed result without its working, `unworked_result`. Write an answer
key (`.tum-mcp/checks/<item>.py`) that runs the procedure and prints each step's state, so
`study verify` proves the trace. The student predicts the next state in an Exercises step
(a table or graph check), never in the lesson.

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
