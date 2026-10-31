# Changes

## Unreleased

- Moodle discovery includes enrolled courses from every semester, current semester
  first. Explicit older and otherwise accessible known course IDs support material
  reads and indexed search. Live Moodle course access is checked before returning
  content, including cached text; enrollment prompts and denied courses stay blocked.
- Artemis discovery includes active and past courses, with active courses first and
  semester labels for past courses when available. Past-course lectures, student slides
  and released exercise statements use the same server permissions and read boundaries.
- Ship timezone data so current-semester detection also works on Windows and other
  hosts without a system IANA timezone database.
- Lecture preparation no longer fails on recordings whose AAC timestamps drift slightly:
  a window decoded a few samples short now pads that jitter instead of rejecting every
  chunk. Each failed preflight sample or chunk is recorded in the receipt with its time,
  stage (acquire, cache, decode, analyze, recognize, validate) and reason, and identical
  failures of every preflight sample stop before the full recording is downloaded.
- New `derivation` block: working shown one transformation per line, aligned on its
  relation, each line with its reason and one labelled group per requested result. With
  `walkthrough` it steps through the lines with Previous and Next, keeps earlier lines,
  draws the state each line reaches, and offers Show all steps. Usable in Study, exercise
  Compare answers, Exam and Lecture.
- Mathematics is typeset by the bundled KaTeX 0.19.1, as in Notion: TeX fonts, square
  roots, kets and spacing, text-size inline vectors and matrices, and long inline math
  that wraps after its relations on a phone. The build still validates every expression
  and its MathML stays as the fallback, now without stray operator space around bars,
  slashes and ket labels; `\left( \right)` fences now compile.
- `study report` flags described objects (`described_object`), large inline matrices
  (`tall_inline_math`), results computed inside one sentence in Compare
  (`compressed_working`), openings that introduce several symbols before any example
  (`dense_introduction`), worked cases without their general rule
  (`example_without_rule`) and symbol-dense identities in prose (`unexplained_identity`).
- review-course separates purposeful reinforcement from duplication, walks each item as
  a first encounter, adds checks for reminders at the point of use, unpacked notation,
  shown objects, explained working and general rules, and calibrates them on two subjects.
  prepare-lecture adds a teaching-value pass for lecture visuals.
- Diagrams, UML, plots and figures take the background of the card that holds them
  instead of a darker inset.
- A Lecture section's sources sit on its title row when its first passage is untitled.
  Review scorecards accept the solution, transfer, Compare and Explore visual ids the
  render check emits, and a review saved with no scores reports every dimension
  unscored instead of failing.

## 0.16.0 — 2026-10-31

- TUMonline can now read your grades and progress, exams and semester fee status. Each is
  off until you allow it in `tum-mcp manage tumonline`. New tools list your achievements
  (grade, credits, semester, date), show module and exam progress per study, list the exams
  you are registered for, search exam offers by course with dates, rooms and registration
  windows, and show the current semester fee, payment deadline and bookings. Examiner names,
  record IDs and the account holder are left out, and nothing registers for an exam.
- The TUMonline permission selector lists only these four permissions, so the arrow keys
  move between them. The Account, Other IT services and Miscellaneous rows are gone: they
  hold credentials or link to outside services.

## 0.15.1 — 2026-10-31

- The README's Get started section ends with setting up a course: create a folder, open an
  agent chat in it and run `$sync-course` (Codex) or `/sync-course` (Claude Code). It
  recommends GPT-6.1 Terra (xhigh) and Claude Opus 5.5 (medium) as starting models, and
  says to collect your own resources in a temporary folder for the agent to sort.

## 0.15.0 — 2026-10-31

- The managed block in a course project's `AGENTS.md` is now an agent guide. It tells the
  agent that it works for a student of the course, which skill handles which kind of
  request (and how to answer "what should I do now?" with a dated plan), how to read short
  requests such as "this week" or "the exam", where each kind of course information lives,
  and how to answer as a tutor. `study sync` and `study upgrade` replace an outdated guide
  and keep the student's own text; an edited guide is kept and reported.
- `tum-mcp study find PROJECT "words"` lists the pages of stored sources that mention every
  word, with a snippet each, and names the sources it could not search. Without words it
  lists every source with its key, title, file and status.
- New course handbooks have a Conventions section for the textbook, notation, terms and
  answer format the course expects.
