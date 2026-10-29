---
name: prepare-exams
description: Prepare a local Exam Prep workspace for a TUM course from its past exams, exercises and materials - a cheatsheet with a semester map, recurring exam patterns with solving workflows, guided past papers and forecast practice exams. Lessons use prepare-study; weekly sheets use prepare-exercises.
---

For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. The handbook's receipt describes local review,
not live freshness; verify affected facts against sources. Reuse context already
read in this request. Do not re-read the whole inventory for each authoring step.

You author `app/exam.json` (`study schema exam`); `tum-mcp study build PROJECT`
renders it as the Exam Prep workspace beside Study and Exercises. Code derives every
count, rate, order, map position and blueprint; the schema has no count fields.
Exam Prep stays local: it is never published and publish-course never includes it.

## Workflow

1. **Scope.** Read the handbook's assessment section, then
   `tum-mcp study exam-report PROJECT`. A missing binding goes through sync-course.
   If past exams are missing, ask once: the user may sync them, import files they hold
   with `tum-mcp study import PROJECT --file F --kind exam --title T`. Prepare what
   the evidence supports; report the rest.
2. **Evidence** ([sources](references/sources.md)). Weigh official rules and exams
   above student copies; keep conflicts visible. Read text with
   `tum-mcp study text PROJECT --key K --pages N-M`; view pages only for scans,
   figures and formulas. Read each document once, even when several copies exist.
3. **Registry** ([patterns](references/patterns.md)). One sitting per real exam;
   attach every copy of it as roles of one variant. Extract every subquestion and
   classify it by transferable solving strategy, reusing existing patterns first.
4. **Cheatsheet** ([cheatsheet](references/cheatsheet.md)). Keep only what earns
   exam points; write the one line first, put the rest behind Expand, and link the
   ideas that genuinely depend on or contrast with each other.
5. **Patterns.** A short workflow that solves every member, recognition cues from the
   question text, an answer template, marking points, pitfalls, a worked practice
   that applies every workflow step in turn, and a drill. Programming tasks follow
   [coding](../prepare-exercises/references/coding.md).
6. **Practice** ([forecast](references/forecast.md)). Make chosen past papers
   replayable with guidance; write forecast exams to the real exam's blueprint from
   `exam-report --section blueprint`, as genuine variants or untested core ideas.
   Every question you write shows its code, diagram, UML diagram, formula, table or plot beside
   the text.
7. **Build and verify** ([verification](references/verification.md)). Edit
   `exam.json` programmatically by key and preserve unrelated items. Build once per
   coherent batch, review `exam-report --section targets`, then check the app.
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
credentials, or copy campus or imported material anywhere public. Exam Prep never
replaces Study; link to its units when they exist.
