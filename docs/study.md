# Course study projects

Six base skills cover source reading, course sync, Study preparation, Exercises
preparation, exam preparation and publishing. They run in your local agent, using the connected
MCP tools to read course sources. The CLI validates and stores the resulting local
files; it does not run an AI model.
The optional `prepare-lecture` skill adds a Lecture workspace; install it with
`tum-mcp install lecture`. See [Lecture](lecture-notes.md).
The optional `audio-notes` skill turns prepared lessons into spoken tracks; install
it with `tum-mcp install audio-notes`. The optional `video-notes` skill turns prepared
topics into depth-first visual explanations and selected Exercises into solution
walkthroughs; install it with `tum-mcp install video-notes`.

## Start with one course

Use `sync-course` for both initial setup and later source updates. For a new project,
provide the course title and semester when known. The agent verifies
its availability, resolves source IDs and asks about ambiguous mappings. A project
cannot switch course or semester. Use a separate directory for another course.

```text
Initialize ./pse-ws26 for Patterns in Software Engineering (WS26/27).
Use its available Artemis teaching material and record any missing sources.
```

The agent inventories Moodle materials, announcements and forums; Artemis
lectures, learning units, student slides and statements; and mapped Zulip course
discussions. It reads only enabled sources. An unavailable login or partially
retrieved source is recorded as a gap rather than an empty course.

```text
pse-ws26/
  AGENTS.md                 Managed agent guide, then your own rules
  materials/
    content/                Lectures, slides and reading
    exams/                  Available revision material
    exercises/              Released statements and practice references
    other/                  Announcements and course information
  .tum-mcp/
    course.md               Cited course structure, logistics, rules and unknowns
    state.json              Course binding, source versions and coverage
    notes/                  Detailed course/agent notes when needed
  app/                      Shared Study, Exercises, Exam and optional Lecture website
    study/                  Study index and one file per unit
    exercises/              Exercise-set index and one file per problem
    exam/                   Exam index, concepts and patterns
    lectures/               Optional Lecture index and entries
  audio/                    Optional category audio derived from the prepared website
  videos/                   Optional explainer videos derived from the prepared website
```

`AGENTS.md` starts with a managed agent guide; keep your own rules and standing
preferences outside it. The guide tells the agent that it works for a student of this
course, which skill handles which kind of request, how to read short requests such as
"this week" or "the exam", where each kind of course information lives, and how to
answer as a tutor: from the course's own sources and notation, with the next step
before a full solution. `study sync` replaces an outdated guide and
keeps the rest of the file; an edited guide is kept and reported for review.

The guide sends the agent to `.tum-mcp/course.md` first. That short handbook explains
the course's goals, lectures/tutorials, weekly work and platforms, assessment/bonus
conditions, conventions (textbook, notation, answer format), communication and
preparation map. Claims carry source
links/locators and checked dates; unknowns and conflicting announcements stay visible.
Detailed source content remains in materials/. All TUM MCP course state, plans and
agent notes live under .tum-mcp/.

For requests spanning workspaces, the agent records the original request and expected
outputs in `.tum-mcp/batches/ID.json` (`study schema batch`) before drafting.
Forecast questions use `exam/mock/MOCK/QUESTION` item keys. A pattern batch also
checks its visible cheatsheet. Write every declared Study, Exercise and pattern plan
before launching the fresh plan checker; it checks the pending plans together.
Study and Exercise source requirements first pass
`study report PROJECT --section coverage-plan --preparation ID`, independently of
authored content. Plans name that `preparation`; their approval records its fingerprint
so later scope changes require a fresh plan check. Study and
Exercise demand mappings, approved plans, computed checks and current browser evidence
must pass `study report PROJECT --section readiness --batch ID` before the combined
`review start PROJECT --batch ID`. Missing outputs do not consume the review round.
The independent review then checks the quality and meaning of those mappings; a ready
draft is not a claim that every teaching decision is already correct.
Mixed batches also review course structure and links between their workspaces.
Content preparation stops there and asks whether to review, unless review was already
requested. Approval defaults to one review-and-repair round; its report includes scores,
repairs and unresolved verification. Score coverage identifies how many current items
have complete checks; averages over that subset are not an overall repaired-batch score.
Extra rounds require the student's request.

Before moving on from an authored item, the agent follows its published procedure
on the worked input and a relevant boundary case, and reads an Exercise solution
without its guide. A correct trace or executable answer key does not prove that
the displayed instructions include their loops, branches and exits. This author
check happens before browser readiness and the optional formal review; it adds no
review round. The assembled draft then checks prerequisites and cross-item consistency.

Packaged completion hooks enforce this stopping point in Codex, Claude Code, Cursor
and Antigravity using each host's native lifecycle. Setup installs the guard and
checks registration. Codex setup asks its runtime for the exact owned hook hashes,
records only those trust entries, then verifies them. It never enables all hooks or
changes approval/sandbox policy. Other hosts use their own hook configuration;
workspace trust and administrator settings still apply. The bridge requires Node.js,
as supplied by the npm installation. An author registers an explicit
batch with `study task start PROJECT --batch ID`; review is off unless its requested
budget is supplied with `--review-rounds`. Use the `--owner HOST:ID` supplied by
the host context when starting, finishing or pausing a task.
`study task finish PROJECT` checks current
evidence before handoff. The guard only continues a task owned by that chat. User
interruptions pause it; three continuations with no file progress stop it as stalled,
with incomplete work still reported. Completed tasks do not restart on later edits.