- Agents look at the slide and sheet pages they rely on instead of trusting extracted text,
  which drops figures and scrambles tables and formulas. `study text --images` renders up to
  12 pages to PNGs for hosts that cannot open PDFs (such as Codex), and `study find` and
  `study text` name the PDF file so hosts that can (such as Claude Code) open the page
  directly. The agent guide, the skills and the Moodle and Artemis read tools say so; the
  unused PDF page reader in the extraction worker became this renderer.
- One unreadable page no longer fails a whole PDF. When pypdf rejects a page (for example a
  slide beyond its parsing limits) or the whole file (a damaged cross-reference table), PDFium
  reads it instead; a page neither can read is listed as needing a visual check. This covers
  `study text`, `study find`, `study import` and Moodle and Artemis material text. `study find`
  also matches words printed with ligatures, so "first" finds "ﬁrst".
- Course content can use heading levels 1 to 3 in Study, Exercises, Exam and Lecture.
  A block without a title continues the section above it, so a table or answer frame
  no longer needs a heading of its own. The page outline nests subsections.
- A multi-part exercise shows one guide per part. The Guide, Solution and "Try another"
  buttons share one row under the problem, and the redundant list of part numbers is gone.
- `study report` flags a flat Study outline of four or more units, multi-part exercises that
  share one guide, and exercise passages that set assumptions or sources apart.
- review-course also scores organization and redundancy for each unit and exercise, and the
  course as a whole: the order of its units and groups, what repeats across units and
  workspaces, and, when Exercises, Exam or Lecture sit beside Study, how they
  link to the passages that teach what they need (integration). `study report --section
  structure` prints a course map and flags terms used before they are taught, odd groups,
  repeated passages and practice, and missing links. Each lost point names its rubric
  check, and the report counts the checks that fail most. An existing `review.json` still
  loads and lists the dimensions it lacks.
- PDF text extraction works for agents running in a macOS sandbox such as Codex's
  `workspace-write`: its memory limit no longer needs to list every process on the machine,
  which the sandbox forbids, so `study text` no longer fails on uncached PDFs there.
- The skills group Study units by lecture, fold assumptions into the problem statement,
  give verdicts with the source's definitions, cover every presented part of the chosen
  sheet, and take the newest sheet stamped for the current semester when no release date
  is shown.
- Campus tools that only read from Moodle, Artemis or Zulip and save local files or
  checkpoints (`moodle_download_material`, `moodle_refresh`, `artemis_get_attachment`,
  `zulip_save_checkpoint`) are now marked read-only, so agents that ask before
  non-read-only tools no longer prompt for downloads. Sign-in, sign-out and cache
  clearing keep their warnings.
- `tum-mcp doctor --live` saves each campus check with its time, and `doctor` and the
  `login` selector show that result for 12 hours instead of "Not verified". Signing in
  again or logging out clears it; only the result, its time and file metadata are stored.

## 0.14.2 — 2026-10-30

- TUMonline login keeps its browser open when an unauthenticated session refresh
  returns an empty HTTP 204, allowing sign-in to finish instead of reporting
  `INVALID_RESPONSE`.

## 0.14.1 — 2026-10-30

- TUMonline login keeps waiting while sign-in is incomplete. An empty HTTP 200
  from the anonymous session refresh no longer closes the login window with
  `INVALID_RESPONSE`. Malformed responses and server failures still report errors.

## 0.14.0 — 2026-10-30

- Graph diagrams sit on a grid: each node takes a `row` and `col` instead of pixel
  coordinates. The app sizes boxes from their labels (two lines, centred), spaces rows and
  columns, crops to what is drawn, bends a blocked edge around nodes to the side where it
  crosses fewest edges, draws self-loops and bows the two arrows of a two-way pair apart,
  each with its own label, and places every edge label clear of lines and nodes.
- UML class and state diagrams and a new `flowchart` diagram are laid out by the bundled
  Eclipse Layout Kernel (elkjs, EPL-2.0, loaded only on pages that show such a diagram)
  in the order the author lists elements: an interface above its implementations with one
  joined trunk, state machines with curved transitions and entry activities in a
  compartment, flowcharts with questions inside the diamonds and labelled exits.
  Sequence diagrams keep their renderer.
