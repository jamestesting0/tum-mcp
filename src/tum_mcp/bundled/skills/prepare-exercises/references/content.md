# Structured exercise input

Run `tum-mcp study schema exercises` for the authoritative schema and `study inspect
PROJECT` for source freshness. Author app/exercises.json, or study/exercises.json
when that legacy layout already exists. Never create both folders. Layout upgrades
are explicit: `study build PROJECT --upgrade-layout` retains a checked backup;
ordinary legacy builds remain supported.

The v1 document binds course_key to one course and contains stable sets with
exercises. Preserve set/exercise/step keys across edits. Sources use inventory keys
and reviewed SHA256 values. Statements and solutions reuse the safe Study block
types (text, code, table, formula, diagram, UML diagram and line graph); no embedded HTML or executed code.
Declare every used source. Use optional parts for original subparts and objectives
for observable reasoning goals; the app lists objectives as goals when a student
opens Guidance, so phrase them without giving away the method. A step's purpose is
a private review note and is not shown. Prerequisites pair a Study unit key, and the
`block` key of the passage that teaches the idea when there is one, with an inline
explanation so Exercises can be prepared first; the app opens that passage beside the
exercise, and later Study builds validate links. Check that the passage really teaches
what the task needs ([coverage](../../prepare-study/references/coverage.md#while-authoring)).

Steps contain purpose, prompt, optional rich blocks, sources/check, requested hints
and reviewed explanation. Students answer on paper; the app shows no answer boxes
except the choice options, the code editor, and the graph and plot controls. Pick the
check by what the student should compare with:

| Check | Use and boundaries |
| --- | --- |
| choice | The only check the app grades. Four distinct options, each with feedback that names the misconception; the student can open why every option is right or wrong. Use it for genuine decisions, not to turn a calculation or proof into recognition. |
| numeric | One finite `answer` with an optional `unit`, and `feedback` that repairs the likeliest wrong value. |
| table | Caption, columns and labelled rows. Each cell is `given` text, `numeric` (key, answer, optional unit) or `text` (key, answer). The student sees the table with empty answer cells, fills them in on paper and compares. |
| graph | A safe diagram, a mode (`nodes`, `edges` or `path`), the answer and feedback. The student can select on the diagram; Compare shows the first answer by node label. Use a neutral frame that does not reveal the solution. |
| plot | A line graph with labelled axes and optional given series, increasing `x_values`, one target `y` each, a snap step and feedback. The student can place points; Compare shows the targets as a table. |
| text | One short `answer`, such as a name, a value with words or one line of code (`format: code` with a language), and feedback. Not for prose with many valid phrasings; use `self_check` for those. |
| self_check | A `model_answer` and a rubric of the essential points, with format `text` or `code`. A text model answer is a list of blocks in the shape of the answer: a filled table for cases, points for parallel items, a formula for a derivation. For code, the model answer is code, and either `file` names an editable file of the question's `files` block, which the student edits there, or `starter_code` is a skeleton that opens in the step's own editor. Code is never run, and nothing is graded by keywords. |

For every check except `choice`, and for a step without a check, the student presses
Compare and sees the answer, the step's explanation and the check's `feedback` under
"If yours differs". Compare is the only reveal: the explanation adds the reasoning and
never repeats the model answer (the build rejects a copy). Give exactly one answer: the
clearest form, not a list of variants. Write the feedback as the repair for the likeliest
mistake.

## Say the task first

The first sentence of every question you write names what the student produces and
where: "Implement `Directory.size()` so that ...", "Explain why ...", "Draw the
sequence of calls for ...". Context follows only as far as the task needs it. A
title such as "The task" or a description of the situation alone is not a task. Do
not repeat the task in every step; each step prompt names its own move in one
sentence. A released statement keeps its wording; when it does not say what to hand
in, the first step does. Write no filler such as "Work through the steps" or "Compare
with the solution": the app already offers those controls.

## Point at the code

For programming exercises, put the files in a `files` block: the files the student
changes (`editable: true`, with the template's `TODO` markers) and the read-only files
they need to read, under their real package paths. Keep it to the files that matter.
A step that needs code points at it with `code: [{"path": ..., "lines": "8-9"}]`
instead of quoting it; the app shows those lines with an "Open in files" jump. A
writing step names the file in its prompt, sets the self-check's `file` to it and points
at the lines to change, so the student opens the file from that excerpt; the model answer shows only the part that changes. Line ranges are checked against the
files, so re-check them whenever a file changes.

## Give the student everything the answer uses

A student sees only the statement, its blocks, the step prompts up to the current one
and any starter code. Every class, method, field, value and constraint that an answer,
hint, explanation, rubric or later step relies on must appear there first, or the step
must ask the student to introduce it and name it ("call it `Unit`"). Introduce a name
once and use it consistently afterwards. When an answer needs the current design,
show it: a UML class diagram with the members, the code being changed, or the data in
a table. Starter code declares the fields and types the model answer uses.

Check every step by reading its answer next to only what the student has seen so far.
If the answer mentions something that is not there, add it to the question, the
prompt or the starter, never only to the answer.

## Show the question, not only tell it

A question students must picture from prose alone is harder than the subject. Every
question you write (distilled practice, Exam Prep practice exams, worked practices
and drills) pairs its text with at least one block that shows the situation; the
build rejects text-only ones. A released statement keeps its wording but not its wall
of text: give each part its own block titled with its number, enumerations as points,
givens (numbers, costs, scoring rules) as a table and the setting as a figure or diagram
beside it. Do not repeat a given in the steps. When a statement relies on a slide or figure,
redraw what it needs beside the statement and cite it with `pages`. Choose the shape as
in [representations](../../prepare-study/references/review.md#choose-the-representation):
code or signatures for code, UML for designs and interactions, a diagram or state table
for structures, a figure for physical setups, a formula for symbols, a table for cases
and traces, a matrix for two-input rules, a plot for growth. Write prompts, hints and
feedback as in [writing](../../prepare-study/references/writing.md).

In prompts, hints and feedback, put identifiers and short code in backticks
(`` `notify()` ``) so they render as inline code, as in prepare-study.

Make the visual carry information the question needs; never decorate. Keep the code
short enough to read on a phone, and do not let the visual reveal the answer.

Use rich step blocks for long mathematical givens, diagrams, code and tables. A table
the student fills in is the step's `table` check, not a block. Code
blocks accept `line_numbers: true` when a step refers to lines. Distilled practice sets
`kind: distilled` and `distilled_from` (original exercise keys). All
block/graph sources must be declared. The solution's `answers` give one short, direct
answer per original part, in order and labelled ("(a)"), in the form the part asks for: a
filled table, the graph, a formula, code. The working belongs in Guidance; assumptions
and alternative valid methods go in `notes`. A step may omit a check. The direct solution
is always available. Record whether a solution is authored or official (official requires
a declared official_source) for provenance; the app shows every solution simply as the
solution. Optional transfer contains a fresh prompt and comparison answer blocks. Set category, summary, week
and due_at are optional and appear in the exercise list; date values include a timezone.

Semantic exercise changes start fresh progress while retaining old browser records;
reviewing source hashes or changing group labels alone preserves learning revision.
Do not copy student responses into authored data. Keep comments in .tum-mcp/comments.json.
The single builder installs shared assets and one payload, exposing only authored
workspaces. Preserve content.json and unchanged exercises byte-for-byte when possible.
