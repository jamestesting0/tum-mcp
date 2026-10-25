# TUM MCP

Connect your coding agent to Moodle, Artemis and Zulip. Read course content and
build a private, source-backed study workspace. Unofficial; independent of TUM.

**Development version: 0.6.0, unreleased.** The public npm release remains 0.5.0.
The study workflows below are included in this checkout and its locally built package.
[Release notes](CHANGELOG.md).

## Agent setup

Paste this into your coding agent to install the published package:

```text
Install @jamestesting888/tum-mcp on this computer. Check Node.js is 22.14+.
Run npm install --global @jamestesting888/tum-mcp@latest, then:
  tum-mcp setup --client codex
Use --client claude, cursor, antigravity, or generic for a different client.
Preserve existing settings and customized skills. Follow the activation steps.
Help me run tum-mcp connect in an interactive terminal and choose services.
I will complete sign-in/MFA in the browser. Never request secrets in chat.
Ask which Artemis courses and Zulip channels to enable before reading content.
Run tum-mcp doctor to explain what is available and what still needs setup.
```

For the unreleased workflows, [build and install the local artifact](docs/development.md#checks).

## Connect

You need **Node.js 22.14+**, **a Chromium browser**, and your TUM account.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup --client codex
tum-mcp connect
tum-mcp doctor
```

Select services with **Space**, then **Enter**. Choose an installed browser and
complete sign-in there. Only selected tabs open; Zulip needs no API key.
Enable the [course and channel scopes](docs/tum-mcp.md#connections-and-scopes) you want to use.

| Client | Setup |
| --- | --- |
| Codex | `--client codex` · plugin and skills; enable/restart when prompted |
| Claude Code | `--client claude` · MCP registration and skills |
| Cursor | `--client cursor` · MCP registration; reload MCP servers |
| Google Antigravity | `--client antigravity` · MCP registration; reload MCP servers |
| Other MCP clients | `--client generic` · configuration for manual installation |

Cursor and Antigravity can use [manually exported skills](docs/tum-mcp.md#client-and-skill-setup).
Supports macOS, Windows, glibc Linux x86_64/ARM64 and WSL 3.x. In WSL, sign-in
opens a Windows browser. Add `--host windows` to setup for a Windows client that
uses the WSL backend. [Browser and WSL setup](docs/setup.md#wsl).

Setup supplies a private Python runtime. New connections use encrypted local
files and need no native keyring, Git or Docker.

For optional GitHub Pages publishing, install [GitHub CLI](https://cli.github.com/)
and sign in on the same computer where the agent runs:

```sh
gh auth login --hostname github.com
tum-mcp doctor --live
```

`doctor` reports whether GitHub CLI is available; `--live` also verifies its active
GitHub authentication. No token needs to be pasted into the agent or stored by
TUM MCP. A coding platform's GitHub connector does not automatically authenticate
the local CLI. GitHub is optional for local study and campus access.

## Read and study

| Source | Available content |
| --- | --- |
| Moodle | Materials, pages, announcements, forums, original downloads and cited PDF pages |
| Artemis | Lectures, text/online/video units, student slide PDFs, released exercise statements and permitted own feedback |
| Zulip | Selected course channels, discussion search and cited catch-up |

Campus access is read-only. Exercise start, deployment, execution, submission,
posting and read-state changes are unavailable.

The development package has **five skills**, with source details loaded as needed:

Their maintained source is in this repository at
[`src/tum_mcp/bundled/skills/`](src/tum_mcp/bundled/skills/). Client setup installs
managed copies; edit or review the repository source when developing the package.

| Skill | Purpose |
| --- | --- |
| `read-content` | Retrieve and explain content across all three websites |
| `sync-study` | Initialize a chosen course or update its existing project, preserving materials and edits |
| `prepare-study` | Build or improve study sites and address passage comments |
| `audio-notes` | Convert prepared course content into maintained category audio under `audio/` |
| `publish-study` | Publish a study website using a private GitHub repository and maintain later updates |

Ask your agent: “Initialize a study project for **[exact course and semester]**,
then prepare its study website.” The course must be available through your
connections. The same `sync-study` skill detects existing state and updates it.
Each project contains one course. [Study workflow and local demo](docs/study.md).
Launch its prepared website from the course project folder:

```sh
tum-mcp study
```

It opens your browser at `http://127.0.0.1:8765`. Press Ctrl+C in the terminal to stop.
For access from your phone, ask your agent to publish the prepared website.
This optional workflow uses GitHub CLI authentication and an eligible paid GitHub
plan. The repository is private, but the GitHub Pages website is public. Review
the intended content before publishing. Later builds update the same site, and
`tum-mcp study` also prints its hosted URL. [Publishing](docs/study.md#publish-a-study-website).
Then ask for audio notes to turn the prepared content into one spoken lesson per
category. Existing audio is compared with the current course so only missing or
changed categories need generation.

## Sign-in and session privacy

Sign-in and MFA happen in a temporary browser window. Only service-owned session
cookies are retained; identity-provider cookies are discarded when it closes.
Sessions stay on your computer in encrypted files with owner-restricted keys.
Configured local clients share those connections and selected scopes.

## Course content and study privacy

The agent retrieves material for your request through your configured AI provider.
Moodle's document cache expires after 30 days and is capped at 1 GiB. Saved
originals and study projects stay local until you remove them, except for website
files you explicitly choose to publish.

Study sites run on your computer without analytics, external fonts or CDNs.
Card ratings and practice results stay in browser storage, separated by course
and content revision. Updating course material preserves your notes and flags
changed sources before rebuilding dependent units.
Passage comments are saved in the course project; your agent reads them when you
ask it to address feedback.

## Update

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp update
```

`update` prepares the invoked package's runtime and refreshes configured clients.
Sessions, scopes and downloads carry forward. User-edited entries and skills are
preserved and reported for review. Reload the client; refresh its cached plugin
if needed. Study sites are updated separately through the study workflows.

## Remove

```sh
tum-mcp uninstall --all
npm uninstall --global @jamestesting888/tum-mcp
```

Managed registrations and unchanged skills are removed. Settings, sessions,
downloads and study projects are preserved. After closing clients, add
`--purge-runtime` to remove generated runtimes or `--forget-credentials` to
remove saved local sessions and historical Git tokens. [Removal details](docs/setup.md#update-and-remove).

[Guide](docs/tum-mcp.md) · [Setup](docs/setup.md) · [Study workflows](docs/study.md) · [Development](docs/development.md)

[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