- Plots: a series can be a `function` of x that the build samples, split at poles and
  jumps, or data drawn as lines, markers, points, connected steps or stems with their
  values; plots add shaded `areas`, marked `notes`, explicit ticks, a logarithmic y
  axis labelled with real values and labels at the line ends. Axis labels are Unicode.
- Drawings keep 12 px text on a phone: graphs and UML diagrams shrink only that far and
  scroll sideways beyond it; plots redraw at their real width.
- `tum-mcp study visuals PROJECT` measures every drawn visual of lessons, practice
  questions, exercise steps and Exam at 390, 600 and 1280 px (lines through nodes,
  clashing labels, small or clipped text, drawings that differ from their block), writes
  contact sheets to `.tum-mcp/visuals/` and records the result; `study report` gains a
  render section that lists missing, stale and failing checks.
- `review-course` reviews in five passes (logic, text, visuals, interaction and
  intuition), scores a new intuition dimension and each drawn visual on a six-criterion
  visual rubric, and calibrates against a gallery of rated examples
  (`study visuals --gallery`). A review passes only when every visual is scored, and
  representation never scores above the item's weakest visual.
- prepare-study gains guides for diagrams and plots, and the study skills run the render
  check after each build. The component demo shows each new diagram and plot form.

## 0.13.0 — 2026-10-29

- Lessons read as structure rather than prose: a `text` step or point that opens with a short `Label: ` shows the label in bold, and `study report` flags paragraphs over 45 words or three long sentences (`dense_paragraph`), calculations chained inside a sentence (`prose_calculation`) and mathematics typed as plain characters instead of inline LaTeX (`plain_math`). Arithmetic in inline LaTeX is recomputed like arithmetic in prose. prepare-study's writing guide gains the procedure, worked-example and notation rules behind them.
- Figures are checked for readable labels at build time: a label that touches a line, sits on a filled shape, overlaps another label or leaves the canvas is rejected with its text named, and the app draws labels on a page-coloured halo at the drawn size. prepare-study's figure guide adopts label and spacing rules from open-source diagram skills.
- Study lessons gain definitions that sit inside the section introducing them, as the
  term in bold beside its meaning; a `{{term}}` mention anywhere in the app opens the
  definition in place, and blocks can carry a `key` that links lead to.
- Text sections can give a hard idea as numbered `steps`, and a new `figure` block shows
  a drawing (checked SVG that follows the light and dark theme, cropped to what is drawn)
  or an image from the app's `figures/` folder, in lessons, questions, exercises and
  published sites.
- Diagram labels never hide behind nodes: a label wider than its edge moves above the
  shapes, and a single picture shows its caption once instead of a description and a
  caption. The exercise outline drops its separators, and the completed mark stays on
  the entry's line.
- Algorithm traces show the algorithm's state beside the drawing (a queue, the domains),
  mark what changed at each step and highlight the edge being worked on.
- Practice questions that are about a situation show it (a graph, drawing, table,
  formula or code) beside the question, and a question about a concept may stand alone;
  options appear in a stable shuffled order and a question can offer one optional hint. A
  question missed at the first attempt stays in To review after **Try again** until it
  is answered correctly from a fresh start.
- Exercise solutions give one short, labelled answer per part, in the form the part asks
  for; model answers can be tables, lists or formulas, and graph answers are drawn on the
  graph. **Compare** is now the only reveal: hints stop after the last one, a step
  without a check is compared too, and an explanation may not repeat its model answer.
- **Review** beside a prerequisite opens that Study passage next to the exercise without
  losing your place; a unit links its Lecture, the exercises that build on it and
  the Exam patterns that cite it, and Lecture link back. In the local
  preview, a citation opens the stored course file at the cited page.
- A new `review-course` skill scores each Study unit and exercise from 1 to 3 on
  correctness, clarity, cognitive load, representation, practice and coverage, saves the
  scores with their findings in `.tum-mcp/review.json` (`study schema review`) and fixes
  what falls below the bar; `study report` lists unreviewed, stale and low items.
  prepare-study and prepare-exercises finish with it.
- `tum-mcp study report` flags dense paragraphs, sections of more than about 90 words of
  prose, sentences about the material instead of the subject ("the lecture groups…"),
  question pictures that repeat the prompt, exercise statements pasted as one block,
  thin lessons, untraced procedures, questions too long for a phone screen, slide
  numbers left in titles instead of `pages`,
  answer tables Compare never answers, wrong arithmetic, large steps with one hint and
  feedback that names no mistake. A coverage ledger (`.tum-mcp/coverage.json`,
  `study schema coverage`) records each source's stated outcomes, sheet problems and
  course state, so the report lists what is not yet taught, read or prepared; learners
  see which problems are not prepared yet. The study skills share one review gate and
  one writing guide (plain, direct sentences after ASD-STE100, without AI phrasing), and
  they show two-input rules as decision matrices and released exercise statements split
  by part with their givens and setting drawn.
