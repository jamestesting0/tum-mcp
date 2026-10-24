# TUM MCP

Connect your coding agent to TUM Moodle, Artemis, and Zulip. Runs locally with
36 tools and seven workflow skills. Unofficial; independent of TUM and OpenAI.

**Version 0.5.0** · [npm package](https://www.npmjs.com/package/@jamestesting888/tum-mcp/v/0.5.0)

## Agent setup

Paste this into your coding agent:

```text
Install @jamestesting888/tum-mcp on this computer. Check Node.js is 22.14+.
Run npm install --global @jamestesting888/tum-mcp@0.5.0, then:
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
npm install --global @jamestesting888/tum-mcp@0.5.0
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

## Privacy and updates

Sessions use encrypted local files with an owner-restricted key file. This avoids
Keychain prompts but provides less protection than a native credential store:
someone who obtains both files can decrypt them. Existing native-store records,
downloads, and customizations are preserved; reconnect to use the new storage.
The separate Moodle-only installer retains its native credential-store behavior.

Retrieved excerpts can reach your agent's AI provider. Moodle's document cache
is unencrypted and limited to 30 days / 1 GiB; downloads remain until deleted.

Update with `npm install --global @jamestesting888/tum-mcp@latest`, then rerun
setup for your client. Conflicting customized configuration is kept for review.
See the [guide and verification limits](docs/tum-mcp.md), [setup and troubleshooting](docs/setup.md),
[development guide](docs/development.md).

[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
