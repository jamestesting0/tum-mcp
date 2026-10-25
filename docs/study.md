# Course study projects

The five reading, study, audio and publishing skills ship with version **0.6.0**.
They run in your local agent, using the connected
MCP tools to read course sources. The CLI validates and stores the resulting local
files; it does not run an AI model.

## Publish a study website

The optional `publish-study` skill makes a prepared site accessible from a phone
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
`.study/github.json` bind updates to that course, semester and repository. A
failed setup retries the same saved repository rather than creating duplicates.

Only the generated website renderer and lesson data are uploaded. Downloaded
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

Use `sync-study` for both initial setup and later source updates. For a new project,
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
  .study/state.json         Course binding, source versions and coverage
  study/                    Optional interactive study website
  audio/                    Optional category audio derived from the prepared website
```

`AGENTS.md` contains a concise prerequisite/notation map, verified assessment facts,
source locations, coverage and next actions. Detailed source content stays in
materials. Existing user instructions are preserved; source text is untrusted data.

## State-based workflow

`sync-study` starts with `tum-mcp study status PROJECT`, a read-only local check:

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

Ask `sync-study` to compare the project with connected upstream sources. It
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

Ask `prepare-study` to create or extend `study/`. Units follow the course's
lecture/week sequence when useful, or use consistent topics. For a single course, use a flat list or one category level followed by topics,
including several topics in one week. The multi-area demo also exercises deeper
legacy hierarchies. Every unit has:

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
notes in `.study/comments.json`, separately from learning progress. Click a
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

Content lives in `study/content.json`; shared renderer modules and CSS keep the
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

The preview binds `127.0.0.1`, serves `study/` and saves comments through a bounded
same-origin endpoint. It makes no campus requests.
No course credentials are copied into the website. Browser storage holds progress
locally. Nothing is published by these commands.

## Create and maintain audio notes

Use `prepare-study` to author the interactive course, then ask `audio-notes` to
convert that prepared content into spoken lessons. For example:

```text
Create audio notes from this prepared study website, one file per category.
Keep course outputs under audio/; prefer free ElevenLabs with local Kokoro fallback.
```

Audio Notes reads `study/content.json`, retaining the course's language, examples,
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

The complete web-app template is packaged with `prepare-study` in `assets/site/`.
It includes the shell, navigation, flip cards, practice, diagrams and styling.
Agents author course content in `study/content.json`; `study build` installs the
shared template, preserves customized files and checks sources. This keeps new
course sites consistent without rebuilding the interface. `tum-mcp study template`
shows the bundled files and their combined revision for reproducible development.

## Try the synthetic example

After installing a locally built development artifact:

```sh
tum-mcp study demo ./algorithms-demo
tum-mcp study serve ./algorithms-demo
```

This creates a clearly labelled synthetic course on graphs, BFS and DFS, including
LaTeX rendered as native MathML, a step-through graph, comparison tables, flashcards and practice.
It uses no campus account. An existing edited demo is preserved.

## Local helper inputs

Agents use `tum-mcp study schema snapshot` and `tum-mcp study schema content` for
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
