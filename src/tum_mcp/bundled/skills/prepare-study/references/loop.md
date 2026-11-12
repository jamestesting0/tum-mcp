# Draft, check, then the review loop

Shared by prepare-study, prepare-exercises, prepare-exams and prepare-lecture. Authoring
(Phase A) ends with a draft that passes every code check; the review loop (Phase B,
review-course) has fresh checkers read it. The session that wrote an item never scores it.

## Phase A: draft and check

1. **Fix the scope once.** From the request, the coverage ledger
   (`tum-mcp study report PROJECT --section coverage`) and `tum-mcp study schedule PROJECT`
   ("this week" and what has been taught). Bonus problems are out unless the student asks
   for them; prepared ones stay and are reviewed. Material released while you work waits
   for the next round of work. For Study or Exercises, write
   `.tum-mcp/preparation/ID.json` using `tum-mcp study schema preparation`.
   Account for all relevant inventory through the cutoff, including the first lecture,
   or name a bounded selection and its exclusions. Keep teaching dates, release dates
   and reports of a session distinct. Put future semester outcomes in the roadmap.
   Record each required outcome clause or exercise demand and its source locator first.
   A tracked campus source still marked `needs_fetch` keeps its key: download it with
   read-content, then `study sync` a partial snapshot holding only that resource with its
   `source_file` ([snapshot contract](../../sync-course/references/project.md)).
   `study import` is for files only the student holds; importing a campus download
   creates an untracked private duplicate.
   For each preparation request, write `.tum-mcp/batches/ID.json`
   (`study schema batch`) with the original request, every planned item key (including
   each forecast question as `exam/mock/MOCK/QUESTION`) and
   the Study/Exercise preparation IDs. A Lecture output names `lecture/LECTURE_KEY`;
   its notes and highlights join the batch automatically. Use the batch as the
   checklist and continue through local authoring and repair until every output is ready.
   Register it immediately with `study task start PROJECT --batch ID`. Its default
   ends at a complete draft and a review invitation. Only when review was already
   requested, add `--review-rounds N` using its authorized total budget (default one).
   The enabled host completion hook continues this registered task after a premature
   stop. Use the hook context's `--owner HOST:ID` on task start, finish and pause. It never authorizes review. Honor a user pause or a concrete external blocker
   with `study task pause PROJECT --reason REASON` and report the evidence.
   A missing date, unavailable source or provisional sheet may leave the original
   cutoff unresolved even while a selected subset is ready.
2. **Read each source once into a digest.** `.tum-mcp/digests/<source>.json` holds its
   stated outcomes, worked examples, definitions and figures with their pages, and the
   source's `sha256` from `.tum-mcp/state.json`. Record each worked demonstration once:
   its pages, what it shows and its inputs. Scan the text to find them and open the pages
   of the ones you teach; plans choose from this list
   ([planning](planning.md#choose-the-lectures-examples)). `tum-mcp study digests PROJECT` lists
   missing and stale ones. Plans, authors and checkers read the digest instead of the
   whole source; open the source pages for anything the digest does not settle.
3. **Check coverage before drafting.** Run
   `study report PROJECT --section coverage-plan --preparation ID`. This validates
   source inventory, outcomes, original sheet parts and planned targets without reading
   authored content. Resolve every gap first. Each target's reason names what the
   student must do and the result they must produce, including every source clause.
   Do not replace a complete procedure with its first step or omit a promised result.
   **Plan every item.** `.tum-mcp/plans/<item>.json` (for example `plans/study/dfs.json`)
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
   Study/Exercise plans name their source scope as `preparation: "ID"`. The existing
   plan checker reads its requirements first; approval binds their fingerprint.
   Changing requirements later requires a new plan check, not silently smaller coverage.
   For Study application/reasoning, include solved `practice` cases contrasting the
   worked example with a meaningful new condition or decision (see planning.md).
   For a bounded mixed batch, prepare all requested Study, Exercise and Exam plans
   before one fresh plan check. The checker holds when a declared batch still lacks
   plans; do not call it after each individual pattern. Fix rejected plans together;
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
   plans before writing.
   Read the complete batch locally before this call and fix all detectable omissions
   together. Do not request independent checks of unchanged approved plans. Changing
   only an artifact key elsewhere in the batch does not change the source requirements.
5. **Solve first.** For anything computed (a trace, a result, a mock question), write the
   answer key `.tum-mcp/checks/<item>.py` before the item: it prints
   `{"values": {path: value}, "walkthroughs": {block: [state per step]}}` and
   `tum-mcp study verify PROJECT` compares it with the content on every check.
   Reuse the solved plan instances and preserve their calculations in this key;
   solving the same case again is unnecessary unless the input or method changed.
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
   checker's waiver cannot clear them. The flags marked for a ruling (inline lists,
   a shorter definition than the course's, a lesson without a visual) are ruled on
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
   **Check the batch.** `tum-mcp study build PROJECT`, `tum-mcp study visuals PROJECT`
   (desktop; fix every render defect in the content) and
   `tum-mcp study visuals PROJECT --interact` (learner controls and formula layout).
   A clipped equation or a scrollbar on the equation itself fails the interaction
   receipt. Use the reported route, width and learning state to reproduce it.
   Contact sheets cover drawings and tables. Open equations, derivations and code
   in the built app to inspect readability and the quality of the working.
8. **Check the whole requested draft before asking.** Fill the scope's teaching,
   practice and answer mappings. Check that each learner action actually exercises
   the recorded demand, and that the outline and introductory copy agree. Persist
   executable answer keys for computed demands, including results first checked in scratch work.
   Build and run `tum-mcp study visuals PROJECT --phone` and
   `tum-mcp study visuals PROJECT --interact --phone`. Narrow both invocations with the
   same `--unit` and `--exercise` selectors for a bounded scope. Read
   `tum-mcp study report PROJECT --section readiness --preparation ID`.
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

review-course drives `tum-mcp review`: fresh checkers read packets, the maker fixes by
check, code re-runs the checks above, and the gate passes when correctness and coverage are
3, every teaching check passes and the rest are at least 2 with a kept reason. Publishing
reads the same gate.
