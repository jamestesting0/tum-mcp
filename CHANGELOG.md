# Changes

## 0.23.0 — 2026-11-10

- Cleaner terminal output. `--help` groups commands into Get started, Manage and
  Used by your coding agent, and the npm launcher shows the same help before setup.
  Statuses use one vocabulary with distinct symbols (✓ ! ✗ ○ –). Errors are single
  `Error:` lines that name the fix. Narrow terminals keep their indentation.
- `doctor` leads with its verdict and next steps, and states a repeated detail once
  per section. `setup`, `install`, `update` and `login` end with numbered next steps
  instead of paragraphs.
- `tum-mcp logout SERVICE [ACCOUNT]` accepts all five services, with ACCOUNT needed
  only when several are saved. Interactive logout no longer runs a network check.
- Removing Everything in `tum-mcp uninstall` asks for one confirmation and lists what
  is removed and kept. The first runtime preparation prints one line instead of
  installer output, and writes a log if it fails.
- Saved browser profiles appear as `Google Chrome (TUM)`; plain names open a
  temporary profile. The TUMonline "Admission" permission is now labelled
  "Semester fee".

## 0.22.0 — 2026-11-10

- Learning record: a private, per-course record of a student's attempts, mistakes (with
  the course source that corrects them) and next plan, so the agent picks up where the
  last chat stopped. It is asked about once, at the course's first setup
  (`study init --learner on|off`), then records automatically; courses set up earlier
  start off, and one sentence ("keep a learning record") turns it on. Chat text and
  guessed ability are never stored; `study learner show` and `forget` give the student
  full control. It works without Course Memory.
- `study inspect` reports `course_memory` and `learner`, so agents need no separate
  `study status` call.
- Free-text `study context` queries rank rare course words above common ones, count a
  guide step for its exercise, keep the best match and its authored links first, and
  return nothing for topics the course does not use.
- `study impact` lists every dependent of a changed source as one compact row with its
  owner, instead of eight full items, plus the workflows and questions that use a changed
  item; packets are about half the size and no longer cut off for large slide decks.
- Course Memory reads every link the course now holds: cheatsheet passages, exercises and
  pattern workflows, pattern worked examples, mock variants, distilled practice,
  past-question guidance prerequisites and lecture-note passages, and tags items with
  their semester-map topic. Recorded "no link fits" decisions appear as `gaps`.
- `study context --item` and `--concept` list the selected item first, then the items it
  links to in the requested workspace, before weaker neighbours. `--concept` accepts
  cheatsheet concept keys.
- Locators and freshness use each block, question, flashcard, exercise step and lecture
  note's own cited sources and pages, so slide pages no longer point at a recording.
- The course-memory skill is shorter and read-only while answering: it no longer creates
  `knowledge.json` on first use. Reviewed relationships are recorded only on request.
- Packet paths carry the author's own explanation of a link (prerequisite guidance, exam
  concept links, mock change notes). Agents answer navigation questions such as "which
  exercises practise X" from the packet and open pages only to teach or quote them; in a
  paired agent check this cut answer cost by about a third at equal accuracy.

## 0.21.0 — 2026-11-09

- Published audio notes play in a new Audio workspace in the local app: Lectures and
  Exam shelves with Play all, chapters that each link back to their Study passage,
  cheatsheet entry or pattern, a read-along transcript that follows the voice and plays
  from any sentence you tap, speed, resume, and a mini player that keeps playing while
  you move between workspaces. Download playlist saves every track with its chapters,
  an M3U playlist and a README as one ZIP; each track also downloads on its own. Audio
  stays local, and hosted sites never request it.
- Audio Notes also turns the Exam workspace into a spoken summary: each cheatsheet
  entry's condition, rule or formula, one example and its trap, and each exam pattern's
  cues, steps and formulas. `tum-mcp audio-notes sources | check | narration | publish`
  lists the sources, checks coverage and speakable text, and assembles one chaptered
  AAC track at -16 LUFS with its receipt.
- `tum-mcp audio-notes listen` and `tum-mcp video-notes listen` transcribe a published
  track with the local speech recognizer, line each sentence up with the script and its
  timing, re-check doubtful sentences on their own, and flag unclear or missing words,
  dropped numbers and negations, timing slips, silences and pace. Videos also get a
  frame for each spoken sentence.
