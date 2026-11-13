# Plan before authoring

Study teaches a student who meets each topic for the first time. A short plan, written
before any block, decides how each idea is taught to this student in this subject. The
moves come from what makes each idea hard, chosen with the
[moves table](teaching.md#teaching-moves), not from a fixed lesson template.

## Teaching profile

`.tum-mcp/course.md` has a `## Teaching profile` section. Write it the first time you author
Study for a course and revise it when its evidence changes. Use the handbook and module
description, the prerequisite modules, past exam formats and the student's own rules in
AGENTS.md. Record, with sources:

- What earlier courses taught and students can be assumed to know. Study reminds the student
  of these in one line where it uses them; it does not re-teach them.
- What understanding means in this subject: compute, trace, prove, design, write code, argue.
- The subject's natural representations and the difficulties the materials or exams show.
- The student's stated background, when they give it.

Keep it to a few lines. An unknown stays "not yet established".

## Teaching plan

Write `.tum-mcp/plans/study/<unit-key>.json` before you author a new unit; reorder,
merge or split units; or rewrite a unit for flow or intuition findings. Use
`tum-mcp study schema plan` and the [plan gate](loop.md). A wording fix needs no new
plan. This JSON is the checked teaching plan; a second Markdown copy is not required.

Name the source preparation, outcomes and concepts in teaching order. For each concept,
choose its kind, a concrete instance with its result, and the block keys that will teach
it. Use `skip` only to explain why the kind's default representation does not fit.
For example:

```json
{
  "item": "study/four-views",
  "preparation": "first-two",
  "outcomes": ["views"],
  "concepts": [{
    "name": "Human likeness and rationality",
    "kind": "comparison",
    "instance": "A model that reproduces human reasoning errors is thinking humanly; a sound theorem prover is thinking rationally. Classify their aims, not whether they use a computer.",
    "outcomes": ["views"],
    "blocks": ["four-views", "four-views-cases"]
  }]
}
```

Before sending the complete batch to the fresh checker, read it once using the questions
below and repair all identifiable gaps together. A conceptual instance can be a concrete
classification or counterexample with its explanation; a multi-step computation is needed
only when the idea calls for one. Keep prerequisite assumptions in the teaching profile
and exclusions in the preparation scope. Add narrative notes only for decisions those
records cannot express. When authoring changes a checked decision, update its plan too.
Reuse unchanged approvals. For a whole-course build, also write
`.tum-mcp/plans/course.md`: the unit order and the question each unit answers, with the earlier
unit whose limitation it resolves.

For application/reasoning objectives, also plan the questions in `practice`, before
writing options. Each entry has `question` (its stable question key), `contrast` (the
worked case it differs from and the unworked input or decision), and `answer` (the new
input, result and shortest valid reasoning). For example, after a DFS trace that reaches
a goal, ask about an unreachable goal behind a cycle: the student must decide whether
visited-state tracking permits termination, rather than replay the demonstrated pop
order. Solve that new case now. A changed start/goal on the same graph can work when it
changes the reasoning; different names or numbers alone are insufficient.
Recall-only objectives need no invented transfer case. Released exercise statements
remain faithful to their source. This is part of the existing plan check, not another
checker or a separate planning document.
Routine application may use new values without becoming a deeper transfer task.
Judge the required calculation or decision, not shared vocabulary or numbers alone.

## Choose the lecture's examples

A lecture demonstrates its methods on worked examples. Choose the ones a student needs
and teach each of them completely; leave the rest out. Read the source's `examples` in
its digest: one line per worked demonstration with its pages, what it shows and its
inputs (graph, weights, board, start and goal).

An example is critical when at least one holds:

| Critical when | For example |
| --- | --- |
| It is the lecture's run of a procedure or calculation the student must perform | The breadth-first run to a goal; A* on the Romania map; h1 and h2 on the 8-puzzle |
| It shows a decision, branch or failure the main run cannot | A path cost improved before the goal is removed; a cutoff versus a failure; a heuristic that loops; a reopened node |
| Later material or the exercises build on it | The map or board that later lectures reuse |
| It shows why a method works or what it costs | The node counts that make iterative deepening affordable; A*'s f-contours; the search tree that repeats a state |

Leave out the same mechanism run again on another object, motivation and application
pictures without workable inputs, empirical tables (state the finding and cite the page)
and partial illustrations the main run already covers. Teach one main example per
mechanism. Add a second only when it shows something the first cannot; a contrast on
the same input is a `variant` run of one walkthrough. Construct an example only when
the lecture has none for the concept, or for practice. There is no quota.

For each `procedure`, `algorithm` or `model` concept, the plan names its `example`:
`origin` (`source` or `constructed`), `source` and `pages`, what it `shows`, its
`endpoint` and the `block` that teaches it; a constructed example says `why`. The plan
check refuses such a concept without one, unless `skip` explains why it is not worked.

```json
"example": {"origin": "source", "source": "uninformed", "pages": "52-56",
  "shows": "B is reached at 310, then improved to 278 before it is removed",
  "endpoint": "B removed with g = 278, path S-R-P-B", "block": "ucs-romania"}
```

Teach a chosen example in full:

1. **Its inputs.** The lecture's exact graph, weights, values, board, start and goal,
   labels and conventions (child order, tie-break, when the goal is tested).
2. **Its picture.** A tree as a tree (`layout: "tree"`, growing as the lecture grows it), a
   weighted graph as a drawn graph with its costs on the edges, and a map, board or plot
   as the lecture's own crop when it is the clearest, walked through with `regions`
   ([picking the picture](representations.md#pick-the-picture-the-work-acts-on)). What the
   slide writes beside a node (g, h, f with their sum) goes in the step's `node_values`,
   not into the node label ([representations](representations.md#algorithm-traces)).
3. **Its steps.** One step is one operation the lecturer shows, usually one expansion:
   never several expansions in one step, never finer than the slides. Compute states in
   code first. Write each step's `why` from its own numbers and the rule that forces it,
   not a sentence repeated across steps. A computed value shows its inputs and arithmetic
   in its `why` or a state row. For tile 3, show the start and goal coordinates:
   row 2 to 0, column 1 to 2, so \(\lvert 2-0\rvert + \lvert 1-2\rvert = 3\).
4. **Every state to its endpoint.** Show every state the slides show and any step a student
   needs between them. When the slides stop early and the result matters, finish the run
   with the lecture's own inputs. Never add a goal, value or
   input the lecture lacks to reach an ending: a run without a goal ends where its
   traversal ends (all nodes within the limit expanded, a cutoff).
5. **One walkthrough per run.** Repeated rounds, such as iterative deepening's limits,
   are subgoals of one walkthrough. Every worked run in the unit, a table of states
   included, is a planned `example`; plan it or cut it.

Each step lists the value of every visible node in `node_values`; values are not carried
from earlier steps. Use run-keyed answer states so verification checks every step. Low cognitive load is about
how an example is presented (one step at a time, the change highlighted, the reason
stated), never about a smaller or easier example.

## Check the plan before writing

Read the plan as a student who knows only the profile's prerequisites and the earlier units:

1. Does each concept use only what comes before it?
2. Does every move have a reason, and is any move forced?
3. Would the student know why each concept comes where it does?
4. Does the through-line cover the source outcomes in the coverage ledger?

When an answer is no, fix the plan before you write blocks.

## Plans differ by content

- **Belief over time (algorithmic).** Through-line: track a hidden state from noisy evidence
  without summing over every path. One umbrella world with one set of numbers carries every
  worked case. Each concept follows from the previous one's limit: one path is easy to score
  but there are \(2^T\) paths, so filtering; filtering ignores later evidence, so smoothing; the
  most likely state each day need not form the most likely sequence, so the sequence
  algorithm. Stationarity and second-order chains are not needed for the tasks: one reminder,
  the rest in Explore.
- **Spectral decompositions (mathematical).** Through-line: describe what a matrix does to each
  direction, and what to use when its eigenvectors do not form a basis. Show the diagonal matrix
  itself first, then the normal versus non-normal contrast. The SVD is a derivation with a
  reason on each line. No bridging sentences where the algebra already connects the steps.
- **Thinking, acting and rationality (conceptual).** Through-line: four ways to define AI and
  why the course takes the rational-agent view. Cases and non-examples, and a decision matrix
  for the two axes. Classify concrete systems with reasons and distinguish a behavioral
  test from a claim about internal reasoning.
