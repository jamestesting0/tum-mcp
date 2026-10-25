# Changes

## 0.6.0 — unreleased

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
- Recognize occupied preview ports on Windows. Reuse isolated test fixtures,
  retain native/platform coverage and expose slow tests and failures in CI.
- Group Artemis and Zulip implementation by provider, retaining read-only campus
  tools and Moodle compatibility. Fix OCR with aliased macOS temporary paths.

Upgrading does not rebuild personal study sites automatically. Ask your agent to
update the prepared website; customized renderer files are preserved for review.
Audio, source materials, comments and study projects remain outside package
installation/removal. The public npm version is still **0.5.0** until this candidate
is published.
