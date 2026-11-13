# Representations

Shared by prepare-study, prepare-exercises, prepare-exams and review-course. Pick the
shape each idea has; prose says only what the picture cannot.

## Choose the representation

| The idea is | Show it as |
| --- | --- |
| A term students must learn | A `definition` block; mark later mentions `{{term}}` |
| A reusable procedure or algorithm | Labelled steps with explicit repeat ranges, source-style pseudocode or a flowchart; preserve all branches and exits |
| A concrete run of an algorithm or process | A `walkthrough` over the graph, grid, table, code, working, plot or figure it changes: each step an action with its `why`, the `state` rows the student would otherwise track; its "All steps" view is the trace table |
| Parallel cases (games, environments, designs) | A table with one row per case, or a list; when each case needs its own working, one `example` per case |
| One worked case read whole (a classification, a calculation, applying a definition) | An `example`: what is `given`, the `steps` and the `result`; a state that changes step by step is a `walkthrough` instead |
| The wrong move students make at one moment | A `callout` with `tone: pitfall`: the situation, the wrong and the right move, why |
| A condition or limit of the rule just stated | A `callout` with `tone: note`, one or two sentences that add something the text does not say |
| A rule or value that depends on two inputs | A decision matrix: one input down the side, the other across the top, the result in each cell |
| Choosing a method, model or case from a problem's properties | A decision table: one row per choice, a column per deciding property, so the student reads off which properties pick it |
| A conditional probability from counts (tests, diagnoses, filters) | A natural-frequency table or tree of whole counts first, then the ratio as a formula; counts are easier to reason with than percentages |
| A system of parts and the flows between them (an agent and its environment, an agent architecture) | A `diagram` or `figure` of the parts and labelled arrows; plan it as a `model`, which must be drawn |
| Something with a physical or spatial shape (an arm and its angles, rooms, a map, a mechanism) | A `figure` drawn as in [figures](figures.md), or an image |
| A hard argument or a multi-part explanation | Numbered `steps`, one claim each |
| A calculation or definition with symbols | A formula block with every symbol explained |
| A calculation the student should redo, or a derivation | A `derivation`: one transformation per line with its reason, a labelled group per requested result |
| A transformation of a state over several steps (a gate on a qubit, a row reduction, a Bayes update) | A `walkthrough` with a formula stage (one line of working per step, the reason as its `why`), or a `derivation` with `walkthrough` when each line draws its own picture |
| Two methods or inputs on the same problem | A `walkthrough` with a `variant`: both runs on one stage, and the `contrast` where they part |
| A worked case of a reusable rule | The worked case (an `example`), then the rule as a formula block with conditions and when to use it; another case only if it tests a new decision, condition or misconception |
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

## Pick the picture the work acts on

Choose the component a student grasps fastest: the one they would sketch on paper.

| The data | Show it as | Never |
| --- | --- | --- |
| A graph or tree, even when the source lists its edges | A `diagram` with the costs on the edges (`layout: "tree"` for a tree); a search on it is a walkthrough over that drawing, the frontier a `state` row | A From/To/Cost table and a table of frontier rows (`graph_as_table`) |
| A board, grid or array (a puzzle, a maze, a matrix, a seating plan) | A `grid`: the board itself, boards side by side when two are compared, the cell being worked marked, a move as an arrow, computed values written into the cells | A list or table of coordinates |
| Values per item, a comparison, a lookup the steps consult | A table | A table of results the steps never reach |

Every step changes what the student sees. A result appears in the step that computes it
(table rows through `shown`, node values through `node_values`), never all at once in the
first step: a walkthrough that marks one row and then announces the total demonstrates
nothing (`unstepped_table`). Work each item the lecture works, or give the finished
table with its working beside it outside a walkthrough.
The weakness is a process hidden by its results. Use a walkthrough when the changes
teach the method. Use a grid in any subject when a value's row and column carry its meaning.
Keep a table when rows are records and columns are attributes, such as methods compared
by cost; there a cell's place means nothing. Keep a table for comparison, lookup or observations read together;
keep a fixed picture outside a walkthrough when nothing meaningful changes.
The weakness is duplicated teaching objects without a new purpose. Let the walkthrough's
first step introduce its object when a static copy adds nothing. Keep a separate reference
or comparison when the learner needs to inspect it alongside the working.

