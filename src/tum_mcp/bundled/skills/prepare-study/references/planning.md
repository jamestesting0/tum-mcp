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
