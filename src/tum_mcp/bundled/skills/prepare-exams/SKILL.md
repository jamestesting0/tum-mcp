---
name: prepare-exams
description: Prepare a local Exam workspace for a TUM course from its past exams, exercises and materials - a cheatsheet with a semester map, recurring exam patterns with solving workflows, guided past papers and forecast practice exams. Lessons use prepare-study; weekly sheets use prepare-exercises.
---

For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. The handbook's receipt describes local review,
not live freshness; verify affected facts against sources. Reuse context already
read in this request. Do not re-read the whole inventory for each authoring step. Look at
every slide, sheet or exam page you rely on: `tum-mcp study text` finds and quotes it but
drops figures and scrambles tables and formulas. Open the PDF page if your tools display
PDFs; otherwise add `--images` and open the image. A scanned page has
no searchable text, so a phrase search can miss what is on it.

Write in the course's content language for this workspace: `languages.<workspace>` in
`.tum-mcp/course.md` (`study`, `exercises`, `exam` or `lectures`). When it is missing, use
`content_language`, the language the course is taught in. If that differs from the student's
language (`student_language`; record it from this chat when missing), ask which of the two
they want before you plan or write anything, and end your turn with that question. Never draft
in one language while the answer is open. Only when you cannot ask at all, use the course's
language. Record each language as a two-letter code such as `en` or `de`. Translate a released statement
faithfully: its givens, symbols and labels stay as printed. Never translate code or
identifiers such as method, class, variable and file names. When the workspace language
differs from the course's or the student's, list each key term once in `app/terms.json`
under `pairs` (`study schema terms`). Both cases need it: an English workspace of a German
course, and a German workspace for a student who writes in English. A term spelled the same
in both languages needs no pair. The build marks
its first use in each unit and shows the other language there, so never add it in brackets.

You author the files under `app/exam/` (`exam.json`, and one file per concept, pattern
and mock; `study schema exam`); `tum-mcp study build PROJECT`
renders it as the Exam workspace beside Study and Exercises. `study schema --example
exam-pattern` prints a complete, valid pattern file and `exam-mock` a mock exam;
start from them. `exam-step`,
`exam-concept`, `exam-formula`, `exam-pitfall`, `exam-drill` and `exam-guided-step` print
single parts. Code derives every
count, rate, order, map position and blueprint; the schema has no count fields.
Publishing the course app includes prepared Exam content; original documents and
source citations stay local. Use publish-course for a publication request.

**Maths.** Everything a student reads that is mathematics is LaTeX in `\( ... \)`, one
span per expression (JSON doubles each backslash). `study lint` reports `plain_math` and
`math_word`, and readiness waits until both are gone:

| Write | Not |
| --- | --- |
| `\(X = \{1, 2\}\)`, `\(Z = \emptyset\)` | X={1,2}, Z=∅ |
| `\(P(a)\)`, `\(\neg P \lor Q\)`, `\(P \leftrightarrow Q\)` | P(a), ¬P ∨ Q, P↔Q |
| `\(0.6 \cdot 200 + 0.4 \cdot (-300) = 0\)`, one span | 0.6·200 + …, or `\(0.6\)`·200 |
| `\(P(A = \mathrm{true} \mid \mathrm{warning})\)` | `\(P(A=true \mid warning)\)` |
| `\(\frac{0.4}{0.4 + 0.1} = 0.8\)` in a worked step | 0.4/(0.4+0.1) = 0.8 |

## Workflow

1. **Scope.** Read the handbook's assessment section, then
   `tum-mcp study exam-report PROJECT`. A missing binding goes through sync-course.
   If past exams are missing, ask once: the user may sync them, import files they hold
   with `tum-mcp study import PROJECT --file F --kind exam --title T`. Prepare what
   the evidence supports; report the rest. A request for the whole course covers the
   material released so far: prepare that now and name the unreleased weeks in the
   report; never pause the request for material that does not exist yet. Without past
   exams, the exercises set the question types: read the Exercises workspace, else the
   released exercises and the repositories that are available (a missing one never
   stops the work). Every kind of task the exercises ask becomes a pattern, or a
   practice question when only one exercise asks it. Without Study,
   Exam works alone; offer once, in the report, to prepare Study. Exam serves students
   who have studied the material: keep it concise and never re-teach. Depth stays in
   Study, one tap away through the Recall row of each pattern and solution.
