# Changes

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
- Lecture Notes: recording times open from the sources of each passage and figure
  instead of appearing in the text, and the sidebar lists lectures only.
- Add a Contents button to Study, Exercises and Lecture Notes. It lists the page's
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
  Lecture Notes in the existing course app. Prefer transcripts and supplied
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