`sync-course` reads the relevant authoritative sources and maintains the handbook;
the CLI scaffolds it without pretending to understand the course. Its review receipt
records the local generation and hashes of supporting sources. `study inspect`
reports changed supporting sources and coverage gaps so refreshes can focus on
affected claims. A reviewed local snapshot does not establish live freshness or
complete understanding. See the bundled sync-course context reference for the full
source-review workflow.

## State-based workflow

`sync-course` starts with `tum-mcp study status PROJECT`, a read-only local check:

| Mode | Action |
| --- | --- |
| `initialize` | Verify the chosen available course, then initialize its inventory. |
| `sync` | Reuse the bound course/semester and known source IDs; check the requested changes. |
| `recover` | Inspect incomplete, damaged or conflicting local state before writing. |

Existing material without state is inspected before adoption. Damaged state and
customized instructions are preserved; they are never treated as an empty project.
The status check does not authenticate services or prove upstream freshness.
The underlying `study init` and `study sync` commands remain separate.

## Keep it current

Ask `sync-course` to compare the project with connected upstream sources. It
reuses the saved course, semester, source IDs and reliable revisions. It retrieves
changed material and updates course knowledge. Incomplete listings never imply withdrawal. Withdrawn sources
keep their local originals; edited or deleted managed files are reported for review.
Unchanged payloads can be reused when their source binding, URL, locator and
reliable revision match. Pending content stays pending across repeated checks;
a metadata-only check cannot make unfetched content current.

The agent updates course facts outside the inventory block. The helper checks
that its managed block has not been edited before replacing it. LF/CRLF
conversions are accepted, and synchronization preserves the existing line-ending style. A failed write
restores files when possible and reports any remaining conflict.

## Prepare the website

Ask `prepare-study` to create or extend the Study workspace in `app/`. The agent
writes one file per unit under `app/study/` from your stored course material, and `tum-mcp study build`
installs the shared course app and checks every cited source. Units follow the
course's lecture or week sequence when useful, or consistent topics, with at most
one category level. Every unit has:

- Content: a short lesson with objectives, source links, assumptions and worked
  examples, using formulas, tables, code, graphs, UML diagrams, flowcharts, drawn figures
  or plots where they help. Graphs keep the rows and columns the author chose; UML
  diagrams and flowcharts are laid out automatically; plots draw functions from their
  formula. On a phone a drawing shrinks only until its text reaches 12 px and scrolls
  sideways beyond that. A hard idea comes as short numbered steps instead of a long paragraph. A
  term to learn appears in bold beside its meaning, inside the section that introduces
  it; a dotted term anywhere in the app opens its definition in place. Algorithm traces
  step through one operation at a time and show the algorithm's state (a queue, the
  domains) beside the drawing, marking what changed.
- Flashcards for recall. On a keyboard, arrows move, Space flips and 1/2 rate a card.
- Practice questions with options in a stable shuffled order, an optional hint and
  feedback for every option. A question about a situation shows it (a graph, a
  drawing, a table, a formula) beside the question and states each fact once.

The agent uses stored material first, so local content edits work offline. Ask for
an upstream refresh when you want new course content; an existing check is reused
within the same request. Unchanged units and reviewed material are retained. The
skill audits objective coverage, technical accuracy and distractors, and writes in
short, direct sentences that keep necessary terms and conditions.

The course home introduces the course, resumes where you left off and lists topics
with progress. Each view ends with a Next link through cards and practice to the
next unit. Revision pools cards and questions from the topics you choose (all topics
until you choose) and can focus on cards marked Again and questions you missed. A
question you missed stays there after **Try again**; it leaves once you answer it
correctly from a fresh start. Revision reuses the original items and progress, so
changing the topic selection never clears results, and it remembers your selection
for this course. A unit's header links the Lecture, exercises and Exam
patterns that build on it. In the local preview, a citation opens the stored course
file at the cited page. Formulas and inline
notation such as `\(v_i\)` are validated at build and typeset in the browser by the
bundled KaTeX, as in Notion: TeX fonts and spacing, text-size inline vectors and
matrices, and long inline math that wraps after its relations on a phone. Screen
readers get KaTeX's MathML copy. Derivation blocks show working line by line, aligned
on the relation, and can step through it. Code and dollar signs stay literal. The app has light and dark themes and a phone layout.

Content lives in one file per item under `app/`; shared renderer modules and CSS keep the
site extensible. Source hashes identify affected units. A stale source stops a
build until the explanation is reviewed. Unchanged units retain their revision;
revised questions receive separate progress. Customized templates are preserved
and reported, so the agent must review compatibility when extending them.

```sh
tum-mcp study inspect ./pse-ws26
tum-mcp study find ./pse-ws26 "observer pattern"   # stored pages that mention every word
tum-mcp study text ./pse-ws26 --key KEY --pages 3-5 --images   # page text plus a PNG of each page
tum-mcp study build ./pse-ws26
tum-mcp study report ./pse-ws26   # review flags, the course map and what the sources leave uncovered
tum-mcp study visuals ./pse-ws26  # measure every drawn visual and draw contact sheets
```

Slide text finds and quotes a page, but it drops figures and scrambles tables and
formulas, so the agent looks at every slide or sheet page it relies on. Hosts that
display PDFs, such as Claude Code, open the page directly; for the others, such as
Codex, `study text --images` renders up to 12 pages to PNGs under `.tum-mcp/cache/`,
once per file version, without Poppler or any other system tool.

