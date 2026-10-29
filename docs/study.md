# Course study projects

Six base skills cover source reading, course sync, Study preparation, Exercises
preparation, exam preparation and publishing. They run in your local agent, using the connected
MCP tools to read course sources. The CLI validates and stores the resulting local
files; it does not run an AI model.
The optional `prepare-lecture` skill adds a Lecture Notes workspace; install it with
`tum-mcp install lecture`. See [Lecture Notes](lecture-notes.md).
The optional `audio-notes` skill turns prepared lessons into spoken tracks; install
it with `tum-mcp install audio-notes`. The optional `video-notes` skill turns prepared
topics into short narrated explainer videos; install it with `tum-mcp install video-notes`.

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
  AGENTS.md                 Course knowledge and current inventory
  materials/
    content/                Lectures, slides and reading
    exams/                  Available revision material
    exercises/              Released statements and practice references
    other/                  Announcements and course information
  .tum-mcp/
    course.md               Cited course structure, logistics, rules and unknowns
    state.json              Course binding, source versions and coverage
    notes/                  Detailed course/agent notes when needed
  app/                      Shared Study, Exercises, Exam Prep and optional Lecture Notes website
    content.json            Optional source-backed Study content
    exercises.json          Optional prepared exercise guidance
    exam.json               Optional Exam Prep content (local only)
  audio/                    Optional category audio derived from the prepared website
  videos/                   Optional explainer videos derived from the prepared website
