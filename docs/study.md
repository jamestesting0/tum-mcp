# Course study projects

Six base skills cover source reading, course sync, Study preparation, Exercises preparation, audio and publishing.
The optional `prepare-lecture` skill adds a Lecture Notes workspace; install it with
`tum-mcp install lecture`. See [Lecture Notes](lecture-notes.md).
The optional `sync-studocu` skill collects selected student-uploaded material separately.

## Studocu materials

Install the optional extension with `tum-mcp install studocu` and reload your
client. Ask `sync-studocu` to collect materials for a course project. It can
initialize a Studocu-only project with a verified course and semester.
Search is anonymous and bounded; a limited result set is not a complete inventory.
`tum-mcp studocu connect` explains how to sign in to Studocu in your own browser.
The extension cannot infer account entitlement or download original files through
the public MCP. Save an original that your account permits in the browser.

The skill records a reviewed selection with `tum-mcp studocu plan PROJECT
--selection FILE` and tracks it with `tum-mcp studocu status PROJECT --json`.
Import a selected original with `tum-mcp studocu import PROJECT --document-id ID
--file FILE`. The document-to-file association is user-selected. Originals go to
`materials/studocu/summaries`, `materials/studocu/exams` (including mocks and
solutions), or `materials/studocu/other`. Files remain local and retain their
original bytes. Consult the skill's collection reference for the selection schema.
Exact matches in the same group, type and known year share one original through
a private alias. Each selected document retains its own source identity and URL.
Changing a document's classification or refreshing its original separates aliases
when they no longer match; previous versions remain in private history.
When an existing selection is planned again, unchanged duplicate originals are
consolidated. Edited or missing files are preserved for review.

Local study material can cite student uploads. Publishing rejects included
Studocu-backed sources; this source check cannot identify uncited copied text or
replace a review of the published content.
They run in your local agent, using the connected
MCP tools to read course sources. The CLI validates and stores the resulting local
files; it does not run an AI model.

## Publish a study website

The optional `publish-course` skill makes a prepared site accessible from a phone
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
audio and arbitrary files stay local. Git itself is not required: the publisher
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
  app/                      Shared Study, Exercises and optional Lecture Notes website
    content.json            Optional source-backed Study content
    exercises.json          Optional prepared exercise guidance
  audio/                    Optional category audio derived from the prepared website
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

Ask `prepare-study` to create or extend the Study workspace in `app/`. Units follow the course's
lecture/week sequence when useful, or use consistent topics. For a single course, use a flat list or one category level followed by topics,
including several topics in one week. Every unit has:

- A concise explanation with source links, assumptions and worked examples.
- Editable LaTeX formulas and inline variables, diagrams, code or comparison tables where they explain the concept.
- Flip cards with arrow navigation, Space to flip and 1/2 for Again/Got it.
- Practice questions with exactly four options, one justified answer and feedback for every option.

The agent uses stored material first, so local content edits work offline. Ask for
an upstream refresh when you want new course content; an existing check is reused
within the same request. Unchanged units and reviewed material are retained.

The skill audits objective coverage, technical accuracy and distractors. Its
STE-inspired English uses short, direct sentences while retaining necessary terms
and conditions. The design contract uses TUM blue/navy with quiet reading surfaces,
local fonts, light/dark themes, keyboard navigation and a phone layout. The outline
collapses using a midpoint boundary arrow revealed on hover or keyboard focus;
touch screens keep a visible control. On phones it opens a viewport overlay from
any reading position, with its own scroll and Escape to close. Theme stays in the
outline; the reset icon is on the course home. A Next link follows the active
activity at the end of each view.

Revision combines flashcards and practice from topics you select. Open Revision in
the outline, choose topics and collapse the checklist when ready. It reuses the
course's categories; selecting a category includes all its topics, and a mixed
checkbox shows a partly selected category. Revision reuses the
original items, sources and progress; selecting or removing topics never clears
your results. The topic selection is remembered locally for this course.

The topic picker and its nested categories collapse independently. You can select a
whole category while it is closed; its count and mixed state reflect the selection.
At End of set, outlined question rows include a Review action and chevron. Click
one to review it in a popup. Closing the popup returns
you to the same results row without changing progress.