The agent records what each lecture states students should learn, and which sheet
problems are prepared, in `.tum-mcp/coverage.json`. `study report` lists outcomes
that are not yet taught, sources not yet read and problems still pending, so a request
to cover a whole course is judged against the course's own outcomes.

The Study overview shows known core gaps under **Not prepared yet**, including outcomes
that are partly prepared. Unknown source coverage and optional reading backlog stay
in the local agent report. They do not create learner-facing panels or count as prepared.
The core list updates on build after the agent reviews and updates the ledger; it does
not track the student's progress. Exercises uses the same expandable presentation for
pending sheets. Preparation queues and the full source inventory stay local;
published sites contain prepared learning content, not authoring queues.

`study visuals` opens every lesson, practice question, exercise step and Exam
visual, including exercise Solution, Compare and transfer-answer blocks, in an installed
Chrome, Edge or Chromium at desktop (1280 px) width; `--phone` adds phone (390 px) and
narrow (600 px) widths. It reports lines through nodes, labels that overlap or sit on a
line, text under 12 px, clipped text and drawings that differ from their block. Each
walkthrough is measured and photographed at its first and its last step, so an overlap that
appears only as a search tree grows is caught. A drawing wider than the reading column is
scaled down to its 12 px text floor, then widened into the free margin beside the column;
one that still scrolls sideways at desktop width is listed under `notes`. It writes
contact sheets to `.tum-mcp/visuals/` and records the result in
`.tum-mcp/visual-check.json`. Editing an item or updating the app makes its result stale,
and `study report` lists items whose check is missing, stale or failing. A rerun redraws
only the items changed since their last passing check and lists the rest as `unchanged`;
updating the app's templates, images or the checks themselves redraws everything.

Authoring and review are separate. A prepare skill first drafts and checks its work
(Phase A): it reads each source once into a digest (`.tum-mcp/digests/`, `study digests`),
writes a structured plan per item (`.tum-mcp/plans/`) that one fresh reader checks before
any writing (`review run-checker --plans`, or `review plan-record` for a subagent's
answer), writes an answer key for anything
computed (`.tum-mcp/checks/<item>.py`, compared with the content by `study verify`), lints
each item as it is written (`study lint --item`) and finishes with the build, the render
check and the interaction smoke (`study visuals --interact`). The interaction check
opens Study and Exercise learning states, measures rendered formulas, and fails the
readiness receipt for any clipped formula or formula with its own scrollbar. An outer
table may scroll as a unit when its formulas remain reachable. Use `--phone` to
check phone and narrow layouts as well. It then asks before the review loop.

