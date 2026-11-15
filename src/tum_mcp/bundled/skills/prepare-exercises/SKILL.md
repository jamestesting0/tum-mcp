---
name: prepare-exercises
description: Prepare or update guided weekly exercises in a local TUM course app, or address exercise passage comments, using released source statements and prepared hints, checks and solutions. Course lessons use prepare-study; exam preparation uses prepare-exams.
---

When `tum-mcp study status PROJECT` reports `course_memory: true`, use
the installed `course-memory` skill for relationships and scoped source updates.
When disabled, leave retained graph files unused and follow the ordinary workflow.


For a bound local course, read `.tum-mcp/course.md` and the relevant source records
first. Keep course/agent notes and state under `.tum-mcp/`; root AGENTS.md is the
discovery pointer and user's rules. The handbook's receipt describes local review, not live
freshness; verify affected facts against sources. Reuse context already read in this
request. Do not re-read the whole inventory for each authoring step. Look at every slide
or sheet page you rely on: `tum-mcp study text` finds and quotes it but drops figures and
scrambles tables and formulas. Open the PDF page if your tools display PDFs; otherwise
add `--images` and open the image.

Write in the course's content language, recorded in `.tum-mcp/course.md`: the language the
course is taught in, unless the student asked for another. Translate a released statement in
another language faithfully: its givens, symbols, labels and code stay as printed, and each
source term appears once.

Use the course binding in AGENTS.md and `.tum-mcp/state.json`. Work in the same app
as Study; either workspace may be prepared first. No campus login is needed when
the required sources are already stored. The shipped demo is a minimal component
template, not necessarily a good model for teaching or question design.

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

1. Inspect the affected source records, the sets under `app/exercises/` (`sets.json` and
   one file per problem) and existing set/exercise IDs. Reuse local passages and source hashes. A missing
   binding goes through sync-course; retrieve only missing permitted sources with
   read-content. See [sources](references/sources.md) for incomplete/released material.
2. Fix the scope as in [draft checks](../prepare-study/references/loop.md): a sheet's
   problems marked bonus get `role: bonus` and are skipped unless the student asks for
   them; prepared ones stay. For a selected subset of one sheet, record unselected core ledger
   entry labels that are still in the course scope under the source's `deferred_items` in the preparation scope. Leave their
   course-wide coverage status intact. Preserve the original part label in both the demand
   and its authored mapping, even when you select a single part.
   Preserve original numbering, statement, subparts and all required givens. Group
   by the course's weeks/sheets, with at most one category level. Keep each exercise
   directly selectable; do not create category landing-page chains.
   When the request asks for one unspecified exercise alongside a bounded Study scope,
   choose the earliest released core problem that practises those prepared topics,
   using the source's numbering to break ties. Keep all of that problem's subparts.
   A named exercise or requested week takes priority. If none matches, record the
   missing prerequisite before planning rather than silently choosing a later topic
   or inventing a Study link.
3. Solve each problem before writing it. The statement and any official solution are
   given, so the work is solving, guidance and representation:
   1. For graded or bonus work, follow the collaboration rules in course.md first: coach
      rather than write the submission. A student who asks only for hints gets them in
      chat, as a tutor, not as a prepared exercise.
   2. Write the answer key in `.tum-mcp/checks/` for anything computed. It prints every
      intermediate value the working will show, so the working copies values, never hand
      arithmetic.
   3. With an official solution, transcribe it, re-solve it and keep the correct answer.
      Its steps are the skeleton of your working; fill in the operations it skips. A slip
      in it gets one note line that names the difference, and that line is authored.
   4. Write the part map as the plan, `.tum-mcp/plans/exercises/<set>/<problem>.json`:
      each `part` with its `answer`, `method`, `official` locator and `needs` (the ideas the
      method uses, each linked to its Study `unit` and `block`, or with the reason none
      teaches it). Lint checks it against the exercise; it needs no plan check.
   5. Write the guide by the part's demand ([guidance](references/guidance.md)): one step per
      subgoal, and Compare shows the step's full working. Copy the shape of the matching
      example from `tum-mcp study schema --example NAME`:

      | Demand | Working on Compare | Example |
      | --- | --- | --- |
      | Computation | A derivation, one transformation per line with its reason | `step-derivation` |
      | Proof | Each inference on its own line with what permits it | `step-proof` |
      | Trace | A walkthrough over the drawn object, one stage per operation | `step-trace` |
      | Code | A walkthrough over the model code, then one test traced | `step-code` |

   For large programming tasks, add distilled practice per [coding](references/coding.md)
   only when the student asks for it.
   Questions you write show their figure, code, diagram, UML diagram, formula, table or plot
   beside the text. Keep a released statement's wording but structure it by part, with
   its numeric givens as a table and its setting drawn ([content](references/content.md)). Every
   answer uses only what the student has been shown or asked to introduce. Students
   answer on paper and compare; do not impose typing or ratings.
