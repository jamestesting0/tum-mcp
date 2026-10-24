# TUM MCP

Connect your coding agent to TUM Moodle, Artemis, and Zulip. Runs locally with
36 tools and three website skills. Unofficial; independent of TUM and OpenAI.

[npm package](https://www.npmjs.com/package/@jamestesting888/tum-mcp)

## Agent setup

Paste this into your coding agent:

```text
Install @jamestesting888/tum-mcp on this computer. Check Node.js is 22.14+.
Run npm install --global @jamestesting888/tum-mcp@latest, then:
  tum-mcp setup --client codex
Use --client claude, cursor, antigravity, or generic for a different client.
Preserve existing settings and customized skills. Follow the activation steps.
Help me run tum-mcp connect in an interactive terminal and choose services.
I will complete TUM sign-in/MFA in the browser. Never request secrets in chat.
Ask which Artemis courses and Zulip channels to enable before reading content.
Run tum-mcp doctor to explain what is available and what still needs setup.
```

## Quick start

You need **Node.js 22.14+**, **a Chromium browser**, and your TUM account.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup --client codex
tum-mcp connect
tum-mcp doctor
```

Choose services with **Space**, then **Enter**. Choose an installed browser when
prompted. Moodle, Artemis and Zulip use the same flow; only selected tabs open.
Complete sign-in/MFA there; no Zulip API key is needed.
New Artemis/Zulip accounts need explicit [course and channel scopes](docs/tum-mcp.md#connections-and-scopes).

| Client | Setup |
| --- | --- |
| Codex | `--client codex` · plugin and workflow skills; enable/restart when prompted |
| Claude Code | `--client claude` · MCP registration and workflow skills |
| Cursor | `--client cursor` · MCP registration; reload MCP servers |
| Google Antigravity | `--client antigravity` · MCP registration; reload MCP servers |
| Other local MCP clients | `--client generic` · configuration for manual installation |

Cursor and Antigravity workflow skills can be [exported for manual installation](docs/tum-mcp.md#client-and-skill-setup).
Works on macOS, Windows, glibc Linux x86_64/ARM64, and WSL 3.x. From WSL,
Windows browsers open on the Windows desktop. Use
`tum-mcp setup --client cursor --host windows` to register a Windows client
against that same WSL backend; replace `cursor` with your client.
[WSL setup and requirements](docs/setup.md#wsl).

Setup supplies a private Python runtime. Git is optional for assignment workspaces;
Docker is optional for isolated assignment tests. No native keyring is needed by
new campus connections, including Linux x86_64 and ARM64.

The agent sees one skill per website: **tum-moodle**, **tum-artemis** and
**tum-zulip**. Each routes to the relevant workflow and loads detailed guidance
only when needed.

## Available tools

| Service | What your agent can do |
| --- | --- |
| Moodle | Search materials and forums, cite PDF pages, download originals |
| Artemis | Read exercises and permitted feedback, prepare existing-participation workspaces, run approved local tests, preview submissions |
| Zulip | Search selected channels and catch up on course discussions with citations |

Remote start, push, submit, and rebuild are disabled. Zulip posting and DMs are
unavailable. `doctor` checks local readiness; `doctor --live` verifies saved
sessions, and `doctor --json` gives machine-readable results. Saved configuration
and active client connections are reported separately.

## Privacy

Sign-in and MFA happen in a temporary browser window. Only service-owned session
cookies are saved; identity-provider cookies are discarded when that window
closes. Sessions stay on your computer in encrypted files with owner-restricted
keys, shared by your configured local clients.

Your agent retrieves course content for your requests and uses excerpts through
your configured AI provider. Moodle's local document cache expires after 30 days
and is capped at 1 GiB. Downloaded originals stay local until you delete them.

## Updates

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp update
```

npm downloads the new package; `update` prepares its runtime and refreshes your
previously configured clients. Sessions, scopes and downloads carry forward.
User-edited entries or skills are preserved and reported for review. Reload the
client; update/reinstall the local plugin in Codex if it still uses a cached copy.
Use `setup --client NAME` to register a new client.

## Removal

```sh
tum-mcp uninstall --all
npm uninstall --global @jamestesting888/tum-mcp
```

This removes managed registrations and unchanged skills while keeping settings,
sessions, cache, downloads and assignment work. To remove generated runtimes too,
close coding clients and add `--purge-runtime`. Add `--forget-credentials` to
remove saved local sessions and Git tokens. [Removal details](docs/setup.md#update-and-remove).

See the [guide and verification limits](docs/tum-mcp.md), [setup and troubleshooting](docs/setup.md),
[development guide](docs/development.md).

[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