- The exercise outline names a category only when it adds to the set titles, and the
  outline keeps its scroll position when you open a lesson.
- Codex picks up changed or newly enabled skills: the plugin version follows the
  installed skills, and `tum-mcp doctor` names the refresh step when Codex still loads
  an older copy.

## 0.12.0 — 2026-10-29

- Remove the optional Studocu extension, its `sync-studocu` skill and `tum-mcp studocu`
  commands. Download such material yourself and add it with `tum-mcp study import`.

## 0.11.0 — 2026-10-28

- Add the base `prepare-exams` workflow and the local **Exam** workspace: a
  cheatsheet with a semester map you can pan, zoom and open full screen, exam patterns
  with solving workflows and a worked practice question each, guided past papers, and
  practice exams with a solution under every question. Statistics, map layout,
  blueprint and novelty checks are derived by code. Exam is never published.
- Add `tum-mcp study exam-report`, `study text` (page text extracted once per file),
  `study import` (private local files such as past exams you hold) and
  `study duplicates` (identical and near-duplicate copies across Moodle, Artemis,
  Studocu and local files); `study inspect` lists identical copies.
- Students answer on paper. Only multiple-choice answers are checked; every other step
  offers Compare, which shows one answer, its explanation and a hint for the likeliest
  mistake. Exercises no longer show answer boxes, review buttons or status lines;
  finishing an exercise marks it completed in the outline.
- Exercises gain code-writing steps that open the function skeleton in an editor and
  show the model answer as code, numbered code blocks and distilled practice for large
  programming tasks; prepare-exercises documents how to distil Artemis programming
  exercises. Text and numeric checks hold a single answer, and authors are told to give
  every question the context its answers use.
- Authored questions must show code, a diagram, a formula, a table or a plot beside
  their text, and their first sentence says what the student produces. A new `uml`
  block draws UML class, sequence and state diagrams in every workspace, and
  `` `code` `` in text renders as inline code.
- Code is syntax-highlighted in blocks, editors and model answers. A new `files` block
  shows a small project with a file tree, tabs and editable files kept in the browser;
  steps point at file lines with an "Open in files" jump, code-writing steps edit
  the project file they point at, and the file tree folds away. Distilled exercises no
  longer carry concept tags. Code blocks can carry a step-by-step walkthrough, and
  prepare-study asks for examples shown as a diagram or walkthrough, not only told.
- Right-click (or Shift+F10) any sidebar entry to mark it completed.
- A page whose sections all cite the same sources shows one citation beside its title
  line, and a cheatsheet section whose entries share sources cites them once; exam
  pages mention past exams only when there are some. Lines that only described a page
  or told students to compare (such as the Exam summary) are gone, and the skills
  ask for text that teaches.
- A new `tree` block draws hierarchies such as file structures, object trees and call
  trees with icons, connector lines and optional notes.
- Cheatsheet entries show their recognition cue and pitfall as labelled rows with icons;
  the semester map has an icon toolbar and an in-canvas legend.
- Give every skill a Codex display name, so Codex no longer shows "Tum MCP:" prefixes.
- Pages no longer wait for the local video index; the video panel appears once it loads,
  so a slow preview server cannot drop it.
- Pages no longer over-scroll: hidden labels cannot stretch the page, and the space that
  keeps step arrows in place goes once you scroll back up.

## 0.10.0 — 2026-10-27

- Add the optional `video-notes` extension (`tum-mcp install video-notes`): short
  narrated, animated explainers from prepared Study topics, one per selected topic,
  under the course's `videos/` folder. The skill plans storyboards from the prepared
  content only; `tum-mcp video-notes` checks storyboards, measures narration, renders
  with a pinned Manim/Typst runtime installed on first use, verifies sync, loudness,
  captions and layout, and publishes with receipts, archives and crash recovery.
- Play published videos in the local app above each topic's Content, with chapters,
  captions, a transcript and a notice when the topic changed after the video was made.
  Hosted study sites never request or include videos.
