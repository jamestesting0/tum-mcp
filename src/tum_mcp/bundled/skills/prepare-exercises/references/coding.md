# Programming exercises

A programming exercise works in one project: the files of the real task, some to read and
some to edit. The app opens it as an editor beside the task, as Artemis does. Each writing
step writes into a project file, and Compare and the Solution show lines of the solved
files.

## Get the files

Use the first source that exists:

1. **A clone the student points to.** Snapshot it with `tum-mcp study repository PROJECT
   --from FOLDER --exercise ARTEMIS_ID`. The command skips `.git` and other hidden files;
   do not open them yourself, and never build, run, commit or push. Ask whether the clone
   still holds the template or already has their own work.
2. **Artemis.** Call `artemis_get_repository` for the exercise. It saves the source files
   as Artemis copied them from the template, never the student's later work, and returns
   a listing without file text. Copy the saved folder into the course project with
   `tum-mcp study repository PROJECT --from FOLDER`.
   - If it reports `not_started`, ask the student to start the exercise in Artemis, or to
     accept a project rebuilt from the statement. Never start it yourself.
   - If the repository is larger than the editor holds, narrow it with `include` globs to
     the source folders the tasks touch.
3. **The statement**, only when neither exists, for example a programming question in a
   PDF exam. Rebuild the files:
   - each class or interface in the statement's UML gets a file with exactly its members;
   - code the statement prints goes into its file, unchanged;
   - a run or test the statement describes gets a read-only `Main` or test file;
   - a `TODO` comment marks each place where the statement assigns work.
   For an Artemis exercise, say why in `rebuilt_because`.

The problem statement comes from `artemis_get_exercise`: class diagrams, code excerpts and
constraints. Its `tasks` list the graded tasks with their test ids; the `<testid>` markup
is metadata, never statement text. With `save_images=true` it saves each embedded image,
such as a state chart. The student's visible feedback (`artemis_get_feedback`, when they
ask for it) shows through failing test names where students struggle.

## Build the project

1. Decide which files the tasks change. Those are `editable`; every other file is
   read-only. A class the task asks the student to create is an editable file that starts
   empty.
2. Write each editable file solved, as a correct answer leaves it, under
   `.tum-mcp/work/projects/EXERCISE/solved/` at the same path. Change only what the
   tasks ask for; keep the template's names, imports and layout.
3. Pack the project into the exercise:
   `tum-mcp study files PROJECT EXERCISE --from artemis-ID --editable PATH ... --solutions
   DIR --description TEXT`. A rebuilt project passes `--from STARTER_DIR --origin rebuilt`;
   distilled practice passes `--origin authored`.
4. Pack again after any change to the solved files. `study lint` flags a project that no
   longer matches its Artemis snapshot.

Rebuild the statement's class diagrams as `uml` class diagrams with the members the tasks
need, beside the files. Code is never run: check the solved files by careful reading and
tracing.

## Write the guide

- A writing step's prompt names the file and the subgoal it reaches, such as "In
  `IdleState.java`, store the request and start boarding", never only "the required
  behavior". It sets the self-check's `file`, and its `code` reference points at the
  starter lines where the work goes, so the app opens the file there.
- `solution_code` points at the solved lines the step produces, with a `walkthrough` that
  explains them. Compare shows those lines; the step has no `model_answer`.
- A reading step points at the lines to read with `code`.
- A Solution answer for a coding part points at its solved lines with `code`.
- A part that asks to run code becomes a trace step: the student predicts the output or
  state for the entry file or test, and Compare shows the trace.

Copy the shape from `tum-mcp study schema --example step-code` and `--example files`.

## Find the concept kernels

For each task, note in `.tum-mcp/work/` a short table:

| Kernel | Essential? | Evidence |
| --- | --- | --- |
| Generic method with a bounded type parameter | Yes | Task 2 signature, test `testSortsComparable` |
| Reading the CSV input format | No (scaffolding) | Provided `Parser` class |

Essential kernels are language features, APIs, design ideas, algorithms, invariants and
contracts the tests check. Domain names, boilerplate, I/O and build setup are scaffolding.

## Distilled practice per essential kernel

Add distilled practice only when the student asks for it. Use a fresh, minimal domain so
students recognise the idea rather than the task. Distilled exercises set
`kind: distilled` and `distilled_from` with the original exercise keys; the app shows
"Practice for" links back to the originals. Each one has a small `authored` project of two
or three files.

| Step | Check | Purpose |
| --- | --- | --- |
| Write | `self_check` with `format: code` and `file`, with `solution_code` and a rubric of the essential points; add example inputs and outputs as a table | Implement the method or class that uses the kernel. One per essential kernel. |
| Trace | `numeric`, `table` or `choice` | Predict output or state after given code, when a misconception about behaviour is likely. |
| Fix | `numeric` line number on a code reference, then the corrected line as `text` with `format: code` | Find and repair a typical bug. |
| Map back | text step | Name the class or method in the original task where the idea applies. |

Do not replace writing with recognition. Arranging given lines or choosing where a field
belongs lets a student pass without producing code. Use `choice` only for a genuine design
decision with plausible alternatives. Use only the steps the kernel needs.

## Keep it faithful

- Every essential kernel maps to at least one distilled item.
- Same language version, standard library and APIs as the course.
- A project from Artemis shows the template's files as they are; never reformat, rename
  or trim them.
- Accept every equivalent form a correct solution may take.

## Programming exams

Programming exams reuse these kernels under time pressure. Their exam patterns usually
read: read the task list and constraints, locate the TODOs, satisfy contracts in test
order, then check edge cases mentally. Size forecast coding questions to the exam's
time, and prefer writing single methods or small classes over full projects.
