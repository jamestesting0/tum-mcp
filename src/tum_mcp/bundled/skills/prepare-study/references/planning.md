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

Write `.tum-mcp/plans/<unit-key>.md` before you author a new unit; reorder, merge or split
units; or rewrite a unit for flow or intuition findings. A wording fix needs no plan. The plan
is as long as the unit needs: a one-idea unit may need ten lines.

```markdown
# <unit title>

Student: what they bring (profile prerequisites, earlier units) and what is new or hard here.
Through-line: the question this unit answers, and its story in two or three sentences.

## Concepts, in teaching order
- <concept>: why it is hard (new notation, many interacting parts, counter-intuitive,
  confused with X, long procedure) or "simple".
  Moves: <...> because <...>. Relation to the previous concept: follows from / contrasts /
  parallel / none. Representation: <...> because <...>. Practice: <the decision it tests>.

Examples: one running example, several, or none, and why.
Left out or moved to Explore: <...>, and why.
Changed while authoring: <decision>, and why.
```

Write each decision with its reason. When authoring shows a better decision, change the plan
too; review-course checks the unit against it. For a whole-course build, also write
`.tum-mcp/plans/course.md`: the unit order and the question each unit answers, with the earlier
unit whose limitation it resolves.

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
  for the two axes. No worked or running example: nothing here has interacting steps.
