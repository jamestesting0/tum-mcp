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
a private review note and is not shown. Prerequisites pair a Study unit key with an
inline explanation so Exercises can be prepared first; later Study builds validate links.

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
| self_check | A `model_answer` and a rubric of the essential points, with format `text` or `code`. For code, either `file` names an editable file of the question's `files` block, which the student edits there, or `starter_code` is a skeleton that opens in the step's own editor. The model answer is shown as highlighted code. Code is never run, and nothing is graded by keywords. |

For every check except `choice` the student presses Compare and sees the answer, the
step's explanation and the check's `feedback` under "If yours differs". Give exactly
one answer: the clearest form, not a list of variants. Write the feedback as the repair
for the likeliest mistake.

## Say the task first

The first sentence of every question you write names what the student produces and
where: "Implement `Directory.size()` so that ...", "Explain why ...", "Draw the
sequence of calls for ...". Context follows only as far as the task needs it. A
title such as "The task" or a description of the situation alone is not a task. Do
not repeat the task in every step; each step prompt names its own move in one
sentence. Released statements stay as released; when one does not say what to hand
in, the first step does.

## Point at the code

For programming exercises, put the files in a `files` block: the files the student
changes (`editable: true`, with the template's `TODO` markers) and the read-only files
they need to read, under their real package paths. Keep it to the files that matter.
A step that needs code points at it with `code: [{"path": ..., "lines": "8-9"}]`
instead of quoting it; the app shows those lines with an "Open in files" jump. A
writing step names the file in its prompt and sets the self-check's `file` to it; the
model answer shows only the part that changes. Line ranges are checked against the
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
build rejects text-only ones. Original statements stay as released: add the picture
in a step or the worked answer instead. Pick what the question is about:

| The question is about | Show it with |
| --- | --- |
| Code to write, fix, trace or extend | A code block with the starting code, the class or method signatures, or the faulty lines (`line_numbers: true` when steps refer to lines). |
| Classes, interfaces and their relations, design patterns | A UML class diagram (`uml`, `diagram: class`) with the members the question needs. |
| Calls between objects over time, protocols, callbacks | A UML sequence diagram (`uml`, `diagram: sequence`), with loop or alt fragments for repetition and branches. |
| Graphs, trees, object structures, data structures | A diagram of the structure, or a table of its state after each operation. |
| Calculations, proofs, definitions with symbols | A formula block with every symbol explained. |
| Comparisons, traces, inputs and outputs, costs | A table. |
| Functions, growth, measurements | A plot. |

In prompts, hints and feedback, put identifiers and short code in backticks
(`` `notify()` ``) so they render as inline code, as in prepare-study.

Make the visual carry information the question needs; never decorate. Keep the code
short enough to read on a phone, and do not let the visual reveal the answer.

Use rich step blocks for long mathematical givens, diagrams, code and tables. Code
blocks accept `line_numbers: true` when a step refers to lines. Distilled practice sets
`kind: distilled`, `distilled_from` (original exercise keys) and `concepts`. All
block/graph sources must be declared. Put full model proofs/code in safe worked
solution blocks, with assumptions and alternative valid methods; do not bury them
in a multiple-choice answer. The app already labels the solution, so title its blocks
by what they show ("Composite roles"), never "Solution". A step may omit a check. The direct solution is always
available. Record whether a solution is authored or official (official requires a
declared official_source) for provenance; the app shows every solution simply as the
solution. Optional
transfer contains a fresh prompt and comparison answer. Set category, summary, week
and due_at are optional and appear in the exercise list; date values include a timezone.

Semantic exercise changes start fresh progress while retaining old browser records;
reviewing source hashes or changing group labels alone preserves learning revision.
Do not copy student responses into authored data. Keep comments in .tum-mcp/comments.json.
The single builder installs shared assets and one payload, exposing only authored
workspaces. Preserve content.json and unchanged exercises byte-for-byte when possible.