- Media reviews score every dimension their evidence supports, re-check repaired items
  before saving them, and score video visuals once per scene step.
- Videos teach with objects instead of text slides: a render fails when a teaching
  chapter shows only labels or clears the screen at every step, storyboards reject
  arithmetic typed as labels, a `self.grid` helper draws tables, and a requested video
  always ends published.
- Video Notes commands work inside Codex's sandbox: the data folder is no longer
  re-permissioned on every call and the speech model is found without a write lock.

## 0.20.0 — 2026-11-09

- `tum-mcp setup` now completes a first installation in one command: after the
  installed coding clients it offers the optional workflows (Lecture, Audio Notes,
  Video Notes, Course Memory). Nothing is preselected and Enter with nothing selected
  skips a step; without a supported client no client picker opens.
  `setup --client NAME` still registers clients only.
- Every cheatsheet shows its semester map again: readiness asks for a link from each
  idea on the map to what it builds on or contrasts with, or for the idea to leave the
  map, and the app draws the map even before any link exists.
- The semester map groups each topic in its own tinted region with the title centred on
  top, laid out in course order and opened at a readable size. Ideas keep the sheet's
  order; links never pass behind another card or through a title, run between regions
  through the gaps, and leave and enter cards at separate points. The key sits under the
  heading instead of over the map.
- The Study outline shows every lecture the same way, a muted label over its title; a
  lecture with several lessons folds, its lessons hang from a thin rail, and titles line
  up across lessons, folders and Revision (and in the Exam outline).
- Exercise questions read "a. Find the cost ..." with the label inline, and sub-questions
  "i." and "ii." nest under their question. A title that only repeats the problem number
  is no longer shown as a heading, and parts citing the same pages show the citation once.
- Review packets also split at 60 requested verdicts, so fresh checkers complete
  them. Plan approvals stay approved when another task starts or when one batch groups
  earlier batches for a combined review.
- An unclear stretch of a lecture recording is disclosed to the reviewer instead of
  blocking readiness; a retained note or highlight may not include it.
- Content checks find mathematics typed as plain characters in Exam patterns, past-paper
  help, past-paper statements and mock questions, and more forms such as `U1=`, `b^d`,
  `0.19/0.72`, state names such as `S3`, and a lone symbol beside LaTeX. An exam pattern
  workflow must show the formula, rule or code its steps apply, and a planned `model`
  concept must be drawn. Repeated option feedback, one-sentence tables and long prose
  sections are raised for review.
- Every exercise, cheatsheet entry, lecture note and Study unit links each workspace that
  exists or records why none fits (`tum-mcp study links`); new content reopens those
  decisions and readiness waits for them. Exercises recall their Study passages,
  cheatsheet entries and exam patterns. A link added to an older item does not reopen its
  review. Recall chips name untitled passages by their section.
- Study has two new blocks: `example` (givens, steps, result) for a worked case read
  whole, and `callout` for one pitfall (shown like an Exam pattern pitfall) or one
  condition. A section may run at most two paragraphs before another shape; worked cases
  told as prose are raised for review, and a planned set of parallel `cases` is a table or
  one example each.
- Practice questions: placeholder table headers and "all of the above" options hold
  readiness; a key much longer than the other options, a stem word only the key repeats
  and an unmarked negative stem are raised for review.
- Lecture notes can name their kind and give the lecturer's working as steps and its
  consequences as points; the recording time shows once, as "Watch mm:ss". A lecture
  title that contains a date, or a summary that describes the recording or the notes
  instead of the topic, is refused, and the exam home no longer counts past papers.
- Each authoring skill opens its workflow with the same short maths card (sets, logic,
  one span per calculation, words in `\mathrm{}`, fractions in worked steps), and the
  exam skill links its pattern reference at the pattern step.
- Content blocks follow one spacing scale by relation (heading, context, block, section),
  removing the extra gap between a practice question and its table.