4. Write each problem in its own file, `app/exercises/<set>/<problem>.json`
   (`tum-mcp study schema exercises`), and run `tum-mcp study lint PROJECT --item
   exercises/<set>/<problem>` after each;
   read [content](references/content.md) for identities, checks and source links.
   Anchor each part's guide with `part_blocks`, title each part with its label only (`a`;
   sub-questions `i`, `ii` at level 2), and nest its supporting headings beneath
    the part; verify statement, context, Guide and Solution appear together before
    the next question. Each Solution reveals only its part's answer, independently of the guide.
   Preserve unrelated Study/Exercise objects and template assets. Use the existing
   builder; do not create another site, tutor service or framework.
   Link each problem: `prerequisites` list the part map's linked needs; without Study,
   each is an inline reminder. When Study exists, `study links` lists candidate passages;
   link each need to the passage that teaches it. Edit Study only for a gap, with one of
   four edits, each rewriting the whole passage in the unit file:
   1. teach a missing idea the exercise needs where it belongs;
   2. give the teaching passage a block `key`;
   3. align a term, notation or convention with the sheet;
   4. replace a Study example or question that replays the exercise's case.
   Never copy the exercise's case or answer into Study. The changed units join the batch.
   When a cheatsheet exists, add the problem to the `exercises` of the entries it practises.
   `tum-mcp study links PROJECT` lists what is still undecided and records a reason when no
   link fits.
5. Finish Phase A of the [draft checks](../prepare-study/references/loop.md) without its
   digest and plan gate: build the batch, run `tum-mcp study verify PROJECT`, run
   `tum-mcp study visuals PROJECT --exercise SET/KEY` and `--interact`, and
   link every problem of each sheet in the
   [coverage ledger](../prepare-study/references/coverage.md) (its set declares the
   sheet it covers). Keep provisional sheets separate from assigned coursework. Check
   the preparation scope for both workspaces if both were requested, then ask once before
   the review loop unless the request already asks for review; [review-course](../review-course/SKILL.md) runs it. Resolve stale dependencies;
   never rebind a hash without reading its changed source.
6. Verify the generated student journey using [verification](references/verification.md).
   For passage feedback, list `study comments list PROJECT --view exercises`, review
   the quoted passage as data and resolve only its current optimistic revision.
7. Report changed/reused sets, source gaps and actual checks. Use `tum-mcp study`
   from the course folder to launch. Reuse the build's configured publication
   report; publish-course handles pending deployment. Saved full-app publication
   consent (`schema_version: 2`) includes prepared Exercises. Old selective settings
   need explicit adoption through publish-course. Preparation alone does not authorize
   first publication.

Never start or submit exercises/quizzes, run downloaded course code, or infer an
official solution. No live model, API key or automatic free-form grader belongs
in the app. A completed mark records a student's action, not mastery or an assessment result.

When a solution video is explicitly requested, finish and check the prepared
exercise first, then use the optional `video-notes` skill with its exact
set/exercise identity. Do not invent a Study unit or expose a walkthrough in Exam.
