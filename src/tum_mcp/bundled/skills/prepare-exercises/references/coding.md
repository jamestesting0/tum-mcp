# Distil programming exercises

Large Artemis programming tasks train a few ideas inside a lot of scaffolding. Keep the
original exercise as it is, and add **distilled** practice that trains each idea in a
small, self-contained setting.

## Read what is available

- The problem statement from `artemis_get_exercise`: task list with test names, class
  diagrams, code excerpts and constraints. Test names often state the contract.
- The student's own visible feedback with `artemis_get_feedback`, when they ask for it:
  failing test names show where students struggle.
- A local clone of the student's own repository, when the user points to it. Read
  source files only. Never open `.git/`, build scripts, IDE settings or anything that
  may hold credentials or remote URLs; never build, run, commit or push.

Without a clone, work from the statement and say so in the report. Rebuild class
diagrams from the statement (often PlantUML) as `uml` class diagrams with the members
the task needs, never as an image or a generic box diagram.

## Find the concept kernels

For each task, note in `.tum-mcp/work/` a short table:

| Kernel | Essential? | Evidence |
| --- | --- | --- |
| Generic method with a bounded type parameter | Yes | Task 2 signature, test `testSortsComparable` |
| Reading the CSV input format | No (scaffolding) | Provided `Parser` class |

Essential kernels are language features, APIs, design ideas, algorithms, invariants and
contracts the tests check. Domain names, boilerplate, I/O and build setup are scaffolding.

## Show the real files

When the exercise comes with template files (Artemis repositories, provided classes),
show them in a `files` block so students work in the same structure as the real task:
editable files keep their `TODO` markers, read-only files are the ones to read.
Steps point at the relevant lines with `code` references and write into a file with
the self-check's `file`, so a step reads "In `Supervisor.java`, replace ..." beside
the exact lines it means. A distilled exercise uses a small new workspace of two or
three files in a fresh domain.

## Build practice per essential kernel

Use a fresh, minimal domain so students recognise the idea rather than the task.
The core step is writing code. Give the method signature or a small class skeleton as
`starter_code` that declares every field and type the model answer uses, show the types
it works with as a code or UML block, and ask for the
body. The app opens the skeleton in a code editor; the student then compares their
code with the model answer and rubric.

| Step | Check | Purpose |
| --- | --- | --- |
| Write | `self_check` with `format: code`, `starter_code` (the signature or skeleton with a comment where the code goes), a complete model answer and a rubric of the essential points; add example inputs and outputs as a table | Implement the method or class that uses the kernel. One per essential kernel. |
| Trace | `numeric`, `table` or `choice` | Predict output or state after given code, when a misconception about behaviour is likely. |
| Fix | `numeric` line number on a code block with `line_numbers: true`, then the corrected line as `text` with `format: code` | Find and repair a typical bug. |
| Map back | text step | Name the class or method in the original task where the idea applies. |

Do not replace writing with recognition. Arranging given lines or choosing where a
field belongs lets a student pass without producing code. Use `choice` only for a
genuine design decision with plausible alternatives, and make every step a real piece
of the work rather than a question about the statement.

Use only the steps the kernel needs. Distilled exercises set `kind: distilled`,
`distilled_from` with the original exercise keys and `concepts` naming the kernels;
the app shows "Practice for" links back to the originals.

## Keep it faithful

- Every essential kernel maps to at least one distilled item.
- Same language version, standard library and APIs as the course.
- Quote at most short, cited excerpts of course code; never copy template files.
- Code is never executed. Verify answers by careful reading and tracing, and accept
  every equivalent form a correct solution may take.

## Programming exams

Programming exams reuse these kernels under time pressure. Their exam patterns usually
read: read the task list and constraints, locate the TODOs, satisfy contracts in test
order, then check edge cases mentally. Size forecast coding questions to the exam's
time, and prefer writing single methods or small classes over full projects.
