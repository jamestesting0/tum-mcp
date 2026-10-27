# Structured exercise input

Run `tum-mcp study schema exercises` for the authoritative schema and `study inspect
PROJECT` for source freshness. Author app/exercises.json, or study/exercises.json
when that legacy layout already exists. Never create both folders. Layout upgrades
are explicit: `study build PROJECT --upgrade-layout` retains a checked backup;
ordinary legacy builds remain supported.

The v1 document binds course_key to one course and contains stable sets with
exercises. Preserve set/exercise/step keys across edits. Sources use inventory keys
and reviewed SHA256 values. Statements and solutions reuse the safe Study block
types (text, code, table, formula, diagram and line graph); no embedded HTML or executed code.
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
| table | caption, columns and labelled rows. Each cell is given text, numeric (key, answer, tolerance, feedback), or text (key, accepted variants, feedback). Text comparison trims/collapses whitespace and ignores case; use only when that is valid for the subject. Check partial errors without revealing the correct values. |
| graph | A safe diagram plus mode nodes, edges or path and reviewed answer variants. Node keys identify nodes; edge keys are start--end. Use a neutral question frame that does not reveal the solution. Paths are ordered node lists respecting direction; node/edge selections are sets. Use for traversal, reachability, cuts or selected edges. Use plot for line graphs; use paper + rubric for arbitrary drawings. |
| plot | A line graph block with labelled axes and optional given series; increasing x_values, one answer y for each, absolute tolerance, positive snap step and repair feedback. Learners tap the graph or edit coordinates; keyboard arrows adjust points. This checks finite sample coordinates, not an entire continuous curve. Give enough sample positions for the actual learning goal; use paper + rubric for open sketches or derivations. |
| self_check | Rubric and model_answer with format text, math or code. Math accepts long plain text/LaTeX work; code accepts an optional language and literal starter_code. Code is never executed. Proofs, symbolic equivalence and programs are compared by the learner, never graded by keywords. |

Use rich step blocks for long mathematical givens, diagrams, code and tables. All
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
