# Changes

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
