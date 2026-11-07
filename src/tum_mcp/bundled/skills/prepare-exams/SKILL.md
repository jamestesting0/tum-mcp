---
name: prepare-exams
description: Prepare a local Exam workspace for a TUM course from its past exams, exercises and materials - a cheatsheet with a semester map, recurring exam patterns with solving workflows, guided past papers and forecast practice exams. Lessons use prepare-study; weekly sheets use prepare-exercises.
---

When `tum-mcp study status PROJECT` reports `course_memory: true`, use
the installed `course-memory` skill for relationships and scoped source updates.
When disabled, leave retained graph files unused and follow the ordinary workflow.


For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. The handbook's receipt describes local review,
not live freshness; verify affected facts against sources. Reuse context already
read in this request. Do not re-read the whole inventory for each authoring step. Look at
every slide, sheet or exam page you rely on: `tum-mcp study text` finds and quotes it but
drops figures and scrambles tables and formulas. Open the PDF page if your tools display
PDFs; otherwise add `--images` and open the image.

You author the files under `app/exam/` (`exam.json`, and one file per concept, pattern
and mock; `study schema exam`); `tum-mcp study build PROJECT`
renders it as the Exam workspace beside Study and Exercises. Code derives every
count, rate, order, map position and blueprint; the schema has no count fields.
Publishing the course app includes prepared Exam content; original documents and
source citations stay local. Use publish-course for a publication request.

## Workflow

1. **Scope.** Read the handbook's assessment section, then
   `tum-mcp study exam-report PROJECT`. A missing binding goes through sync-course.
   If past exams are missing, ask once: the user may sync them, import files they hold
   with `tum-mcp study import PROJECT --file F --kind exam --title T`. Prepare what
   the evidence supports; report the rest. Exam serves students who have studied the
   material: keep it concise and never re-teach. Depth stays in Study, one tap away through
   the Recall row that patterns and solutions show for their concepts.
2. **Evidence** ([sources](references/sources.md)). Weigh official rules and exams
   above student copies; keep conflicts visible. Find and quote with
   `tum-mcp study text PROJECT --key K --pages N-M`, and look at each page a question
   comes from. Read each document once, even when several copies exist. Fill the
   exam profile from the latest available paper's cover and working instructions
   (points and allowed aids included), unless newer official exam guidance supersedes
   it. Name the dated reference in `profile.notes`; do not leave stated facts blank.
3. **Registry** ([patterns](references/patterns.md)). One sitting per real exam;
   attach every copy of it as roles of one variant. Extract every subquestion and
   classify it by transferable solving strategy, reusing existing patterns first.
4. **Cheatsheet** ([cheatsheet](references/cheatsheet.md)). Record every kind of
   exam-relevant source material; give each its form, its line first and the rest behind
   Expand; link dependent or contrasting ideas.
5. **Patterns.** A short workflow that solves every member, with a decision step where
   the method forks; recognition cues from the question text, the formula, rule or code
   each step and case applies,
   marking points, pitfalls shown in their situation as wrong/right/why, worked practice that applies every
   workflow step and covers each case once, and a drill that practises every case again
   with help initially hidden. Each drill also supplies an optional staged `guide`
   using prompts, hints and explained answers linked to its workflow, plus a complete
   standalone Solution. Programming tasks follow
   [coding](../prepare-exercises/references/coding.md).
6. **Practice** ([forecast](references/forecast.md)). Make every in-scope past paper
   replayable by default (statement and solution; a solution you wrote is labelled as
   yours), with task-specific `guidance.steps`; a generic “solve the question” step
   is not guidance. Missing guides for current classified paper questions hold the
   draft gate before review. A listed paper students cannot practise holds the gate. Where a
   question's answer is computable, its answer key in `.tum-mcp/checks/` computes the
   forecast variants' answers too; write forecast exams to the real exam's blueprint from
   `exam-report --section blueprint`, as genuine variants or untested core ideas.
   Every question you write shows its figure, code, diagram, UML diagram, formula, table or
   plot beside the text, and reads as in [writing](../prepare-study/references/writing.md).
7. **Build and verify** ([verification](references/verification.md)). Edit each item's
   own file and preserve unrelated items; plan patterns (their cases) before writing and
   lint each with `tum-mcp study lint PROJECT --item exam/pattern/KEY`; after editing
   cheatsheet entries lint the sheet with `--item exam/sheet`. Build once per
   coherent batch, review `exam-report --section targets`, finish Phase A of the
   [draft checks](../prepare-study/references/loop.md), run
   `tum-mcp study visuals PROJECT --exam` and `--interact`, and fix what they report. Solutions
   answer each part once, labelled, in the form the part asks for. When a question needs
   knowledge Study lacks, record it in the [coverage ledger](../prepare-study/references/coverage.md).
   Cheatsheet facts taught in the requested prepared Study need a corresponding
   flashcard or question for Revision. For Exam topics beyond that Study scope,
   judge retrieval through the prepared Exam practice; do not add unrequested Study
   units to clear a review check. The review loop ([review-course](../review-course/SKILL.md))
   checks the cheatsheet, each pattern and each mock question with their profiles.
   Finish the complete requested draft and internal checks, then ask whether to run
   one review-and-repair round. Skip this question when review was already requested.
8. **Report** sittings, questions and their coverage, review items, kept outliers with
   reasons, gaps and checks actually run. Launch with `tum-mcp study`.

## Judgment

Targets such as entry length, workflow length, map size and blueprint fit are
guidance. `exam-report` flags outliers; keep one only when the content needs it and
say why. Hard rules are enforced by the schema: resolvable references, one document
per sitting, acyclic prerequisites, truthful labels and consistent marking.

## Boundaries

Never call a forecast a prediction, a leak or official; frequencies are history.
Student solutions are unverified; official labels need an official source. Solve every
answer independently. Never start, submit or execute course code, read `.git/` or
credentials, or copy campus or imported material anywhere public. Exam never
replaces Study; link to its units when they exist.