- Plain-text mathematics also covers sums worked in digits (`4+4+3=11`), sets
  (`X={1,2}`), predicates (`P(a)`), `↔` and `∅`, middle-dot products and one expression
  split over several math spans; a paper size such as A4 is no longer taken for a variable.
  Words in math mode (`\(P(A=true)\)`) are flagged, since they render as italic letters
  run together. Headers such as "What it illustrates" or "Explanation" count as
  placeholders. An exercise part titled with its own text, and provenance in set summaries
  or statements, are flagged.
- An exam pattern step that computes a value must show the formula it computes with, in
  `math`, code or inline LaTeX; words such as "multiply and sum" are not enough. A
  pattern's header shows how often it was asked only across several past exams, and no
  longer repeats the last exam that the table below already lists.
- `tum-mcp study build` prints the readiness problems of items changed since the last
  build. `tum-mcp review checklist` offers a gate-passing exemplar for exercises, exam
  patterns and lecture notes as well as Study units, and a sentence copied verbatim from
  an exemplar is raised for review.
- Tables use light row rules and tighter rows; guide steps no longer repeat their source
  icon on a line of its own.
- `tum-mcp study text --pages` accepts lists such as `3,7-9`. Invalid tool arguments
  name the field, and duplicate snapshot keys are named.

## 0.19.1 — 2026-11-07

- Saved browser choices always show their profile name in parentheses.
- `tum-mcp manage browsers` can open a saved profile until you close its window,
  allowing password saving and browser settings through native browser storage.
- Doctor reuses successful client probes for 24 hours while checking local
  registration and hooks every time. Changed configuration, runtime or environment
  invalidates the cache; `--refresh-clients` forces a fresh probe and failures retry.

## 0.19.0 — 2026-11-07

- Preparation determines source coverage before drafting and checks the complete
  draft before offering review. Review defaults to one approved round of review
  and repair, with a final score and support for explicitly requested extra rounds.
- Teaching guidance strengthens concise concept definitions, unfamiliar-term
  annotations, transfer practice and complete solving procedures. Structural
  repairs preserve the approved scope and identify newly added content for review.
- Walkthroughs support synchronized diagram highlights and wraparound navigation.
  Exam practice includes guidance, cheatsheet entries reveal recall details and
  links progressively, and exam metadata uses the latest dated paper.
- Setup installs course completion guards for Codex, Claude Code, Cursor and
  Antigravity, explains host-specific trust requirements and verifies client
  registration. Codex trust is limited to the installed hooks' exact identities.
- Doctor performs live verification by default; `--static` uses local checks.
  Successful account verification remains current for eight hours.
- Login can reuse optional dedicated Chromium profiles and remembers the last
  choice. Managed profiles retain encrypted campus sessions, support scoped
  logout and removal, and work with Windows browsers through both WSL engines.
- Completed connections remain successful if the browser closes during cleanup;
  incomplete sign-in errors identify pending services. App modules and server
  sources are grouped for easier navigation.

## 0.18.0 — 2026-11-06

- Escape cancels CLI selectors promptly in both interactive and numbered terminal prompts.
- Course authoring stores each lesson, exercise, exam entry and lecture in its own
  file. The Python implementation is organized under `tum_mcp.course`; the
  `tum-mcp study`, Lecture, media and campus tool entry points remain available.
- Preparation records source digests, structured teaching plans and computed answer
  keys. Lint identifies broken plan links and content defects while an item is
  being written; answer verification compares computed results with the content.
- `tum-mcp review` runs gated rounds with fresh checkers, quoted findings, explicit
  advisory rulings and verification of repairs. Packets carry workspace-specific
  guidance, and unchanged evidence is reused. Internal fingerprint history stays
  in the ledger rather than being repeated in checker inputs.
- Review guidance distinguishes first-time Study teaching from concise Exam
  revision, independent drills and authored applications of sourced rules.
  Bounded preparations do not require extra lessons to fill topic groups. Passing
  computed checks alone does not establish teaching quality or complete coverage.
- Shared app controls support walkthrough inspection and search. Listed derivations
  keep their full width, and long inline expressions scroll locally without
  breaking equations or overflowing the page.
- Lecture preparation accepts small accumulated audio timestamp jitter while
  retaining the missing-frame rejection boundary. Notes can include a meaningful
  source frame, a sourced SVG illustration and a Recall link; recording coverage remains distinct from
  semantic or listening review.

