# Review gate and representations

Shared by prepare-study, prepare-exercises and prepare-exams. A build checks the schema;
`tum-mcp study report PROJECT` (and `study exam-report` for Exam Prep) derives review flags
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
5. Show each idea in the shape it has (table below); prose says only what the picture cannot.
6. Review the last batch to the same depth as the first, against the source's own outcomes.
7. Resolve or justify every flag from `study report`.
8. Score the batch with [review-course](../../review-course/SKILL.md); its scorecard turns
   stale when an item changes, so the review follows the content.

## Choose the representation

| The idea is | Show it as |
| --- | --- |
| A term students must learn | A `definition` block; mark later mentions `{{term}}` |
| An algorithm or process over time | A diagram whose frames carry `state` rows (queue, domains, values) and a reason in each caption, or a trace table with one row per step |
| Parallel cases (games, environments, designs) | A table with one row per case, or a list |
| A calculation or definition with symbols | A formula block with every symbol explained |
| Classes, relations, interactions, behaviour over events | A UML class, sequence or state diagram |
| A hierarchy (files, objects, recursion) | A tree |
| Code to read, trace, fix or write | Code, with a walkthrough when it is read part by part |
| A relation between quantities | A plot |

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
