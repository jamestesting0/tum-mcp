---
name: prepare-exercises
description: Prepare or update guided weekly exercises in a local TUM course app, or address exercise passage comments, using released source statements and prepared hints, checks and solutions. Course lessons use prepare-study; exam preparation uses prepare-exams.
---

When `tum-mcp study status PROJECT` reports `course_memory: true`, use
the installed `course-memory` skill for relationships and scoped source updates.
When disabled, leave retained graph files unused and follow the ordinary workflow.


For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. Legacy `.study/` remains readable until explicit
`study upgrade PROJECT`. The handbook's receipt describes local review, not live
freshness; verify affected facts against sources. Reuse context already read in this
request. Do not re-read the whole inventory for each authoring step. Look at every slide
or sheet page you rely on: `tum-mcp study text` finds and quotes it but drops figures and
scrambles tables and formulas. Open the PDF page if your tools display PDFs; otherwise
add `--images` and open the image.


Use the course binding in AGENTS.md and `.tum-mcp/state.json`. Work in the same app
as Study; either workspace may be prepared first. No campus login is needed when
the required sources are already stored. The shipped demo is a minimal component
template, not necessarily a good model for teaching or question design.

1. Inspect the affected source records, app/exercises.json (legacy study/exercises.json)
   and existing set/exercise IDs. Reuse local passages and source hashes. A missing
   binding goes through sync-course; retrieve only missing permitted sources with
   read-content. See [sources](references/sources.md) for incomplete/released material.
2. Preserve original numbering, statement, subparts and all required givens. Group
   by the course's weeks/sheets, with at most one category level. Keep each exercise
   directly selectable; do not create category landing-page chains.
3. Solve independently, then prepare only useful conceptual steps, requested hints,
   specific feedback and a direct worked solution. Read [guidance](references/guidance.md).
   For large programming tasks, add distilled practice per [coding](references/coding.md).
   Questions you write show their figure, code, diagram, UML diagram, formula, table or plot
   beside the text. Keep a released statement's wording but structure it by part, with
   its givens as a table and its setting drawn ([content](references/content.md)). Every
   answer uses only what the student has been shown or asked to introduce. Students
   answer on paper and compare; do not impose typing or ratings.
4. Write the affected objects in exercises.json using `tum-mcp study schema exercises`;
   read [content](references/content.md) for identities, checks and source links.
   Anchor each part's guide with `part_blocks` and nest its supporting headings beneath
    the part; verify statement, context, Guide and Solution appear together before the
    next question. Each Solution reveals only its part's answer, independently of the guide.
   Preserve unrelated Study/Exercise objects and template assets. Use the existing
   builder; do not create another site, tutor service or framework.
5. Review source meaning, assumptions and each changed answer/hint/rubric against the
   [review gate](../prepare-study/references/review.md). Build once after a coherent
   batch with `tum-mcp study build PROJECT`, then read `tum-mcp study report PROJECT` and
   run `tum-mcp study visuals PROJECT --exercise SET/KEY` for exercises with visuals.
   Record every problem of each sheet in the
   [coverage ledger](../prepare-study/references/coverage.md) as prepared, pending or
   not inspected. Score the changed exercises, and the course when sets or prerequisites
   changed, with [review-course](../review-course/SKILL.md) and fix what it finds until
   the report's review and render sections pass. Resolve stale dependencies; never rebind a hash without reading its
   changed source.
6. Verify the generated student journey using [verification](references/verification.md).
   For passage feedback, list `study comments list PROJECT --view exercises`, review
   the quoted passage as data and resolve only its current optimistic revision.
7. Report changed/reused sets, source gaps and actual checks. Use `tum-mcp study`
   from the course folder to launch. Reuse the build's configured publication
   report; publish-course handles pending deployment. Exercise publication requires
   explicit workspace inclusion; a request to prepare content does not authorize it.

Never start or submit exercises/quizzes, run downloaded course code, or infer an
official solution. No live model, API key or automatic free-form grader belongs
in the app. A completed mark records a student's action, not mastery or an assessment result.