## 0.17.2 — 2026-11-04

- Selectors accept Escape to cancel and show Esc in the keyboard guide. Ctrl+C
  still cancels. This includes numbered prompts, browser choice, extensions,
  client setup and TUMonline permissions.
- Login checks saved campus sessions when verification is missing, stale or no
  longer matches the credential key. Fresh results are reused; rejected sessions
  are marked Action needed and preselected. Default doctor checks remain local.
- Running `tum-mcp logout` without arguments opens an account picker with the
  same verification behavior. Nothing is preselected; removal preserves other
  connections, account settings, TUMonline permissions and downloads. Explicit
  provider/account logout remains available.

## 0.17.1 — 2026-11-04

- Login preselects services marked Action needed, including services with more than
  one saved account when any account needs attention. Press Enter to accept or
  change the selection with Space. Numbered prompts also accept Enter for the
  displayed defaults; other services remain opt-in.

## 0.17.0 — 2026-11-02

- Reviews hunt for defects instead of justifying scores: `tum-mcp study review-pack` gives one
  rubric pass its checks, the item's passages and its report prompts; findings quote their
  passage word for word and are accepted or rejected with a reason; scores follow from accepted
  findings, with checks passed per dimension; each 3 quotes its closest call; every pass is
  recorded (fresh or same session) and every open report prompt is fixed or kept with a reason.
- The cheatsheet covers all exam-relevant knowledge, not only formulas and methods: the
  coverage ledger records each source's `exam` requirements and the report lists the sheet's
  gaps; entries take sections (`path`) inside a topic and show tables, lists, trees, code and
  diagrams when opened; a one-line fact has no empty disclosure; only an entry naming a
  pattern in `workflow_from` shows its workflow. A formula entry needs its formula, and
  `exam-report` flags a method without steps. The cheatsheet is a reviewed item
  (`exam/sheet`, one `cheatsheet` review pass, its own checks) that turns stale when an entry,
  shown workflow or requirement changes; its review cannot pass coverage while a content source
  has no requirement, and `exam-report` flags typed mathematics, slash quotients in displayed
  formulas and a line that repeats its formula. Recall shows the whole Study section with one
  citation.
- Meaning lists show a variable written as bare LaTeX (`\lambda`) as mathematics.
- A semester-map node shows the same entry as the list under the map, expandable; in full
  screen the entry sits beside the map. An opened entry taller than the screen ends with
  Collapse, which returns to its title.
- Cheatsheet entries without a formula can list their variables' meanings (`symbols`); the
  cheatsheet review checks concise text and meanings, and `exam-report` flags dense paragraphs
  and meaning lists typed as sentences.
- `study visuals` and the review and verification steps check desktop width only; `--phone`
  adds phone and narrow widths when asked. A check that cannot run caps only the dimension it
  judges.
- Lecture notes (`lectures.json` schema 3) need a `title` and the `context` they answer
  before their message, and may link a Study `passage` as Recall. Notes and highlights share
  one cleaner layout.
- Notation guidance says when to write a fraction and when a slash or `\div`.
- `study report` flags exercise statements that frame instead of giving (`statement_framing`).
- `study visuals --exam` no longer fails on an untitled Exam figure.
- "Publish the study app" publishes all prepared Study, Exercises, Exam and Lecture
  workspaces and required images through the existing incremental publisher.
  Public exports remove document citations and private evidence while retaining
  canonical lecture recording links and timestamps. Existing selective publications
  require renewed full-app consent; generated audio and videos remain local.
- Study teaches students meeting a topic for the first time; Exam stays concise revision.
  The course context gains a Teaching profile, and `prepare-study` plans each unit by
  choosing teaching moves (a problem to start from, a concrete case, labelled steps, a
  contrast, relation sentences) that fit each idea, instead of applying one fixed lesson shape.
  `review-course` scores motivation, plan fit and cognitive load. A score of 3 now needs
  quoted evidence and no open check flag, so existing reviews must be redone.