```

`AGENTS.md` retains user rules and points agents to `.tum-mcp/course.md`. That short
handbook explains the course's goals, lectures/tutorials, weekly work and platforms,
assessment/bonus conditions, communication and preparation map. Claims carry source
links/locators and checked dates; unknowns and conflicting announcements stay visible.
Detailed source content remains in materials/. All TUM MCP course state, plans and
agent notes live under .tum-mcp/.

`sync-course` reads the relevant authoritative sources and maintains the handbook;
the CLI scaffolds it without pretending to understand the course. Its review receipt
records the local generation and hashes of supporting sources. `study inspect`
reports changed supporting sources and coverage gaps so refreshes can focus on
affected claims. A reviewed local snapshot does not establish live freshness or
complete understanding. See the bundled sync-course context reference for the full
source-review workflow.

To rename existing private `.study/` state explicitly, close other course processes
and run `tum-mcp study upgrade PROJECT`. It preserves unknown private files,
comments, publication settings and the full old root instructions as
`.tum-mcp/legacy-AGENTS.md`. Course identity, materials and browser progress stay the
same. Existing legacy state remains readable until upgrade; two state folders are
a conflict to reconcile, never silently merged. This differs from the web-folder
upgrade below.

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
writes `app/content.json` from your stored course material, and `tum-mcp study build`
installs the shared course app and checks every cited source. Units follow the
course's lecture or week sequence when useful, or consistent topics, with at most
one category level. Every unit has:

- Content: a short lesson with objectives, source links, assumptions and worked
  examples, using formulas, tables, code, diagrams or line graphs where they help.
  Terms to learn appear in labelled **Definition** boxes; a dotted term anywhere in
  the app opens its definition in place. Algorithm traces step through one operation
  at a time and show the algorithm's state (a queue, the domains) beside the drawing,
  marking what changed.
- Flashcards for recall. On a keyboard, arrows move, Space flips and 1/2 rate a card.
- Practice questions that show their situation (a graph, a table, a formula) beside
  the question, with options in a stable shuffled order, an optional hint and feedback
  for every option.

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
for this course. A unit's header links the Lecture Notes, exercises and Exam Prep
patterns that build on it. In the local preview, a citation opens the stored course
file at the cited page. Formulas and inline
notation such as `\(v_i\)` compile locally to native MathML; code and dollar signs
stay literal. The app has light and dark themes and a phone layout.

Content lives in `app/content.json`; shared renderer modules and CSS keep the
site extensible. Source hashes identify affected units. A stale source stops a
build until the explanation is reviewed. Unchanged units retain their revision;
revised questions receive separate progress. Customized templates are preserved
and reported, so the agent must review compatibility when extending them.

```sh
tum-mcp study inspect ./pse-ws26
tum-mcp study build ./pse-ws26
tum-mcp study report ./pse-ws26   # review flags and what the sources leave uncovered
```

The agent records what each lecture states students should learn, and which sheet
problems are prepared, in `.tum-mcp/coverage.json`. `study report` lists outcomes
that are not yet taught, sources not yet read and problems still pending, so a request
to cover a whole course is judged against the course's own outcomes.

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

The preview binds `127.0.0.1`, serves `app/` (or the existing legacy `study/`) and saves comments through a bounded
same-origin endpoint. It makes no campus requests.
No course credentials are copied into the website. Browser storage holds progress
locally. Nothing is published by these commands.

## Passage comments

Select text in Content, Flashcards, Practice, Exercises or Lecture Notes, then click
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

Each exercise shows the original statement and subparts first. Work on paper, open the
solution directly (one short answer per part, as a table, graph, formula or code), or
open **Guidance** for the exercise's goals and one step at a time with optional hints.
Multiple-choice steps are checked; for every other step you work on paper and press
**Compare**, the one place that shows the answer, its reasoning and a hint for the
likeliest mistake. **Review** beside a prerequisite opens the Study passage next to
the exercise without losing your place. A sheet whose problems are not all prepared
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

Ask `prepare-exams` to build the **Exam Prep** workspace from the course's past exams,
exercises and materials. Past exams come from `materials/exams` (Moodle) or files you hold yourself:

```bash
tum-mcp study import ./pse-ws26 --file "Klausur WS23.pdf" --kind exam --title "Endterm WS23/24"
tum-mcp study duplicates ./pse-ws26 --near   # identical and likely duplicate copies
tum-mcp study exam-report ./pse-ws26         # what the agent reads before authoring
```

Imported files stay private and survive campus syncs. Copies of the same exam from
different places count once.

- **Cheatsheet**: a semester map of the exam-relevant ideas and one-line entries with
  formulas, triggers and pitfalls; open an entry for details. The map can be dragged,
  zoomed and opened full screen.
- **Exam patterns**: recurring question types with recognition cues, a solving workflow,
  answer template, marking points, a worked practice that applies each workflow step,
  and drills whose answers you can open at any time.
- **Practice exams**: work through real past papers question by question with
  guidance, or read a whole paper and open each question's solution to check yourself;
  forecast practice exams follow the real exam's length and weighting with new
  variants and untested topics.

Right-click any entry in the sidebar, in any workspace, to mark it as completed.

Statistics such as "seen in 4 of 6 exams" are history, never a prediction. Exam Prep
always stays local: it is never published.

Existing `study/` projects continue to work. New projects use `app/`. To upgrade a
verified legacy layout explicitly, run `tum-mcp study build PROJECT --upgrade-layout`.
It keeps the original tree at `.tum-mcp/layout-backup/`, preserves the course identity,
learning revisions, comments, settings and personal files, and stops on customized
generated files, an occupied backup or two layouts. Repeating a completed upgrade
is a no-op. Do not create `app/` alongside an existing `study/` by hand.

## Publish a study website

The `publish-course` skill makes a prepared site accessible from a phone
or another computer. Its GitHub repository is private; the Pages website is
public. An eligible paid GitHub plan is required for Pages from private repositories.
This workflow does not provide private website access. Review lesson text,
quotations and source links for the intended public audience before publishing.

Install GitHub CLI on the execution host and run `gh auth login --hostname github.com`.
`tum-mcp doctor` checks CLI availability without network access; `doctor --live`
also verifies GitHub authentication. It does not publish anything, open sign-in
automatically, extract tokens, or change Git credential settings.

```sh
# Preview the chosen name and hosting requirements without GitHub mutations.
tum-mcp study publish --project PROJECT
# After choosing public website content; the repository stays private.
tum-mcp study publish --project PROJECT --public-site
# Optional account/name override on first setup:
tum-mcp study publish --project PROJECT --public-site --repository OWNER/NAME
```

Names use `study-<course>-<semester>` in lowercase with hyphens. A collision gets
a stable course suffix; existing repositories are never made public. Settings in
`.tum-mcp/github.json` bind updates to that course, semester and repository. A
failed setup retries the same saved repository rather than creating duplicates.

Study is the default hosted workspace, including for old settings. Exercise
statements, hints and full solutions need explicit `--include-exercises` on the
publish command after reviewing their public exposure. `--exclude-exercises`
removes Exercises from subsequent eligible exports, using the same repository and URL. An
Exercises-only site also requires explicit inclusion. Lecture Notes separately requires
`--include-lectures`; old settings default to exclusion. `--exclude-lectures` also removes
previously managed lecture images. A notes-only export with notes excluded is refused.

Only the selected generated website renderer and data are uploaded. Downloaded
originals, credentials, AGENTS.md, study inventory, passage comments, progress,
audio, videos and arbitrary files stay local. Git itself is not required: the publisher
uses authenticated GitHub API calls through `gh`. Local publication settings do
not contain credentials.

After setup, successful `tum-mcp study build PROJECT` commands update that same
repository automatically. Unchanged verified exports require no network calls
or commits. The study skills finish related edits in one build. Remote edits
are preserved for review; the publisher never force-pushes.

```sh
tum-mcp study publish status PROJECT
tum-mcp study publish sync PROJECT       # retry pending/failed deployment
tum-mcp study publish pause PROJECT      # pause future automatic uploads
tum-mcp study publish resume PROJECT
tum-mcp study build PROJECT --local-only # skip uploading this build
```

Uploads are verified against the Pages build and GitHub checks for the exact
commit. Pending deployment exits with code 2 and is resumable; a successful
repository update alone is not a deployed site. Authentication, plan or network
failures preserve the local build. Polling has a budget of at most 60 seconds,
in addition to bounded API requests.
The `tum-mcp study` launcher prints local, hosted and repository URLs, plus pending
or paused status. Study progress remains per browser; passage comments require
the local preview and are disabled in the hosted export. Device synchronization
and offline support are not included.

## Create and maintain audio notes

Install the optional workflow with `tum-mcp install audio-notes`.
Use `prepare-study` to author the interactive course, then ask `audio-notes` to
convert that prepared content into spoken lessons. For example:

```text
Create audio notes from this prepared study website, one file per category.
Keep course outputs under audio/; prefer free ElevenLabs with local Kokoro fallback.
```

Audio Notes reads `app/content.json`, retaining the course's language, examples,
assumptions and limitations. It turns tables, formulas, code and diagram sequences
into explanations that work without a screen. It does not independently research
the course or create new subject matter. An audio-only request reuses the prepared
course; it does not refresh campus sources or rebuild the website automatically.

Before synthesis, Audio Notes consolidates repeated explanations and reviews the
script for coverage, clear terminology, concise examples and useful recall. It
preserves distinct ideas and conditions rather than targeting a fixed duration.
Teaching reviews are tied to the script and narration-guidance fingerprints;
updated guidance prompts a review of existing scripts without automatically
regenerating unchanged speech. These checks do not establish learning outcomes.

All course-specific audio files stay inside the project's `audio/` directory:

```text
audio/
  scripts/01_category.txt    Editable narration, matching the track name
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
leaves text-first. Each video covers one topic, usually 3 to 8 minutes, in short
chapters. It is a visual adaptation of the prepared lesson: the problem first, the
course's own example before the general rule, consistent colors per symbol, one or
two pause-and-think questions from the topic's practice, and a short recap. Nothing
outside the prepared content is added; a missing example is reported back to
`prepare-study`.