2. **Evidence** ([sources](references/sources.md)). Weigh official rules and exams
   above student copies; keep conflicts visible. Find and quote with
   `tum-mcp study text PROJECT --key K --pages N-M`, and look at each page a question
   comes from. Read each document once, even when several copies exist. Fill the
   exam profile from the latest available paper's cover and working instructions
   (points and allowed aids included), unless newer official exam guidance supersedes
   it. Name the dated reference in `profile.notes`; do not leave stated facts blank.
3. **Registry** ([patterns](references/patterns.md)). One sitting per real exam;
   attach every copy of it as roles of one variant. Fetch an exam the course lists before
   importing a student's copy; `study import` then reports the course's own resource.
   Extract every subquestion and classify it by transferable solving strategy, reusing
   existing patterns first.
4. **Cheatsheet** ([cheatsheet](references/cheatsheet.md)). Record every kind of
   exam-relevant source material; give each its form, its line first and the rest behind
   Expand; draw the semester map by linking each core idea to what it builds on or
   contrasts with.
5. **Patterns** ([patterns](references/patterns.md)). A short workflow that solves every
   member. Methods that differ only in the rule one step applies (for example, graph
   searches that differ only in the key that orders the frontier) are one pattern with
   cases on that step. Give
   recognition cues from the question text and the formula, rule or code each step and case
   applies (never a description of it in words), marking points, pitfalls as
   wrong/right/why in their situation, worked practice that applies every step and covers
   each case once, and drills that practise every case again at the exam's size and answer
   format, with a staged `guide` and a complete Solution. In a programming course, code
   patterns practise writing code, as in [coding](../prepare-exercises/references/coding.md).
6. **Practice** ([forecast](references/forecast.md)). Make every in-scope past paper
   replayable by default (statement and solution; a solution you wrote is labelled as
   yours), with task-specific `guidance.steps`; a generic “solve the question” step
   is not guidance. Missing guides for current classified paper questions hold the
   draft gate before review. A listed paper students cannot practise holds the gate. Where a
   question's answer is computable, its answer key in `.tum-mcp/checks/` computes the
   new variants' answers too. A mock exam (`kind: "exam"`) simulates the real exam's
   style and blueprint (`exam-report --section blueprint`) within the prepared scope; for
   part of the course it takes that part's share of the time. A separate untimed set
   (`kind: "practice"`) targets important core ideas the patterns and drills leave
   unpractised, and the lecture methods of a pattern's question family that no past paper
   asked yet (a second algorithm for the same task, the reverse computation). Other
   uncovered cheatsheet ideas are fine; they do not block readiness.
   Every question you write shows a figure, code, diagram, formula, table or plot beside
   its text, written as in [writing](../prepare-study/references/writing.md).
7. **Build and verify** ([verification](references/verification.md)). Edit each item's
   own file and preserve unrelated items; plan patterns (their cases) before writing.
   Write a coherent batch (one topic's entries and patterns), then lint it once with
   `tum-mcp study lint PROJECT` and fix every finding before linting again. Use
   `--item exam/pattern/KEY` or `--item exam/sheet` only to recheck one repair. Run
   each check once per round of fixes, never after each single fix. Build once per
   coherent batch, review `exam-report --section targets`, finish Phase A of the
   [draft checks](../prepare-study/references/loop.md), run
   `tum-mcp study visuals PROJECT --exam` and `--interact`, and fix what they report. Solutions
   answer each part once, labelled, in the form the part asks for. When a question needs
   knowledge Study lacks, record it in the [coverage ledger](../prepare-study/references/coverage.md).
   Cheatsheet facts taught in the requested Study need a Revision flashcard or question;
   topics beyond it are judged through Exam practice, never by adding Study units.
   [review-course](../review-course/SKILL.md) checks the cheatsheet, each pattern and
   each mock question. Finish the requested draft and its checks, then offer one
   review-and-repair round in a short question of your own, unless review was already
   requested.
8. **Report** sittings, questions and coverage, review items, kept outliers, gaps and
   checks run, in plain words. Launch with `tum-mcp study`.

## Judgment

Targets such as entry length, workflow length, map size and blueprint fit are
guidance. `exam-report` flags outliers; keep one only when the content needs it and
say why. Hard rules are enforced by the schema: resolvable references, one document
per sitting, acyclic prerequisites, truthful labels and consistent marking.

## Boundaries

Never call a forecast a prediction, a leak or official; frequencies are history.
Say how uncertain a forecast is in your report, never in the app.
Student solutions are unverified; official labels need an official source. Solve every
answer independently. Never start, submit or execute course code, read `.git/` or
credentials. Original campus and imported files stay local. Prepared Exam content may
be published through publish-course only with explicit or saved full-app publication
consent. Old selective settings need explicit adoption. Exam never
replaces Study; link to its units when they exist.