The website uses Atkinson Hyperlegible Next for headings, explanations and controls.
Code and mathematical notation retain their specialist fonts. Equations adapt to
their container and keep local horizontal scrolling for indivisible wide expressions.
Use `\(v_i\)` in teaching text for inline variables and short expressions (JSON:
`"Use \\(v_i\\)."`). They compile locally to native MathML, including in tables,
glossaries, cards, questions and feedback. Code and dollar signs stay literal.

Select text in Content, Flashcards or Practice, then click **Comment** to record what is unclear.
You can also use Ctrl/Command+Alt+M after selecting text. The local preview saves
notes in `.tum-mcp/comments.json`, separately from learning progress. Click a
numbered passage marker or highlighted text to open its notes beside the quote.
Markers sit beside section headings or the current card/question position.
Notes can be edited, resolved or reopened; changed passages retain their original quotes.
Revision notes retain their original topic and card/question identity.

Tell your agent: **“Address the open comments in this study project.”** The skill
reads the notes, checks the cited material, improves the affected explanation and
verifies the result before recording a resolution. Notes and status changes sync
automatically while the preview is open. Your draft is kept if a note changes
elsewhere; choose Use latest or Keep mine before saving. Reload after the agent
rebuilds the teaching content.

Content lives in `app/content.json`; shared renderer modules and CSS keep the
site extensible. Source hashes identify affected units. A stale source stops a
build until the explanation is reviewed. Unchanged units retain their revision;
revised questions receive separate progress. Customized templates are preserved
and reported, so the agent must review compatibility when extending them.

```sh
tum-mcp study inspect ./pse-ws26
tum-mcp study build ./pse-ws26
```

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

## Prepare weekly exercises

Ask `prepare-exercises` to prepare released weekly sheets in the same app. Study
and Exercises can be prepared in either order. When both exist, a selector at the bottom of the sidebar
switches workspaces and remembers the current place. On phones it lives inside the
open course outline; there is no second switch in the reading area. Exercises are
listed directly under sheets, optionally grouped by category.

The original statement and subparts come first. Students can solve on paper, mark
an exercise Reviewed, reveal a worked solution directly, or open **Guidance**.
Prepared guidance offers one conceptual step, requested hints and specific repair
feedback. Numeric checks state units/tolerance; choice checks have four options.
Fillable tables check numeric cells and explicit text variants individually. Graph
questions support node/edge selections and ordered paths with a visible diagram.
Line graphs allow sample-point placement, coordinate edits and keyboard adjustment.
Long math and programming work use saved writing areas and prepared rubrics; code
is never executed, and symbolic work, proofs and programs are not automatically
graded. Arbitrary graph drawing can use paper and rubric comparison. Typing, hints and step-by-step guidance are optional. Reviewed records an
action, not mastery or an assessment result.

Drafts and assistance stay in this browser. Editing a checked answer clears its
verdict. Semantic changes start fresh progress for only that exercise, while retaining older
browser records; source-hash review alone preserves progress.
Reset on each workspace home affects only that workspace. Exercise passage comments
use the existing private comment service; hosted exports do not expose it.

Existing `study/` projects continue to work. New projects use `app/`. To upgrade a
verified legacy layout explicitly, run `tum-mcp study build PROJECT --upgrade-layout`.
It keeps the original tree at `.tum-mcp/layout-backup/`, preserves the course identity,
learning revisions, comments, settings and personal files, and stops on customized
generated files, an occupied backup or two layouts. Repeating a completed upgrade
is a no-op. Do not create `app/` alongside an existing `study/` by hand.

## Create and maintain audio notes

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

## Packaged app template

The shared web-app template is packaged in `bundled/course_app/site/`, separately from skill instructions.
It includes the shell, navigation, flip cards, practice, diagrams and styling.
Agents author course content in `app/content.json`; `study build` installs the
shared template, preserves customized files and checks sources. This keeps new
course sites consistent without rebuilding the interface. `tum-mcp study template`
shows the bundled files and their combined revision for reproducible development.

## Try the component template

After installing a locally built development artifact:

```sh
tum-mcp study demo ./component-preview
tum-mcp study serve ./component-preview
```

This creates one small Study unit and one exercise covering prose, code, tables,
formulas, graph/process diagrams, cards and response controls. It is a reusable
component template, not necessarily a good teaching or question-authoring example.
Actual course authoring follows reviewed sources and the preparation skills. Rich
learning pilots stay in private test fixtures.
It uses no campus account. An existing edited demo is preserved.

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
