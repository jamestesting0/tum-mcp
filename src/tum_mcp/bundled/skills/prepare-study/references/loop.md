# Draft, check, then the review loop

Shared by prepare-study, prepare-exercises, prepare-exams and prepare-lecture. Authoring
(Phase A) ends with a draft that passes every code check; the review loop (Phase B,
review-course) has fresh checkers read it. The session that wrote an item never scores it.

## Phase A: draft and check

1. **Fix the scope once.**

   1. Read the request, coverage ledger and schedule. Include relevant inventory through
      the cutoff, including the first lecture, or name a bounded selection and exclusions.
      Bonus problems are out unless requested; prepared ones stay and are reviewed.
      Material released during work waits for the next round. Keep teaching dates, release
      dates and session reports distinct. Put future semester outcomes in the roadmap.
   2. For Study or Exercises, write `.tum-mcp/preparation/ID.json`. Record every required
      outcome clause or exercise demand and source locator. A missing date, unavailable source
      or provisional sheet may leave the original cutoff unresolved even if a subset is ready.
   3. A tracked campus source marked `needs_fetch` keeps its key. Download with read-content,
      then sync a partial snapshot holding only that resource with its `source_file`
      ([snapshot contract](../../sync-course/references/project.md)). Import is for files only
      the student holds; importing a campus download creates an untracked private duplicate.
   4. Write `.tum-mcp/batches/ID.json` with the original request, every item key and the
      Study/Exercise preparation IDs. Each forecast question is `exam/mock/MOCK/QUESTION`.
      A Lecture output names `lecture/LECTURE_KEY`; its notes and highlights join automatically.
      Use the batch as the checklist until every output is ready.
   5. Register it immediately. The default task ends at a complete draft and review invitation.
      Only if review was already requested, add `--review-rounds N` for its authorized total
      budget (default one). The completion hook continues a prematurely stopped task; it
      never authorizes review. Use the hook context's `--owner HOST:ID` on start, finish and
      pause. Honor a user pause or concrete external blocker with `study task pause PROJECT
      --reason REASON` and report the evidence.

   | Purpose | Command |
   | --- | --- |
   | Coverage and schedule | `tum-mcp study report PROJECT --section coverage`; `tum-mcp study schedule PROJECT` |
   | File schemas | `tum-mcp study schema batch`; `tum-mcp study schema preparation` |
   | Start a batch | `tum-mcp study task start PROJECT --batch ID` |
   | Block example | `tum-mcp study schema --example KIND` (`--example list` lists names) |

   Gotchas: The batch ID is the filename without `.json`, never free text. Write JSON files
   with the edit tool, not shell heredocs. `study lint PROJECT` without `--item` checks all
   items. Readiness prints a summary; add `--json` for the full result.

   Example `.tum-mcp/batches/search.json`:

   ```json
   {"course_key":"ai","request":"Study search.","items":["study/search"],"preparations":["search"]}
   ```

   Example `.tum-mcp/preparation/search.json`:

   ```json
   {
     "course_key":"ai", "semester":"winter", "workspaces":["study"],
     "mode":"selected_sources",
     "inventory":[{"source":"search-slides","disposition":"required","basis":"source",
       "reason":"The requested lecture.","locator":"pages 1-20"}],
     "demands":[{"id":"trace","source":"search-slides","kind":"study",
       "text":"Trace breadth-first search.","locator":"pages 10-12",
       "outcome":"trace-search","level":"apply"}]
   }
   ```
