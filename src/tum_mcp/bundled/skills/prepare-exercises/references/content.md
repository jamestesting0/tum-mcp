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
and reviewed explanation. Use the original task's response form:

| Check | Use and boundaries |
| --- | --- |
| choice | Four distinct options with specific misconception feedback. Do not convert a proof or calculation table into recognition just for convenience. |
| numeric | Finite answer, nonnegative absolute tolerance, optional unit and repair. Plain decimals/scientific notation only; not a symbolic algebra grader. |
| table | caption, columns and labelled rows. Each cell is given text, numeric (key, answer, tolerance, feedback), or text (key, accepted variants, feedback). Text comparison trims/collapses whitespace and ignores case; use only when that is valid for the subject. |
| graph | A safe diagram plus mode nodes, edges or path and reviewed answer variants. Node keys identify nodes; edge keys are start--end. Use a neutral question frame that does not reveal the solution. Paths are ordered node lists respecting direction; node/edge selections are sets. Use for traversal, reachability, cuts or selected edges. Use plot for line graphs; use paper + rubric for arbitrary drawings. |
| plot | A line graph block with labelled axes and optional given series; increasing x_values, one answer y for each, absolute tolerance, positive snap step and repair feedback. Learners tap the graph or edit coordinates; keyboard arrows adjust points. This checks finite sample coordinates, not an entire continuous curve. Give enough sample positions for the actual learning goal; use paper + rubric for open sketches or derivations. |
| text | A short typed answer: accepted variants, `case_sensitive` (default true), `whitespace` exact, collapse or ignore. Use format `code` with a language for code gaps. Not for prose that has many valid phrasings. |
| self_check | Rubric and model_answer with format text, math or code. Math accepts long plain text/LaTeX work; code accepts an optional language and literal starter_code: the signature or skeleton the student completes, opened in the code editor; the model answer is shown as code. Code is never executed. Proofs, symbolic equivalence and programs are compared by the learner, never graded by keywords. |

Only `choice` is checked by the app. For every other kind the student presses Compare
and sees the expected answer (the first accepted variant, the numeric answer with its
unit and tolerance, the filled table, the graph answer by node label or the plot
targets), the step's explanation, and the check's `feedback` under "If yours differs".
Write that feedback as the repair for the likeliest mistake.

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
in a multiple-choice answer. A step may omit a check. Work on paper/in an editor is
always valid; don't force typing, and keep the direct solution available. Solutions
state authored or official; official requires a declared official_source. Optional
transfer contains a fresh prompt and comparison answer. Set category, summary, week
and due_at are optional and appear in the exercise list; date values include a timezone.

Semantic exercise changes start fresh progress while retaining old browser records;
reviewing source hashes or changing group labels alone preserves learning revision.
Do not copy student responses into authored data. Keep comments in .tum-mcp/comments.json.
The single builder installs shared assets and one payload, exposing only authored
workspaces. Preserve content.json and unchanged exercises byte-for-byte when possible.
