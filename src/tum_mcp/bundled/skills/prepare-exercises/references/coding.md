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

Without a clone, work from the statement and say so in the report.

## Find the concept kernels

For each task, note in `.tum-mcp/work/` a short table:

| Kernel | Essential? | Evidence |
| --- | --- | --- |
| Generic method with a bounded type parameter | Yes | Task 2 signature, test `testSortsComparable` |
| Reading the CSV input format | No (scaffolding) | Provided `Parser` class |

Essential kernels are language features, APIs, design ideas, algorithms, invariants and
contracts the tests check. Domain names, boilerplate, I/O and build setup are scaffolding.

## Build a ladder per essential kernel

Use a fresh, minimal domain so students recognise the idea rather than the task.

| Rung | Check | Purpose |
| --- | --- | --- |
| Trace | `numeric`, `table` or `choice` | Predict output or state after given code. |
| Locate and fix | `numeric` line number on a code block with `line_numbers: true`, then `choice` | Find the faulty line, pick the correct repair. |
| Order | `order` (code lines with `language`; distractors are lines left out of every answer) | Assemble a correct method. |
| Complete | `text` with `format: code` for short gaps (case-sensitive by default), `self_check` with a rubric for longer ones | Fill the gaps in a simplified skeleton of the real task. |
| Write | `self_check` with `format: code`, `starter_code`, model answer and rubric; add example cases as a table | Write a short method or class from scratch. |
| Map back | text step | Name the class or method in the original task where the idea applies. |

Use as many rungs as the kernel needs. Distilled exercises set `kind: distilled`,
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
time, and prefer completion and writing rungs over full projects.