2. **Read each source once into a digest.** `.tum-mcp/digests/<source>.json` holds its
   stated outcomes, worked examples, definitions and figures with their pages, and the
   source's `sha256` from `.tum-mcp/state.json`. Record each worked demonstration once:
   its pages, what it shows and its inputs. Scan the text to find them and open the pages
   of the ones you teach; plans choose from this list
   ([planning](planning.md#choose-the-lectures-examples)). `tum-mcp study digests PROJECT`
   lists missing and stale ones. Plans, authors and checkers read the digest instead of the
   whole source; open the source pages for anything the digest does not settle.
3. **Check coverage before drafting.**

   1. Run `study report PROJECT --section coverage-plan --preparation ID`. It validates
      source inventory, outcomes, original sheet parts and targets without authored content.
      Resolve gaps first. Each target's reason names the action and result, including every
      source clause. Do not replace a complete procedure with its first step or omit a result.
   2. **Plan every item.** `.tum-mcp/plans/<item>.json` (for example `plans/study/dfs.json`)
   names the item's outcomes and each concept with its `kind` (definition, fact, rule,
   procedure, algorithm, model, comparison, cases), the worked `instance` that shows it
   (for a procedure, algorithm or model, the lecture `example` it is taught on) and the
   block keys that will teach it; an exercise plan names each `part` with its `answer`
   and `method`. A kind brings a default shape (an algorithm is stepped through, a
   comparison is a table, a model is drawn, parallel `cases` are a table or one `example`
   each); give `skip` with the reason when it does not fit. Choose the kind from the idea:
   a comparison sets several things side by side on shared attributes, so an argument or
   two options told in a sentence each is a `rule` or `fact`, not a table that repeats the
   text beside it. Read
   `tum-mcp review checklist --profile PROFILE` first: author and checker read the same
   checks, and the checklist points to a gate-passing exemplar of that kind of item (with
   its plan and answer key for a Study unit). Copy its shape, not its sentences.
   3. Study/Exercise plans name their source scope as `preparation: "ID"`. The existing
   plan checker reads its requirements first; approval binds their fingerprint.
   Changing requirements later requires a new plan check, not silently smaller coverage.
   4. For Study application/reasoning, include solved `practice` cases contrasting the
   worked example with a meaningful new condition or decision (see planning.md).
   For every bounded batch, including Study lessons alone, prepare all requested plans
   before one fresh plan check. The checker holds when a declared batch still lacks
   plans; do not call it after each individual lesson or pattern. Fix rejected plans together;
   do not launch a checker
   when `review plans PROJECT` lists no pending plans.
4. **Pass the plan gate.** `tum-mcp review plans PROJECT` gives the plans waiting for a
   check, and one fresh session reads them: `tum-mcp review run-checker PROJECT --plans`
   (a headless host session, recorded as fresh), or a subagent that starts empty, whose answer
   you record with `tum-mcp review plan-record PROJECT --file ANSWER --provenance fresh`.
   A forked agent (Codex `spawn_agent`) replays this conversation and is not fresh; record
   its answer as `same` or use run-checker. Read only this batch
   with `tum-mcp review plans PROJECT --item ITEM` (repeat `--item`). Checking your own
   plans records them as provisional. For Study or Exercises in a single-agent run, or
   when an independent checker is unavailable, read the complete scoped packet and
   record your actual verdicts from its `answer.items` template with
   `tum-mcp review plan-record PROJECT --file ANSWER --provenance same`. A passing
   same-author verdict can complete draft readiness. It does not replace independent
   review or a current independent verdict. Check changed plans again and repair rejected
   plans before writing. A checker fails a plan only for a blocking problem; its `advice`
   comes with a pass. Apply useful advice in the lesson itself, not in the approved plan:
   any plan edit changes its fingerprint and needs a new check. Fix each failing reason
   completely in one revision, including every part the reason names.
   Read the complete batch locally before this call and fix all detectable omissions
   together. Do not request independent checks of unchanged approved plans. Changing
   only an artifact key elsewhere in the batch does not change the source requirements.
5. **Solve first.** For a computed trace, result or mock question, write
   `.tum-mcp/checks/<item>.py` before the item. `study verify PROJECT` runs it and
   compares its JSON with the content. Reuse solved plan instances unless the input or
   method changed.

   Each walkthrough has a `primary` run and a `variant` when authored. Each run has one
   object per step, with every state row exactly once and `@node_values` for computed node
   values. Each step is a full snapshot. `values` maps content paths to expected values.
   For example, adapt the paths, block key and computed inputs to the lesson:

   ```python
   import json


   def run(start):
       return [
           {"Frontier": start, "@node_values": {start.lower(): "0"}},
           {"Frontier": "G", "@node_values": {start.lower(): "0", "g": "1"}},
       ]


   print(
       json.dumps(
           {
               "values": {"blocks[0].result": 1},
               "walkthroughs": {"trace": {"primary": run("S"), "variant": run("A")}},
           }
       )
   )
   ```
6. **Write each item, then lint it.** Edit the item's own file under `app/` with your edit
   tools (no scripts that rewrite whole workspaces). Write each question's context, options
   and feedback for that question: a helper that fills one template across questions gives
   every wrong option the same feedback and wraps sentences in one-row tables. While its
   source and plan are fresh, follow the published procedure on the worked input and a
   relevant boundary case; check the actual loop scope, branches and exits, not an
   independent hidden implementation.
   Read an exercise's Solution alone and keep its working self-contained. Repair these
   gaps in this item before moving to the next. After each item run
   `tum-mcp study lint PROJECT --item ITEM`: schema, report flags, the plan's links and the
   answer key in seconds. Fix every invariant flag; read every other flag and fix it or
   keep it for a stated reason. Text-only questions are invariant defects; even a
   checker's waiver cannot clear them. Fix `dropped_node_value`, `repeated_step_reason`
   and `never_shown_nodes`. Flags for a ruling include
   `duplicate_stage`, `untitled_opening`, `trace_as_table`,
   `repeated_example`, inline lists, a shorter definition than the course's, and a lesson
   without a visual. Two runs on one drawing stay when each is the lecture's run of a
   different mechanism. Flags for a ruling are ruled on
   again by the checkers, and the gate holds until each has a ruling.
7. **Read the assembled draft once before browser checks.** Check prerequisites and
   Recall links against the content actually prepared, and consistency across items.
   **Link across workspaces.** `tum-mcp study links PROJECT` lists every exercise,
   cheatsheet entry, lecture note and unit without a link to a workspace that exists, with
   candidate passages. Link each in its content (exercise `prerequisites`, concept `units` or
   `passages`, note `passage`, unit `lectures`), or record why none fits with `--none ITEM
   --target TARGET --reason TEXT`. New lessons reopen earlier "none" decisions; readiness
   waits until every one is decided.
   Check the finished procedure's successful return/stop and unsuccessful exit literally;
   a correct worked trace does not repair an incomplete published instruction. Compare
   each planned practice contrast against the finished worked sections, including their
   continuations: keep assessment cases reserved, and replace any case the lesson consumed.
   Reuse the per-item dry runs unless an assembly change affects them. This is the
   author's polish pass, not another formal review round.
   On a new site only, run `study visuals PROJECT --unit UNIT` for its first lesson.
8. **Check the whole requested draft before asking.** Fill the scope's teaching,
   practice and answer mappings. Check that each learner action actually exercises
   the recorded demand, and that the outline and introductory copy agree. Persist
   executable answer keys for computed demands, including results first checked in scratch work.
   Run `tum-mcp study lint PROJECT` once for the whole batch, then build and run
   `tum-mcp study visuals PROJECT` and
   `tum-mcp study visuals PROJECT --interact`, narrowed with the same `--unit` and
   `--exercise` selectors for a bounded scope. Desktop is the check; add `--phone` only
   when the student asks about phones. `study visuals` redraws only items changed since
   their last passing check (`unchanged` lists the rest), so rerun it after a fix.
   Fix every render defect. A clipped equation or scrollbar on the equation fails the
   interaction receipt; use its route, width and state to reproduce it. Contact sheets
   cover drawings and tables. Open equations, derivations and code in the built app to
   inspect readability and working. Read
   `tum-mcp study report PROJECT --section readiness --preparation ID` (add `--json`
   for the full result).
   Resolve required gaps before asking for formal review. Name the verified cutoff or
   selected subset, the workload and any excluded or unresolved sources, then ask:
   Ask whether to run one review round, using the student's terms; do not cite skill
   files or workflow rules to the student. Report the findings,
   fixes and any remaining verification when it ends. Extend the budget only if requested. Skip the question when the request already asks for a review,
   and do not ask again in the same session once the student has answered.
   For a multi-workspace request, run
   `study report PROJECT --section readiness --batch ID` and repair every reported
   gap before `review start PROJECT --batch ID`. Keep drafting and fixing local
   problems until this gate passes. If access or a missing source prevents completion,
   report that precise blocked requirement and preserve the ready work.
   An unfinished comparison, a lint failure or stale browser evidence is pending local
   work. Continue it and complete independent requirements before ending the task.
   Read readiness before any final response. When it is false and tools remain usable,
   execute its next action and continue. A partial progress summary does not complete
   preparation. Within this one user request, keep the checklist across context changes.
   Before the final report run `study task finish PROJECT`: it checks the whole draft
   and any already authorized review. If refused, continue its pending work.

## Phase B: the review loop

For a ready Study or Exercises scope, start `tum-mcp review start PROJECT --preparation ID`.
Use ordinary workspace filters for an ad hoc review. Keep author-only findings provisional.
At handoff, reconcile the handbook and final summary with the scope report, including
provisional sheets and unknown lecture dates. Give counts for checked computations,
browser routes and reviewed items separately. For an already-running local preview,
compare its served `data.mjs` with this project's build before linking the stable origin.

Finish all original findings and draft repairs before `review verify`. After that pass,
repair only findings it opened and report those repairs as unverified. Another independent
check needs another round requested by the student; stale verdicts do not carry forward.

review-course drives `tum-mcp review`: fresh checkers read packets, the maker fixes by
check, code re-runs the checks above, and the gate passes when correctness and coverage are
3, every teaching check passes and the rest are at least 2 with a kept reason. Publishing
reads the same gate.
