# TUM MCP

Connect your coding agent to **Moodle, Artemis, Zulip and TUMonline**. Read course
sources with citations and turn them into a private study app. Unofficial and
independent of TUM.

[**npm package**](https://www.npmjs.com/package/@jamestesting888/tum-mcp) ·
[Release notes](CHANGELOG.md) · [Setup guide](docs/setup.md)

## Get started

Requires **Node.js 22.14+**, a Chromium browser and your TUM account.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup
tum-mcp connect
tum-mcp doctor
```

Select `codex`, `claude`, `cursor`, `antigravity` or `generic`, or pass `--client NAME`.
Follow the activation/restart instructions. In `connect`, select services with
**Space**, then **Enter**, and complete sign-in/MFA in the browser. Never paste
credentials into chat. Setup supplies its own Python runtime; Git, Docker and a
native keyring are unnecessary.

Works on macOS, Windows, glibc Linux x86_64/ARM64 and WSL. For a Windows client
using a WSL backend, add `--host windows` to setup.
[Browser and platform details](docs/setup.md).

## Read and study

Ask your agent to explain course material, find announcements or catch up on a
Zulip channel. Campus access is read-only and follows your account permissions;
submissions, posting and exercise execution are unavailable.

| Workflow | Example request |
| --- | --- |
| `read-content` | “Explain this week's lecture with source citations.” |
| `sync-course` | “Set up a project for this course and collect its materials.” |
| `prepare-study` | “Build lessons, flashcards and practice in a study website.” |
| `prepare-exercises` | “Add guided exercises from this week's released sheet.” |
| `publish-course` | “Publish my reviewed study site for phone access.” |

Each project holds one course. Run `tum-mcp study` in its folder to open the app.
Ask the agent to refresh it when sources change or address comments left in the
app. [Study guide and demo](docs/study.md).

TUMonline currently provides study names/degrees, public course catalog metadata
and partial course curriculum positions. The catalog does not show enrollments.
Grades, exams, progress and full curricula are unavailable. Review its local
account policy with `tum-mcp manage tumonline`.
[TUMonline permissions](docs/tum-mcp.md#tumonline-permissions).

## Optional extensions

Run `tum-mcp install` to choose extensions, then reload your client.

| Extension | Skill added | What it offers |
| --- | --- | --- |
| `lecture` | `prepare-lecture` | Lecture Notes with the professor's extra explanations, timestamps and selected critical visuals. Prefers transcripts and slides; local recognition is optional. |
| `studocu` | `sync-studocu` | Search and collect selected supplementary PDFs saved in your browser. Personal use only; excluded from published sites. |
| `audio-notes` | `audio-notes` | Turn prepared Study lessons into concise audio tracks, with resumable generation and coverage tracking. Voice setup happens when used. |

Use `tum-mcp status` to see installed workflows and `tum-mcp uninstall` to remove
them. Named commands also work, such as `tum-mcp install audio-notes` and
`tum-mcp uninstall lecture`. Existing notes, audio and customizations are retained.
Audio Notes needs no additional campus sign-in. Studocu uses your own browser.

[Lecture and recognition](docs/lecture-notes.md) ·
[Studocu collection](docs/study.md#studocu-materials) · [Setup details](docs/setup.md)

## Privacy, updates and removal

Sessions are encrypted locally. Your agent uses your configured AI provider to
process selected material. Publishing requires local GitHub CLI authentication
and an eligible GitHub plan: **the repository is private; the website is public**.
Review content before publishing. [Publishing details](docs/study.md#publish-a-study-website).

```sh
tum-mcp update    # Upgrade the package and refresh managed clients
tum-mcp uninstall
```

Sessions, downloads, course projects and edited skills are preserved. Reload the
client after updates. [Update and removal options](docs/setup.md#update-and-remove).

[Command guide](docs/tum-mcp.md) · [Development](docs/development.md) ·
[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