- Keep extension selections forward compatible: unknown on/off settings from newer
  releases are preserved, and the video setting is only written when enabled.
- Use NVIDIA GPUs for Prepare Lecture recognition on Windows x64 and Linux/WSL x86_64.
  `auto` selects CUDA for a CUDA 12 GPU of compute capability 7.0+, adds a pinned cuBLAS to
  the runtime (no CUDA toolkit or cuDNN), checks the GPU during installation and
  otherwise stays on CPU int8. `TUM_MCP_LECTURE_ENGINE` also accepts `cuda`.
- Document the eSpeak data path limit that breaks local Kokoro on macOS in Audio Notes.
- Keep the local course app loading on Windows: the preview server now queues the
  app's burst of parallel module requests instead of refusing all but five.

## 0.9.5 — 2026-10-27

- Simplify the course project overview wording.

## 0.9.4 — 2026-10-27

- Document the course project folders, including optional extension outputs.

## 0.9.3 — 2026-10-27

- Simplify the README setup and extension guidance.

## 0.9.2 — 2026-10-27

- Combine connection status, extension status and health checks in `doctor`.
  Show only installed or configured clients, including in the setup picker.
- Rename campus sign-in to `login`, paired with `logout`. Keep `connect` and
  `status` as hidden compatibility aliases, including the previous status JSON.
- Make the course app consistent across Study and Exercises: one choice style,
  feedback panel, counter format, arrow controls and disclosure chevron. Revision
  covers all topics until you choose, and review links open the view with items.
- Show exercise goals in Guidance, sheet summaries and due dates in the list, Mark
  reviewed at the end with a visible finish, and a link to the next exercise.
- Improve detail: readable graph edges, fitted phone diagram labels, word-wrapped
  boxes, no dark-mode flash, steady flashcard layout, labelled reset and in-app
  confirmation for deleting comments, and neutral page copy on published sites.
- Lecture: recording times open from the sources of each passage and figure
  instead of appearing in the text, and the sidebar lists lectures only.
- Add a Contents button to Study, Exercises and Lecture. It lists the page's
  headings and follows your reading; wide screens can keep it docked beside the
  text. The home resume button shows a play icon with the topic name.
- Keep queued Contents updates from a previous view from hiding the current
  page's outline after navigation.
- Remove unused serif font files. Builds delete unedited copies and publication
  removes them from managed sites; edited copies are kept.
- Base the study skills on the app: they describe content and checks and point to
  the bundled app instead of restating its styling.

## 0.9.1 — 2026-10-27

- Make Audio Notes an optional `audio-notes` extension. Keep five base skills,
  preserve existing audio files, and describe all extensions in a compact README table.

- Use one compact terminal layout for help, connection status, extensions,
  skills and permissions. Keep automation output available through `--json`.
- Give setup, install and uninstall matching status-aware pickers. Uninstall
  offers full package removal through All. Keep named commands for scripts and
  show optional workflow state through status, connect and doctor; remove the
  separate extensions command group. Studocu browser sign-in stays unverified.
- Include TUMonline connection and permission status in doctor. Default checks
  do not read credentials or create policy files; live checks verify identity
  without fetching studies or grades.
- Make unverified status dots blue, ready/enabled green, action needed amber,
  failures red and inactive states muted. Preserve labels with color disabled.

## 0.9.0 — 2026-10-26

- Add read-only TUMonline study, public catalog and partial curriculum-position
  tools, with separate account permissions, verified identity and bounded paging.
- Add optional Studocu search and reviewed personal PDF collection through
  `tum-mcp install studocu`. Preserve originals, course bindings and recovery
  history; supplementary personal-use sources are excluded from publication.
- Add optional `tum-mcp install lecture` and Prepare Lecture for timestamped
  Lecture in the existing course app. Prefer transcripts and supplied
  materials, skip whole-silent recordings, preserve original-time coverage and
  request only critical video frames. Publication remains an explicit opt-in.
- Support isolated, pinned CPU recognition on Windows x64, Intel Mac and supported
  Linux/WSL hosts, alongside Apple Silicon MLX acceleration. Keep heavy recognizer
  dependencies optional; captions/imported WebVTT need no recognizer installation.
- Handle persistent Studocu SSE replies, enforce response IDs/search limits and
  bound TUMonline policy reads and catalog output. Unify extension status/removal
  and verify both optional workflows together. Shorten the getting-started guide.