### The lecture's own figures

A slide often already holds the clearest picture. Use it, cropped to the visual, and
write the teaching yourself beside it.

| The picture | Use |
| --- | --- |
| A graph or tree a search runs on | Redraw it as a `diagram`: node values, a growing tree, the app's theme, readable on phones |
| A dense map, board, plot, photo or physical setup the lecture draws well | The lecture's crop as a figure `image` |
| A simple shape the lesson must change or label heavily | Redraw it as SVG ([figures](figures.md)) |

1. **Find the visual.** `tum-mcp study figure PROJECT --key KEY --page N` lists the page's
   figure regions and writes a preview with each one numbered; look at it.
2. **Crop it.** `--region 2` (or `2+3` to keep two boards side by side) or
   `--box x0,y0,x1,y1` in page fractions, with `--name romania-map`, saves
   `figures/romania-map.png` sharply rendered and records its page. Crop the visual and its
   own labels, never the slide title, bullets or footer (`slide_image`): the lesson says
   those in its own words.
3. **Walk through it.** A figure stage with that `image` lets each step point at the part
   it works on: `regions` outline boxes in image fractions (`x`, `y`, `w`, `h`, an optional
   `label`) and dim the rest, such as a tile and its goal square with its distance. Read
   the fractions off the grid preview each crop writes (`.tum-mcp/out/figure-grid.png`).
   When the lecture builds a picture over several slides, crop each state and set the
   step's `frame`.

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
graphs, set each step's `active`, `frontier`, `visited`, `cutoff` and relevant `edges` from the
actual run; use the stage's node keys. Code marks its running `lines`, tables their
`shown` rows or changed `cells`, derivations their `shown` lines, plots their `series`
and SVG figures their `layers`. Grids mark cells with `grid_marks`, draw moves with
`grid_arrows` and write results with `grid_values`; a written value stays for later steps. Clear marks that no longer apply when stepping back
or switching runs. The weakness is unexplained discarded information. When a process
supersedes an earlier record, explain what makes it obsolete and how the method treats it.
Do not add a discard step to a method that has none.
Draw a hierarchy with `layout: "tree"` and preserve the lecture's shape.
The weakness is hidden source structure. Use `visible_nodes` when the source builds a
graph gradually, and reveal every part the source uses. When the source shows the whole
structure, leave `visible_nodes` out; unreached nodes stay faint. Remove a node only
when it does not belong to the source example.
Put changing annotations in `node_values`, separate from stable node labels.
Each step lists the value of every visible annotated node: values do not carry forward.
Do not invent values for unannotated nodes. The graph walkthrough
shows its node-state legend automatically. Derive
graph marks and displayed state from the same computed trace, and include visual values
in the answer key when computed. Do not invent a
changing highlight just to clear `static_walkthrough`. An intentionally fixed
picture belongs beside ordinary explanation, outside a staged walkthrough.

Run the lecture's own example in a `walkthrough`, with its inputs unchanged
([choosing examples](planning.md#choose-the-lectures-examples)).
The weakness is a limit presented as completed work. Distinguish a completed operation
from one prevented by a stopping condition. On a graph, nodes generated but not expanded
at a depth limit use `cutoff`, not `visited`. Use this mark only for that meaning;
an unfinished proof or an inconclusive test needs its own explanation.
Each step does one operation as the lecturer shows it. Compute numerical states in code first.
Its `action` says what; its `why` connects this step's facts to the rule that permits it.
The weakness is template reasoning: changing names does not explain a decision.
A shared rule can repeat when the step's own evidence is visible in its working or state.
Do not force different wording or a fixed sentence order for identical justified operations.
The weakness is missing calculation inputs. State the conventions the result depends on,
then show the original inputs, substitutions and arithmetic in `why` or a state row.
A total or an intermediate difference alone is not complete working. For a qualitative
step, show the relevant facts and inference instead of forcing arithmetic.
`note` names the mistake a student
makes at that moment when there is a typical one. Group the steps by `subgoal` (start,
loop, stop). `state` rows show the data the student would otherwise track mentally; the app
marks what changed since the previous step.
The weakness is an interim value mistaken for a final conclusion. Label provisional
values by their role, and announce a result only when its stopping condition holds.
A method that permits an inconclusive result should say so, not force a success or failure.
Include a real failure and its undo when the
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