Behind the skill, `tum-mcp video-notes` does the checkable work. It prints the
fingerprints a storyboard cites and rejects storyboards whose sources changed. It
measures one narration file per sentence and renders the scenes with a pinned Manim
and Typst runtime (no LaTeX needed). It enforces that animations fit their narration
frame by frame and reports overlapping or off-screen text. Each run produces a
contact sheet per chapter for review, and the final video is checked for codec,
sync, loudness, captions and chapters before publication. Unchanged chapters are
reused, interrupted runs resume, and a failed publication restores the previous
files.

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
changed after the video was made. They load when you press play. Hosted study sites
never include or request videos; copy files from `videos/tracks/` to watch them
elsewhere. `tum-mcp video-notes inspect PROJECT` reports planned, stale, pending and
published videos, and `tum-mcp study demo PROJECT --videos` adds a synthetic preview
clip.

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
Imported files stay private: they are never published.

## The course app

The shared course app is packaged in `bundled/course_app/site/`, separately from the
skill instructions. It owns layout, styling and interaction for Study, Exercises and
Lecture Notes. Agents author only course content; `study build` installs the app,
preserves customized files and checks sources, so courses gain app improvements
without rewriting content. `tum-mcp study template` shows the bundled files and
their combined revision for reproducible development.

To see every component with synthetic data:

```sh
tum-mcp study demo ./component-preview
tum-mcp study serve ./component-preview
```

The demo creates one small Study unit and one exercise covering prose, code, tables,
formulas, graph/process diagrams, cards and response controls. It is a format
reference, not necessarily a good teaching or question-authoring example; actual
course authoring follows reviewed sources and the preparation skills. Rich learning
pilots stay in private test fixtures. It uses no campus account, and an existing
edited demo is preserved.

## Local helper inputs

Agents use `tum-mcp study schema snapshot`, `schema content` and `schema exercises` for
validated input schemas. After authenticated tools verify availability, the agent
stages a source snapshot with exact course identity, coverage and resource revisions.
The helper does not authenticate the snapshot or grant any campus access itself.

```sh
tum-mcp study init PROJECT --course "Exact course title" --snapshot snapshot.json
tum-mcp study sync PROJECT --snapshot snapshot.json
```

Import paths are confined to the snapshot directory. Data is stored under the
bound project; credentials and unrelated personal records must never enter it.
Keep real course projects private and out of package artifacts. Uninstalling the
package preserves projects; remove your own project directory separately when wanted.