- Preserve existing Moodle compatibility tools, sessions, downloads, customized
  skills and existing course layouts during installation and upgrades.

## 0.8.1 — 2026-10-26

- Give every doctor/update status a dot: yellow for unverified or attention-needed
  states, green for ready/updated, neutral for information/disabled, and red only
  for failures. Keep status labels readable with terminal colors disabled.

## 0.8.0 — 2026-10-26

- Read Artemis courses, lectures, exercises, own feedback and accessible Zulip
  channels after sign-in without separate local scope grants. Preserve server
  permissions, bounded queries and disabled remote writes.
- Keep standard `--help` for command discovery and guide agents toward relevant
  current-semester metadata before retrieving course content.

## 0.7.0 — 2026-10-26

- Share one course app between Study and Exercises, with a single workspace
  selector in the sidebar footer and a responsive mobile outline.
- Add `prepare-exercises` for source-backed weekly exercises with optional hints,
  explanations, solutions and prepared checks. Support editable tables, long math
  and code drafts, graph selections/paths and line graph sample points. Open work
  uses rubric comparison; the app does not execute code or grade proofs.
- Keep step navigation in place, shorten controls and show section sources through
  compact reference icons. Preserve browser progress, drafts and passage comments.
- Use `.tum-mcp/` for private course state and a cited agent course handbook covering
  course organization, schedules, coursework/platforms, assessment and bonus rules.
  Track reviewed source versions, coverage gaps and changed supporting sources.
- Rename `sync-study` to `sync-course` and `publish-study` to `publish-course`;
  retain managed migration for previous skill names and preserve personal overrides.
- Keep the shipped app a minimal reusable component template, explicitly distinct
  from an example of good course teaching. Keep rich synthetic tests out of the package.

New projects use `app/`; existing `study/` websites remain supported. Run
`tum-mcp study upgrade PROJECT` explicitly to rename legacy `.study/` metadata;
it preserves private records and archives the old root instructions. The separate
`study build PROJECT --upgrade-layout` moves a verified legacy web folder to `app/`
with a backup. Neither package installation nor update migrates course folders or
rebuilds personal sites automatically. Exercise publication is opt-in.

## 0.6.1 — 2026-10-25

- Make `tum-mcp update` download and validate the latest npm release before
  replacing the invoked installation and refreshing configured clients.
  Preserve newer installed versions; `--local` refreshes without contacting npm.
- Make `tum-mcp uninstall` remove managed client setup and the npm package in
  one command. Keep saved data by default; stop package removal on conflicts.
  Client-only removal retains npm, and `--keep-package` supports managed cleanup.
- Run npm through Node on all platforms, serialize package operations, and use
  an external worker while Windows replaces package files.
- Test actual global installations against a private synthetic registry, including
  failed downloads/preparation/replacement, customized files, and data preservation.

## 0.6.0 — 2026-10-25

- Merge course setup and updates into `sync-study`, with recovery for incomplete
  projects and preservation of edits, source coverage and course identity.
- Ship five focused skills: `read-content`, `sync-study`, `prepare-study`,
  `audio-notes` and `publish-study`. Managed upgrades preserve personal overrides.
- Package the study renderer: consistent typography, responsive tables and math,
  flip cards, four-choice practice, collapsible revision topics and review dialogs.
- Add local passage comments across content, cards and practice, with anchored
  popups, automatic sync and conflict protection.
- Support inline LaTeX variables and a mobile outline overlay that keeps your place.
- Add category audio guidance and optional GitHub Pages publication. First
  publication requires consent to a public website; the repository stays private.
- Install all five skills for Cursor and Antigravity during setup and update,
  with ownership checks that preserve customized files during update and removal.
- Recognize occupied preview ports and deliver complete HTTP rejection responses
  on Windows, and serve web assets independently of OS file associations.
  Reuse isolated test fixtures,
  retain native/platform coverage and expose slow tests and failures in CI.
- Preserve Windows CRLF study instructions through repeated synchronization.
- Group Artemis and Zulip implementation by provider, retaining read-only
  course tools. Fix OCR with aliased macOS temporary paths.

Upgrading does not rebuild personal study sites automatically. Ask your agent to
update the prepared website; customized renderer files are preserved for review.
Audio, source materials, comments and study projects remain outside package
installation/removal.