Ask `review-course` to run the review loop (Phase B, `tum-mcp review`). Each round writes
one packet per kind of item (study unit, exercise, exam pattern, cheatsheet, mock
question, lecture entry, course): the checks with a pass and a fail example each
(`review checklist --profile P`), the items' passages with block ids, the report flags,
the answer keys' results and the cited sources' digests. Fresh checkers, sessions that did
not write the content, answer with a verdict per check and quoted findings; `review
record` refuses answers for changed content or unquoted passages. The maker fixes by
check (`review fix` is refused while the quoted passage is unchanged and takes several
`--finding`), rejects a wrong finding with its reason or keeps a score-2 finding the content
cannot fix. `review findings` lists the open findings, one line each, grouped by block. A
defect is filed once, under the check that owns it, with the other checks it fails linked
to it. After the repairs, `review verify` writes one verification pass in the same round:
fresh checkers confirm or reopen each fix and judge again every check the repairs made
stale, so the round can close with current verdicts. Repairs made after that pass are
reported as unverified until the student asks for another round. Checkers get the cited
slide pages as images, the lesson's heading outline and the terms earlier lessons define. A verdict holds
until the blocks it covered change, so a later loop asks only about new and changed
items. `review close-round` computes the gate and writes `.tum-mcp/loop/scorecard.md`;
the gate passes an item when correctness and coverage score 3, every teaching check
passes and the other dimensions are at least 2 with a kept reason. An open invariant flag
(a disagreeing answer key, arithmetic, typed mathematics, a static trace, an unworked
result, text-only question, a cited page past the source's end, a paper students cannot practise) holds its
dimension below 3. The loop stops when the gate passes or its round budget is spent, and
`review status` always names the next action. Each drawn visual is judged from the
contact sheets for fidelity, form, layout, legibility, focus and convention, calibrated
against a gallery of rated examples (`study visuals --gallery`). Scores and findings
stay in `.tum-mcp/`; the app never shows them.

A repair can split an overloaded item while retaining its original key for one part.
After the complete repaired batch passes its draft checks, `review repair-scope` includes
the added items in the same round and records why. It preserves source coverage and
the approved budget. Added items await independent review; their scores are never copied
from the original item. The final report distinguishes the repair from its verification.

Checkers rule on advisory flags rather than silently ignoring them. A ruling that
opens a finding must name the relevant check; an unrelated finding cannot clear it.
Missing question context is not advisory: authored questions pair their text with
useful code, a diagram, formula, table or plot, and a checker cannot waive that gate.
Teaching checks assess every concept, including additions made after planning, and
objective checks require source evidence rather than promoting illustrative asides.
The headless checker gets one targeted repair attempt if its answer format is refused.

Workspace profiles keep the shared dimensions but tailor their evidence: exercise
reviews preserve released statements and assess each part's guide and answer rather
than requiring a second lesson. Exam checks distinguish cheatsheets, patterns and papers;
Lecture checks recording fidelity and added explanation without requiring quizzes.
Exam patterns and the cheatsheet have item scores (the cheatsheet in one pass against the
sources' exam requirements). Every current classified past question appears in its
pattern packet, with statement, solution and guide; changing one reopens the affected
checks. Forecast questions, Lecture selection
and Lecture entries have their own checks; the course pass checks their organization.

## Preview the app

From the course project folder, launch the prepared app with:

```sh
tum-mcp study
```

It opens the default browser at `http://127.0.0.1:8765`. Keep the terminal open;
press Ctrl+C to stop. In WSL, it opens the Windows browser through Windows interop.
If automatic opening is unavailable, open the printed URL. For a different project
or an unattended preview, use `tum-mcp study serve ./pse-ws26 --port 8765`.
If port 8765 is busy, stop the other preview or choose `tum-mcp study --port 8766`.
Keep the same address and port between sessions so browser progress remains available.

The preview binds `127.0.0.1`, serves `app/` and saves comments through a bounded
same-origin endpoint. It makes no campus requests.
No course credentials are copied into the website. Browser storage holds progress
locally. Nothing is published by these commands.

## Passage comments

Select text in Content, Flashcards, Practice, Exercises or Lecture, then click
**Comment** to record what is unclear. You can also use Ctrl/Command+Alt+M after
selecting text. The local preview saves notes in `.tum-mcp/comments.json`, separately
from learning progress. Click a numbered marker or highlighted text to open its notes
beside the quote. Notes can be edited, resolved or reopened; changed passages retain
their original quotes, and Revision notes keep their original topic and item.

Tell your agent: **“Address the open comments in this study project.”** The skill
reads the notes, checks the cited material, improves the affected explanation and
verifies the result before recording a resolution. Notes and status changes sync
automatically while the preview is open. Your draft is kept if a note changes
elsewhere; choose Use latest or Keep mine before saving. Reload after the agent
rebuilds the teaching content.

## Prepare weekly exercises

Ask `prepare-exercises` to prepare released weekly sheets in the same app. Study
and Exercises can be prepared in either order. When both exist, the workspace selector
at the bottom of the outline switches between them and remembers your place; on phones
it sits inside the open outline. The exercise list groups exercises by sheet and shows
each sheet's summary and due date when the sources provide them.

Each sub-question keeps its statement, supporting blocks, Guide and Solution together.
Shared givens come first. Work on paper, open that question's Solution directly (as a
table, graph, formula or code), or use its guide for one step at a time with optional
hints. Solutions open independently and reveal only their own question's answer;
shared solution notes appear once after the questions.
Multiple-choice steps are checked; for every other step you work on paper and press
**Compare**, the one place that shows the answer, its reasoning and a hint for the
likeliest mistake. The Recall row under the statement opens, next to the exercise on
desktop or as a full-page view on mobile, the Study passages it uses, the cheatsheet
entries it practises and up to two exam patterns of those entries. Closing it returns to
the same step and scroll position. The agent links every exercise, cheatsheet entry,
lecture note and Study unit to each workspace that exists, or records why none fits
(`study links`); a new lecture reopens those decisions, and readiness waits for them.
A link added to an older item does not reopen its review. A sheet whose problems are not all prepared
says which ones are still missing. Code steps open the function skeleton in a small editor and
show the model answer as code; code is never run, and nothing is graded by keywords.
Finishing the last step marks the exercise completed in the outline; you can also
right-click any entry to mark it. A Next link leads to the following exercise. Large
programming exercises can come with small distilled practice exercises that train one
idea each and link back to the original.

Choices, code drafts, hints and completion marks stay in this browser. Changing a
checked choice clears its verdict. Semantic changes start fresh progress for only that exercise, while retaining older
browser records; source-hash review alone preserves progress.
Reset on each workspace home affects only that workspace. Exercise passage comments
use the existing private comment service; hosted exports do not expose it.

## Prepare for exams

Ask `prepare-exams` to build the **Exam** workspace from the course's past exams,
exercises and materials. Past exams come from `materials/exams` (Moodle) or files you hold yourself:

```bash
tum-mcp study import ./pse-ws26 --file "Klausur WS23.pdf" --kind exam --title "Endterm WS23/24"
tum-mcp study duplicates ./pse-ws26 --near   # identical and likely duplicate copies
tum-mcp study exam-report ./pse-ws26         # what the agent reads before authoring
```

Imported files stay private and survive campus syncs. Copies of the same exam from
different places count once.

- **Cheatsheet**: a semester map of the exam-relevant ideas and one-line entries
  grouped by topic and section: facts, rules, comparisons, code and frameworks as well as
  formulas and methods. Open an entry for compact recall detail: the rule, conditions,
  decision or common mistake, followed by links to the exact prepared Study passage
  and related practice. Entries can also name prepared Exercises using
  `exercises: [{"set": "sheet-key", "exercise": "question-key"}]`; builds reject missing
  targets. A method can reuse a pattern's workflow. A complete one-line fact has nothing
  to open. Click a map node to read the same entry under the map and expand it; a long
  entry ends with Collapse. The map can be dragged, zoomed and opened full screen, where
  the entry sits beside it.
- **Exam patterns**: recurring question types with recognition cues, a solving workflow
  whose steps open to the exact formula, rule or code they apply (click a variable for
  its meaning), marking points, a worked practice that applies each workflow step,
  and drills with help initially hidden. Open Guide for staged prompts, optional hints
  and explained answers, or Solution for the complete answer. Previously prepared
  drills without guides remain readable; fresh preparation requires a guide.
- **Practice exams**: work through real past papers question by question with
  guidance, or read a whole paper and open each question's solution to check yourself;
  forecast practice exams follow the real exam's length and weighting with new
  variants and untested topics.

Fresh past-paper preparation requires task-specific guides. Older questions without
guides remain accessible with their solutions and an explicit missing-guidance note;
the app does not invent a generic Guide for them.

Right-click any entry in the sidebar, in any workspace, to mark it as completed.

Statistics such as "seen in 4 of 6 exams" are history, never a prediction.
Prepared Exam content is included in public course-app publication; its original
documents and private source metadata stay local.

## Publish a study website

Say "publish the study app". The `publish-course` agent handles validation, the
build, public export, GitHub setup, incremental uploads and deployment
verification, then returns the website link. You do not need to run commands or
choose workspace flags. If GitHub needs authentication, the agent starts sign-in
and you complete account authorization.

The GitHub repository is private; the Pages website is public. An eligible paid
GitHub plan is required for Pages from private repositories. This workflow does
not provide private website access. All prepared Study, Exercises, Exam and
Lecture content is included, with statements, hints, solutions and required
images. Review that content for the intended public audience. Missing workspaces
are not generated merely to publish.

Names use `study-<course>-<semester>` in lowercase with hyphens. A collision gets
a stable course suffix; existing repositories are never made public. Settings in
`.tum-mcp/github.json` bind updates to that course, semester and repository. A
failed setup retries the same saved repository rather than creating duplicates.

Older selective publication settings do not silently expand on an automatic
build. Ask to publish the complete app once to adopt the new contract, retaining
the same repository, URL and automatic-upload preference.

The export removes local-document citations and their source metadata. Canonical
external Lecture recording links remain: notes open their cited times, and
highlight ranges and thumbnails open the original recording. The recording
service may still require the visitor's campus login. Internal Recall panels,
definitions and links between workspaces remain available.

Only the generated renderer, sanitized learning data and required images are
uploaded. Downloaded originals, raw lecture evidence, credentials, AGENTS.md,
course inventory, Course Memory, authoring plans, passage comments, personal
progress, audio, generated videos and arbitrary files stay local. Git itself is
not required: the publisher uses authenticated GitHub API calls through the host's
`gh` CLI. Publication settings contain no credentials.

After setup, successful `tum-mcp study build PROJECT` commands update that same
repository automatically. Unchanged verified exports require no network calls
or commits. The study skills finish related edits in one build. Remote edits
are preserved for review; the publisher never force-pushes.

Ask the agent to update, pause or resume the published app as needed. Internally,
it uses `study publish status` once, `study publish --public-site` for first
publication or full-app adoption, and `study publish sync` for updates/recovery.
These are agent tools, not a checklist for the student. The existing pause/resume
controls and `study build --local-only` remain available.

Uploads are verified against the Pages build and GitHub checks for the exact
commit. Pending deployment exits with code 2 and is resumable; the agent keeps
verifying instead of asking you to retry a command. A successful
repository update alone is not a deployed site. Authentication, plan or network
failures preserve the local build. Polling has a budget of at most 60 seconds,
in addition to bounded API requests.
The `tum-mcp study` launcher prints local, hosted and repository URLs, plus pending
or paused status. Study progress remains per browser; passage comments require
the local preview and are disabled in the hosted export. Device synchronization
and offline support are not included.

## Create and maintain audio notes

Install the optional workflow with `tum-mcp install audio-notes`.
Use `prepare-study` or `prepare-exams` to author the course, then ask `audio-notes` to
convert that prepared content into spoken tracks. For example:

```text
Create audio notes from this prepared study website, one file per category.
Keep course outputs under audio/; prefer free ElevenLabs with local Kokoro fallback.
```

Audio Notes makes two kinds of track. Study tracks re-explain the lessons under
`app/study/`. Cheatsheet tracks are a spoken summary of the Exam workspace: each
cheatsheet entry's condition, rule or formula (read with audible grouping), one short
example and its trap, and each exam pattern's cues, steps and formulas. Both keep the
course's language, examples, assumptions and limitations. It turns tables, formulas, code and diagram sequences
into explanations that work without a screen. It does not independently research
the course or create new subject matter. An audio-only request reuses the prepared
course; it does not refresh campus sources or rebuild the website automatically.

Before synthesis, Audio Notes consolidates repeated explanations and reviews the
script for coverage, clear terminology, chapter re-entry and useful reinforcement. It
preserves distinct ideas and conditions rather than targeting a fixed duration.
Teaching reviews are tied to the script and narration-guidance fingerprints;
updated guidance prompts a review of existing scripts without automatically
regenerating unchanged speech. Audio supports uninterrupted hands-free revision:
no screen, spoken response or mandatory interaction. Exact Study dependencies are
disclosed where a construction cannot be taught through sound alone.
These checks do not establish learning outcomes.

Behind the skill, `tum-mcp audio-notes` does the checkable work: `sources` lists
Study units and Exam entries and patterns with their locators, `check` validates a
category script (coverage, stale sources, unspeakable symbols), `narration` lists one
file per sentence to synthesize, and `publish` assembles one AAC M4A with chapters at
-16 LUFS in the shared media runtime, checks it and writes the manifest receipt.
`listen` then transcribes the published track with the local speech recognizer
(`tum-mcp lecture runtime install`), lines every sentence up with the script and its
planned timing, re-listens to doubtful sentences on their own, and flags unclear or
missing words, dropped numbers and negations, several unheard words in a row, timing
slips, unplanned silences and pace. It checks what was said and when, not how natural
the voice sounds.

All course-specific audio files stay inside the project's `audio/` directory:

```text
audio/
  categories/01_category.json  Category script: sources, chapters and sentences
  scripts/01_category.txt    Published narration text, matching the track name
  tracks/01_category.m4a     One final AAC M4A per category
  chapters/01_category.json  Section titles and measured timestamps
  manifest.json             Last verified published coverage and fingerprints
  plan.json                 Current categories and missing/changed/pending work
  voice.json                Actual provider, voice and settings; no credentials
  playlist.m3u              Tracks in the intended study order
  README.md                 Playback, durations and update details
  SOURCES.md                Prepared content and original source locators
  COVERAGE.md               Source concepts mapped to narration and audio
  .build/                   Candidates, resumable chunks, downloads and QA
  archive/                  Recoverable superseded versions
```

Published tracks appear in the local app (`tum-mcp study`) in an **Audio** workspace:
Lectures and Exam shelves with Play all, a track page with chapters (each with a
Recall link to its Study passage, cheatsheet entry or pattern), a read-along
transcript that follows the voice and plays from any sentence you tap, playback
speed, and a mini player that keeps playing while you move to Study, Exercises or
Exam. Each track resumes where you stopped. **Download playlist** saves a ZIP of
every track (chapters included), an M3U playlist and a short README for any phone or
podcast player; each track also downloads on its own. Like videos, audio is local
only: hosted study sites never include or request it.

Names remain stable across updates, using prefixes and slugs such as
`01_security-foundations`. New content within a category updates that complete
track; a new category receives a new track. Existing audio is compared with
semantic content and file hashes, so unchanged speech can be reused. Scripts alone
do not count as completed audio coverage. Manual edits are preserved and reconciled.

The skill prefers free ElevenLabs when custom-text generation and downloading work.
Its anonymous website and authenticated API have different access requirements.
If free usage runs out or that route is unavailable, local Kokoro is the automatic
fallback unless the user explicitly restricts the provider. Affected categories
are regenerated with one Kokoro profile; completed categories remain intact.
Each category keeps its actual profile on later updates, and mixed providers across
categories are disclosed. Usage limits are respected; no paid usage or quota
workarounds are implied. Only reviewed narration goes to a cloud speech provider.

Kokoro weights, voices and pronunciation assets are cached once per execution
host/user, outside the course, with a reusable isolated runtime. The skill specifies
Windows, macOS and Linux locations, version/hash verification and safe cache reuse.
Course manifests record portable dependency identities rather than requiring a
previous machine's model paths. Setup is lazy, only when local synthesis is needed.
Actual OS/architecture, runtime and course-language compatibility are checked before
generation; unsupported or restricted hosts retain pending work with an explanation.

Candidates are validated before replacing usable tracks. Incomplete generations
remain pending with reusable work under `.build/`. Ask **“Complete the audio notes
for the updated study website”** to reconcile added, changed, removed or moved
material with the previous verified coverage. This is an agent skill, not a new
`tum-mcp study` CLI subcommand or a built-in speech service.

## Create and maintain video notes

Install the optional workflow with `tum-mcp install video-notes`. After
`prepare-study` has authored the course, ask for explainer videos, for example:

```text
Plan explainer videos for the topics in this study website that benefit from animation,
then make the BFS one first.
```

The agent proposes which topics get a video and records a reason for each topic it
leaves text-first. Concept videos develop one topic with sustained visual reasoning,
without a duration target. They adapt the prepared lesson: the problem first, the
course's own example before the general rule, and consistent objects and symbols.
They open with the learning question and section map, develop named knowledge
points within those sections, and finish by connecting the results. Storyboard
checks require `overview`, substantive beats with a `point`, and a final `recap`.
Questions may reuse practice when useful; there is no question quota. Nothing
outside the prepared content is added; a missing example is reported back to
`prepare-study`.

For an explicitly requested Exercise walkthrough, prepare and check the problem
with `prepare-exercises`, then use `video-notes exercise PROJECT SET/KEY` to bind
the exact problem. Cover all parts, justify the method, show transformations and
their meaning, and independently verify the result. The storyboard must establish
the shared problem and include setup, strategy, work, verification and an answer
for each part, with a distinct final-answer emphasis and a complete summary for
multi-part problems. Concise removes detours,
not instruction: a longer clear solution beats a short opaque one.

Behind the skill, `tum-mcp video-notes` does the checkable work. It prints the
fingerprints a storyboard cites and rejects storyboards whose sources changed. It
measures one narration file per sentence and renders the scenes with a pinned Manim
and Typst runtime (no LaTeX needed). It enforces that animations fit their narration
frame by frame; sentence cues align reveals to measured speech. It reports
overlapping or off-screen text. Labels can wrap at a measured scene width without
shrinking; crowded scenes need recomposition rather than smaller type.
Each run produces entry/middle/exit contact sheets
for review, and the final video is checked for codec,
sync, loudness, captions and chapters before publication. A render fails when a
teaching chapter only shows text labels or clears the screen at every step, and
storyboards reject arithmetic typed as plain labels; tables use the `self.grid`
helper. After publishing, `video-notes listen` transcribes the narration, checks each
sentence and its timing against the cues and takes a frame while each sentence is
spoken. Unchanged chapters are
reused, interrupted runs resume, and a failed publication restores the previous
files.

Video colors derive from the current app CSS. New projects use light; explicit
dark remains supported. A rendered video has a fixed theme, independent of the
app's theme switch.

Narration follows the Audio Notes policy: the free ElevenLabs website when it really
generates and downloads the text, otherwise local Kokoro, with no accounts or
payments. Kokoro has no German voice, so a German topic without a working voice
keeps its narration pending; a silent draft can be rendered for review but is never
published.

```text
videos/
  plan.json                  Which topics get videos, and why others are text-first
  storyboards/03_topic.json  Beats, narration, on-screen items and source locators
  scenes/03_topic/chapters.py  Manim scenes using the bundled helpers
  tracks/03_topic.mp4        Published H.264/AAC video
  captions/03_topic.vtt      Captions from measured narration
  chapters/03_topic.vtt      Chapter markers (and a JSON copy)
  posters/03_topic.jpg       Poster frame
  narration/03_topic.txt     Transcript
  manifest.json              Verified receipts for published videos
  style.json, voice.json     Course look and actual narrator profiles
  README.md, COVERAGE.md     Generated overview and coverage
  .build/                    Narration audio, timing, runs and caches
  archive/                   Superseded published files
```

Published videos appear above the topic's Content in the local app (`tum-mcp study`)
with chapters, captions and a transcript link, and show a notice when the topic
changed after the video was made. Exercise videos mount only when Solution (or
“Video solution (all parts)”) opens, never autoplay, pause on close, and do not
change written-answer progress. Exam does not expose them. Hosted study sites
never include or request videos; copy files from `videos/tracks/` to watch them
elsewhere. `tum-mcp video-notes inspect PROJECT` reports planned, stale, pending and
published videos, and `tum-mcp study demo PROJECT --videos` adds a synthetic preview
clip.

`study schema audio-plan`, `audio-manifest` and `review` describe typed records.
`study report PROJECT --section review` has a separate `media` section for
pending/broken/stale outputs, source-bound revisions, evidence and audio/video
averages. Media needs script, signal and listening evidence over the whole track;
video also needs frames and playback evidence. `audio-notes listen` and
`video-notes listen` supply the listening evidence (and, for video, speech-aligned
frames); they cover what was said and when, not how natural the voice sounds. Fresh
checkers score every dimension the evidence supports, a repaired item is checked
again before it is saved, and a dimension without evidence stays unscored. Reviews
never claim mastery or exam readiness.

The render runtime (about 320 MB) installs on first use with
`tum-mcp video-notes runtime install`. Windows x64 needs nothing else. macOS 14+ on
Apple Silicon needs `brew install cairo` and the Xcode Command Line Tools; Linux and
WSL on x86_64 with glibc 2.28+ need `libcairo2-dev`, `libpango1.0-dev` and a C
compiler. `runtime status` prints the exact command and never runs it for you.
Windows on ARM, Intel Macs, Linux ARM64 and musl Linux are not supported: Manim's
OpenGL dependencies publish no wheels there.

## Materials you download yourself

Files from other websites are not downloaded for you. Save them yourself and add them
with `tum-mcp study import PROJECT --file FILE --kind exam --title TITLE`.
Imported originals stay private and are never uploaded. Prepared app content
derived from them can be published with the complete course app; its source
metadata is removed from the public export.

## The course app

The shared course app is packaged in `bundled/course_app/site/`, separately from the
skill instructions. It owns layout, styling and interaction for Study, Exercises and
Lecture. Agents author only course content; `study build` installs the app,
preserves customized files and checks sources, so courses gain app improvements
without rewriting content. `tum-mcp study template` shows the bundled files and
their combined revision for reproducible development.

To see every component with synthetic data:

```sh
tum-mcp study demo ./component-preview
tum-mcp study serve ./component-preview
```

The demo creates one small Study unit and one exercise covering prose, code, tables,
formulas, graphs, UML diagrams, a flowchart, plots, cards and response controls.
It also includes pending Study topics and exercise sheets, plus private report examples
of unknown coverage and optional backlog. It is a
format reference, not necessarily a good teaching or question-authoring example; actual
course authoring follows reviewed sources and the preparation skills. Rich learning
pilots stay in private test fixtures. It uses no campus account, and an existing
edited demo is preserved.

## Local helper inputs

Agents use `tum-mcp study schema snapshot`, `schema content` and `schema exercises` for
validated input schemas. After authenticated tools verify availability, the agent
stages a source snapshot with exact course identity, coverage and resource revisions.
The helper does not authenticate the snapshot or grant any campus access itself.

```sh
tum-mcp study init PROJECT --course "Exact course title" --snapshot snapshot.json --learner on
tum-mcp study sync PROJECT --snapshot snapshot.json
```

Import paths are confined to the snapshot directory. Data is stored under the
bound project; credentials and unrelated personal records must never enter it.
Keep real course projects private and out of package artifacts. Uninstalling the
package preserves projects; remove your own project directory separately when wanted.

## Optional Explore reading

Prepared topics can include an **Explore** tab after Practice for useful supporting
context and further reading. It appears only when that topic has authored material
and opens directly on the reading. Core Content stays sufficient for the course tasks.
Explore has no required completion, cards, questions or minutes, and Continue/Next
keeps the core learning sequence.

Authors classify passages against course outcomes and task dependencies, using the
bundled prepare-study `references/explore.md` policy and private coverage ledger.
Core gaps, optional backlog and unrecorded coverage remain separate in agent reports;
only known core gaps appear on the learner overview. Optional items
carry their own source versions and stable keyed blocks. Changes still need source,
teaching and visual review but preserve saved core practice progress. Local passage
comments remain item-scoped; published sites include optional reading with Study and
exclude private comments/classification reasons. `study demo PROJECT` shows an example.

## Learning record

A course can keep a private record of how its student is doing, so a new chat continues
where the last one stopped. It is asked about once, when the course is first set up:
sync-course asks the student and runs `study init ... --learner on` or `--learner off`.
After that it records without asking again. Courses set up before this feature start off;
saying "keep a learning record for this course" (or `tum-mcp study learner enable .`)
turns it on.

| Stored in `.tum-mcp/learner/` | Never stored |
| --- | --- |
| Attempts on exercises and questions: solved, needed a hint, wrong, skipped | Chat text or quotes |
| Mistakes, each with the course source that corrects it, and when they were resolved | Guessed ability or scores |
| The next study step agreed in a chat | TUMonline data, names, credentials |

For study, practice and "what next" requests the agent reads `study learner brief .`: at
most 1.2 KB with open mistakes and the lessons to review for them, items due again (1, 3,
7, 14 and 30 days after a miss, pushed out by later successes) and the last plan. Other
requests never read it. Files are owner-only, never built into the app and never
published. `study learner show .` prints everything; `study learner forget . ID`,
`--item sheet-1`, `--before DATE` or `--all` deletes for good; `disable` stops
recording. Preferences about how to help ("hints before solutions") go in the course
`AGENTS.md` under `## Preferences`.

## Local course relationships

These commands require the optional **Course Memory** extension, disabled by default.
Enable it with `tum-mcp install course-memory` and reload your client. The installed
`course-memory` skill reads the links the course already holds and writes nothing while
answering; reviewed relationships are recorded only on an explicit request.
`study status PROJECT` reports the `course_memory` capability without reading the
graph. No whole-course ingestion, background process or model benchmark is started.

`study context PROJECT "topic" --limit 4 --max-bytes 8000` connects Study, Exercises, Exam
and Lecture items through the links authors write: exercise prerequisites, cheatsheet
units, passages, exercises and pattern workflows, pattern worked examples, mock variants,
past-question guidance, lecture-note passages and unit lectures, plus optional reviewed
assertions. Use `--item REF` or `--concept KEY` (a cheatsheet entry key) for an exact
selector, and `--purpose exercises` (or study, exam, lectures, review) for the workspace
the answer needs: an exact selector lists itself first, then its authored links in that
workspace. Each item cites only the sources and pages it cites itself, items carry their
semester-map `topic`, and `gaps` reports links an author recorded as not fitting.

`study impact PROJECT --source KEY` lists every direct dependent as a compact row with
its owner (lesson, exercise, exam item or lecture) and evidence status, then possible
review targets reached through authored links. Unknown and unmapped sources remain explicit. `study report PROJECT --section
knowledge` performs a full local semantic audit; it is excluded from the default five
report sections. `study schema knowledge` defines the optional private
`.tum-mcp/knowledge.json`. No graph database, embeddings, provider call
or persistent index is involved.

For teaching, reuse one narrow packet within the unchanged request, then read its
actual source pages natively. Long queries may match partial terms; those matches
remain navigation, not reviewed semantic claims. Avoid speculative whole-course
source searches alongside context. Context defaults remain 12 items / 24,000 UTF-8 bytes, at most two hops, 256 nodes, 2,048
examined edges, 64 distinct checked payloads and four lectures. All limits are reported;
partial or ambiguous navigation is not supported teaching. Review receipts bind complete
item meaning and source scope, independently of learner progress. Source changes require
actual evidence review, content repair and explicit re-review. Candidate/rejected-only
registries leave native course review unchanged. When reviewed relationships exist,
the course report supplies a separate `knowledge_revision`: save it alongside the
native `revision` only after reviewing the integration. Semantic changes stale that
optional binding, including stale reviewed records. Native revisions and student
progress remain independent. Earlier graph-bound review hashes may require one
explicit course review; approvals are never silently migrated or rewritten.

Finish bounded authored-content changes before reviewing their relationships together.
Structure/review reports verify reviewed semantic dependencies without constructing all
inactive-assertion diagnostics; the explicit knowledge report remains a full audit.
Snapshot byte verification and review fingerprints are unchanged.

Annotations and packets stay private and are not exported to the course website. Ordinary
builds do not load this optional registry. Use the installed `course-memory` skill's
`references/knowledge.md` for annotation, update and tutoring guidance. The graph
models course content; it does not infer a student's mastery or readiness.

`tum-mcp uninstall course-memory` stops graph queries, maintenance and semantic-review
binding while preserving `knowledge.json`, history, source evidence and user notes.
Malformed retained memory cannot break native course reports while disabled.
Reinstall preserves the files and revalidates them on use; changed sources while
disabled do not become trusted by reinstalling. Static `study schema knowledge`
remains available for inspection. Removing a skill cannot erase an open chat's
existing context; reload or start a fresh chat to clear it.
