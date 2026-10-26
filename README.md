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
tum-mcp setup --client codex
tum-mcp connect
tum-mcp doctor
```

Choose `codex`, `claude`, `cursor`, `antigravity` or `generic` as the client.
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
| `audio-notes` | “Turn the prepared lessons into audio notes.” |
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

Install only the workflows you need, then reload your client:

```sh
tum-mcp install lecture          # Prepare Lecture + TUM-Live tools and local ASR
tum-mcp install lecture --no-asr # Use captions/imported WebVTT instead
tum-mcp install studocu         # Supplementary Studocu collection workflow
tum-mcp extensions status
```

**Lecture Notes** captures the professor's extra explanations, examples and
caveats, with timestamp links. It starts with transcripts and lecture materials;
only critical visuals need recording frames. Local recognition uses Apple Silicon
acceleration or a separate CPU runtime on supported hosts.
[Lecture Notes and recognizer requirements](docs/lecture-notes.md).

**Studocu** adds public search and reviewed import of permitted original PDFs you
save in your browser. Search coverage is incomplete; browser credentials stay out
of the integration. These supplementary materials remain for personal use and
cannot be included in published sites. [Studocu workflow](docs/study.md#studocu-materials).

Remove either extension with `tum-mcp uninstall lecture` or
`tum-mcp uninstall studocu`. Notes, evidence and customizations are preserved.

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
