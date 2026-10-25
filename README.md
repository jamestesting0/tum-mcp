# TUM MCP

Connect your coding agent to Moodle, Artemis and Zulip. Read course content and
build a private, source-backed study workspace. Unofficial; independent of TUM.

**Development version: 0.6.0, unreleased.** The public npm release remains 0.5.0.
The study workflows below are included in this checkout and its locally built package.

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

## Read and study

| Source | Available content |
| --- | --- |
| Moodle | Materials, pages, announcements, forums, original downloads and cited PDF pages |
| Artemis | Lectures, text/online/video units, student slide PDFs, released exercise statements and permitted own feedback |
| Zulip | Selected course channels, discussion search and cited catch-up |

Campus access is read-only. Exercise start, deployment, execution, submission,
posting and read-state changes are unavailable.

The development package has **four skills**, with source details loaded as needed:

| Skill | Purpose |
| --- | --- |
| `read-content` | Retrieve and explain content across all three websites |
| `init-study` | Initialize one explicitly chosen course, reusable materials and course-specific `AGENTS.md` |
| `update-study` | Compare upstream sources, preserve edits and identify outdated learning units |
| `prepare-study` | Build or extend `study/` with explanations, formulas, visuals, flashcards and practice |

Ask your agent: “Initialize a study project for **[exact course and semester]**,
then prepare its study website.” The course must be available through your
connections. Each project contains one course. [Study workflow and local demo](docs/study.md).

## Sign-in and session privacy

Sign-in and MFA happen in a temporary browser window. Only service-owned session
cookies are retained; identity-provider cookies are discarded when it closes.
Sessions stay on your computer in encrypted files with owner-restricted keys.
Configured local clients share those connections and selected scopes.

## Course content and study privacy

The agent retrieves material for your request through your configured AI provider.
Moodle's document cache expires after 30 days and is capped at 1 GiB. Saved
originals and study projects stay local until you remove them.

Study sites run on your computer without analytics, external fonts or CDNs.
Card ratings and practice results stay in browser storage, separated by course
and content revision. Updating course material preserves your notes and flags
changed sources before rebuilding dependent units.

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