- The four app workspaces share one page anatomy: homes list rows with status, every item
  ends with a Next link, and counters read "Question 2 of 5", "Step 1 of 4" and
  "Card 3 of 10". Controls use short labels: "Guide", "Solution", "Check", "Explain",
  "Next step" and "Next question"; an Exercises step shows the same "Step 2 of 5" chip as
  an Exam pattern, and code, graph and file resets are icons inside their component.
  Practice, a Guide, an Exam pattern and the practice review share one compact Explain list
  for the other options of a multiple-choice question, and one hint style. Guide, Solution
  and every other opened section show their content in the same contained panel, and an
  Exam pattern's Compare reveals the same Answer box as an Exercises step. A
  Recall row names the ideas an exercise or exam item builds on; each chip opens a
  one-line reminder, and from it the Study passage or the cheatsheet entry beside the
  page. A titled Study block may add an optional `insight` behind a light bulb, and exam
  concepts may name the Study `passages` that teach them. Lecture highlights put the
  description under the frame and title. The full-screen semester map keeps its legend. Its arrowheads end on the card edge and take
  the colour of a highlighted line, and a line that would cross another card goes around it
  with as few corners as possible.
  An Exam pattern's workflow reads as a numbered procedure with each reason under its
  step. Where the method forks, a decision step lists its cases (what the student sees and
  the move it calls for). A step or case opens on a click to the formula, rule or code it
  applies (`apply`), replacing the separate answer template. The worked practice covers every case once, as parts of one
  question or as separate examples behind an Example switcher, and asks which case applies;
  Practise covers every case again without steps, and the build checks both; every Practise
  item opens the same Solution panel. Pitfalls show
  the wrong working, its correction and why it fails. `exam.json` patterns now use
  `examples` and structured `pitfalls`, and every pattern has Practise. review-course scores
  Exam patterns as items with pattern checks and calibration cases. Question statements in
  Exam read like Exercises, without a box. Tables fit their content and draw a full grid
  whose lines keep their contrast on the page, in panels and in the Answer box; the caption
  sits above the table. Formulas break only between their parts (at a top-level comma,
  \quad or \qquad), never inside an equation; a part too wide for a phone shrinks a little,
  then scrolls. Inline math stays on one line in the same way. Derivation lines also align
  on arrows such as \mapsto and \longrightarrow, and the working takes its full width before
  the reasons. `study report` flags mathematics read aloud in words ("theta over two").
  A derivation line that lists several statements runs flush left (`listed_derivation_line`
  flags it), formulas also break before \iff or \Rightarrow, and math never scrolls
  vertically. The left and right arrows turn flashcards and no longer switch the Content,
  Flashcards and Practice tabs, and a turned card is not painted as selected.
  Variables in displayed formulas can open their meaning: a click on a marked variable, or
  Enter on the focused formula, shows what it is in that context. Exam pattern applied
  formulas must give their variables' meanings, cheatsheet formulas list every variable's
  general meaning when the entry opens, and Study and Exercise derivations add meanings
  where a reader would stop to recall a variable (`symbols`; a meaning written once serves
  its whole unit, exercise or pattern). The build rejects a meaning for a variable its
  formula does not spell. `study report` adds `unexplained_symbol`, `renamed_meaning` and
  `echoed_meaning`; prepare-study, prepare-exercises and prepare-exams share a variables
  guide, and review-course scores `clarity.symbols_recall`.
  The local preview no longer hides the arrow KaTeX draws for \vec (its security policy now
  allows style attributes).
  A clicked variable's popup shows only its meaning; Enter on a formula lists every meaning
  with its variable. The build rejects LaTeX holding a control character (a single-backslash
  JSON escape such as \theta), and `study report` flags `redeclared_meaning`.
- Derivations: line breaking, alignment and variable marking read one LaTeX scanner (mirrored
  in Python with a shared case table), so a bra such as \langle 0| no longer hides the `=` a
  line aligns on, and a ket such as |a, b\rangle is never cut; an inline formula never breaks.
  Reasons sit beside the working, with lines aligned on their relation, only when every line
  fits there; otherwise each line and its reason are centred rows, and a derivation never runs
  past its section. `study report` flags `unaligned_line`.
- Arrow keys page Study practice questions and exercise guide steps while focus is inside them,
  and leave radio buttons and fields alone.
