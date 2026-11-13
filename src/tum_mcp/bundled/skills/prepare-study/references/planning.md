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
input, result and shortest valid reasoning). The weakness is practice that replays a
solved case without requiring the intended decision. Change a relevant condition or
input, then solve the new case now. Reusing the same setting is useful when the required
reasoning changes. Renaming alone does not establish transfer.
Recall-only objectives need no invented transfer case. Released exercise statements
remain faithful to their source. This is part of the existing plan check, not another
checker or a separate planning document.
Routine application may use new values without becoming a deeper transfer task.
Judge the required calculation or decision, not shared vocabulary or numbers alone.

## Choose the lecture's examples

A lecture demonstrates its methods on worked examples. Choose the ones a student needs
and teach each of them completely; leave the rest out. Read the source's `examples` in
its digest: one line per worked demonstration with its pages, what it shows and its
inputs and conventions.

The weakness is incomplete example selection: explanatory demonstrations can be lost
when only exercises or end-to-end calculations are recorded.

An example is critical when it teaches a procedure the student must perform, shows a
decision or failure the main example cannot, supports later work, or explains why a
method works or what it costs. This includes an algorithm's effort count, a physics
conservation argument and a legal case that establishes an exception. Judge what the
student must understand, not the subject or the example's format.

Leave out the same mechanism run again on another object, motivation and application
pictures without workable inputs, empirical tables (state the finding and cite the page)
and partial illustrations the main run already covers. Teach one main example per
mechanism. Add a second only when it shows something the first cannot; a contrast on
the same input can be a `variant` run of one walkthrough. Keep distinct source
demonstrations when they teach different decisions, even on the same object.
Construct an example only when
the lecture has none for the concept, or for practice. There is no quota.

For each `procedure`, `algorithm` or `model` concept, the plan names its `example`:
`origin` (`source` or `constructed`), `source` and `pages`, what it `shows`, its
`endpoint` and the `block` that teaches it; a constructed example says `why`. Use `shows`
to name the inputs, picture and decisive working or test, not only the concept.
Keep the source pages through that decision and conclusion, not just the setup. The plan
check refuses such a concept without one, unless `skip` explains why it is not worked.

```json
"example": {"origin": "source", "source": "lecture", "pages": "12-14",
  "shows": "At the given temperature and pressure, draw the phase boundary and use its position to choose the conservation rule",
  "endpoint": "The final phase and energy balance agree at the boundary", "block": "boundary-case"}
```

Teach a chosen example in full.
The weakness is a selected example that loses the evidence for its teaching point.

1. **Its inputs.** Preserve the lecture's exact givens, labels, assumptions and conventions.
   The weakness is a smaller substitute that drops the source example's difficulty.
2. **Its picture.** Show the object the reasoning acts on, in its natural form.
   Use the lecture's crop when it is clearest
   ([picking the picture](representations.md#pick-the-picture-the-work-acts-on)).
   Do not force an argument or classification into a graph or an animated process.
3. **Its decisive working.** Preserve each operation the lecturer shows and its order. Compute
   numerical states in code first; check qualitative reasoning against the source.
   The weakness is unexplained working: a result or a repeated rule hides the step's
   own justification. Use the step's facts and the rule that licenses it. A calculation
   shows the original inputs, substitutions and arithmetic in `why` or a state row.
   An argument needs its premises and inference, not invented numbers.
4. **Its endpoint and teaching result.** Show every state the slides show and any step a student
   needs between them. When the slides stop early and the result matters, finish the run
   with the lecture's own inputs. Going beyond the lecture is fine; covering less is not.
   Never invent a missing input or desired result to force an ending. An unresolved
   case may end at a justified limit or an inconclusive result. Preserve the comparison
   or result that makes the example's point, including its interpretation. Correct
   intermediate calculations alone do not establish that point. Do not add a comparator
   when the example teaches no comparison.
5. **One walkthrough per process.** Keep a continuous run, derivation, proof, simulation
   or case history in one walkthrough, with every step it needs. Length is never a reason
   to drop, merge or split steps: the app's step menu keeps long walkthroughs easy to move
   through. Group its phases with `subgoal`; do not repeat
   the picture and restart numbering in consecutive widgets. Iterations of a solver
   and stages of a reaction stay together. Separate blocks are useful for genuinely
   different inputs or decisions, such as contrasting two experimental setups.
   Every worked run in the unit, a table of states
   included, is a planned `example`; plan it or cut it.

For comparison values, follow the [stage annotation guidance](representations.md#algorithm-traces).
Use run-keyed answer states so verification checks every step. Low cognitive load is about
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