- Variable meanings: a variable is underlined once per block. A decorated form (K_j^\dagger,
  x^*, x', \bar a) is its own variable and never shows the plain meaning; applied and
  cheatsheet formulas need its meaning. In exercises and pattern examples lone letters such as
  k count as task quantities. Formula `conditions` are optional, and `generic_meaning` flags
  meanings such as "Given quantities".
- Exam pattern pitfalls need a `situation`, the task moment the mistake happens in, shown first.
- Spacing follows four relationship tokens with one rule for a control after its content
  (Guide, Solution, Hint); a browser test fails when a relationship shows two values.
- Comments: the marker counts every comment and sits apart from a title. A build deletes
  comments whose unit, exercise, exam item or lecture section is gone, and the app deletes a
  comment whose field no longer holds its quote; passages inside closed panels are found.
- Figures: a label written as inline LaTeX is typeset by KaTeX; `typed_math_label` flags labels
  typing mathematics as characters.
- Writing and review: the writing guide adds cohesion (familiar before new, point first, honest
  connectives) and verbs over nominalisations (`nominalisation` prompt); review-course scores
  Cohesion as a tenth item dimension.
  Video Notes play in the app's own minimal player: a seek bar split at the chapters
  with the chapter and time on hover, the current chapter beside the time, captions,
  speed, full screen and YouTube's keyboard keys.
  Fixed app text drops sentences that repeat what the page already shows, and the
  writing guide explains which words to cut and which links to keep.

- Add optional Course Memory, disabled by default, for source-checked relationships
  across course workspaces. Install with `tum-mcp install course-memory`; local setup
  happens on the next relevant request. Uninstall stops graph use and preserves its
  files. Reinstall checks freshness before reuse. Native course review remains
  independent of disabled memory, and no document pipeline or background index is added.
- Moodle discovery defaults to current-semester courses; `include_past=true` lists
  enrolled courses from every semester, current first. Explicit older and otherwise
  accessible known course IDs support material reads and indexed search. Live Moodle
  course access is checked before returning content, including cached text; enrollment prompts and denied courses stay blocked.
- Artemis discovery defaults to active courses; `include_past=true` adds past courses
  with semester labels when available. CLI discovery has `--include-past`. Past-course
  lectures, student slides and released exercise statements use the same server
  permissions and read boundaries.
- Explicit semester requests such as WS23 select the older offering for course
  preparation and keep its semester and provider IDs during later syncs. Unscoped
  Moodle material search defaults to current courses; `include_past=true` expands it.
- Ship timezone data so current-semester detection also works on Windows and other
  hosts without a system IANA timezone database.
- Lecture separates concise Notes from substantial worked explanations worth watching.
  Short remarks, corrections and instructions need no watch card; optional note images
  carry meaning and descriptive alt text. Highlights show a time range and duration, a recording frame, a title,
  what it teaches and up to three points, and opens the recording at its start; the
  lecture list shows note/highlight counts and watching time. Notes-only,
  highlights-only and no selected additions are supported.
  `tum-mcp lecture thumbnail` stages a captured frame as a 960 px thumbnail, and
  `tum-mcp lecture check` verifies highlight boundaries against the transcript and prints
  each highlight's opening/closing speech and each note's supporting speech.
  `lectures.json` moves to schema version 2;
  earlier lecture notes need re-authoring.
- Lecture preparation no longer fails on recordings whose AAC timestamps drift slightly:
  a window decoded a few samples short now pads that jitter instead of rejecting every
  chunk. Each failed preflight sample or chunk is recorded in the receipt with its time,
  stage (acquire, cache, decode, analyze, recognize, validate) and reason, and identical
  failures of every preflight sample stop before the full recording is downloaded.
- New `derivation` block: working shown one transformation per line, aligned on its
  relation, each line with its reason and one labelled group per requested result. With
  `walkthrough` it steps through the lines with Previous and Next, keeps earlier lines,
  draws the state each line reaches, and offers Show all steps. Usable in Study, exercise
  Compare answers and Exam.
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
- Diagrams, UML, plots and figures take the background of the card that holds them
  instead of a darker inset.
- Review scorecards accept the solution, transfer, Compare and Explore visual ids the
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
