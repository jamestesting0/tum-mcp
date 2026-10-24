# TUM MCP

Use TUM Moodle, Artemis, and Zulip from your coding agent. Runs locally with
36 tools and seven workflow skills. Unofficial; independent of TUM and OpenAI.

## Agent setup

Paste this into your coding agent:

```text
Install @jamestesting888/tum-mcp@0.4.0 from npm on this computer.
Check that Node.js is at least 22.14, then run:
  npm install --global @jamestesting888/tum-mcp@0.4.0
  tum-mcp setup --client codex
For Claude Code, use --client claude instead; other MCP clients use --client generic.
Preserve existing settings, plugins, sessions, downloads, and customized skills.
Follow the printed enablement/restart step. Then help me run tum-mcp connect campus
in an interactive terminal so I can complete TUM sign-in/MFA in Chrome.
Ask which Artemis courses and Zulip channels to enable before reading content.
For Moodle, use the plugin's separate Moodle sign-in. Never request secrets in chat.
```

## Manual setup

You need **Node.js 22.14+**, **Google Chrome**, and your TUM account.

```sh
npm install --global @jamestesting888/tum-mcp@0.4.0
tum-mcp setup --client codex
tum-mcp connect campus
```

`campus` connects **Artemis and Zulip together**. Complete sign-in and MFA in
Chrome; no Zulip API key is required. Moodle sign-in is separate: ask the loaded
plugin, **“Sign in to TUM Moodle.”** Follow any client enablement/restart instruction.
Disable the older Moodle plugin when enabling TUM MCP to avoid duplicate tools.

Select the courses and channels the backend may read. `status` shows account IDs;
`discover` lists metadata, and `scope` saves your choices. New accounts start
without content access. See the [connection and scope commands](docs/tum-mcp.md#connections-and-scopes).

Setup downloads a private Python runtime; consumers do not need Python or uv.
Git is needed for assignment workspaces and Docker for isolated assignment tests.
Linux also needs an unlocked Secret Service keyring in its desktop D-Bus session.

## What you can do

| Service | Available |
| --- | --- |
| Moodle | Read/search course materials and forums, cite PDF pages, download originals |
| Artemis | Read released programming exercises and permitted feedback; prepare existing-participation workspaces, run approved local tests, preview submissions |
| Zulip | Search selected channels, read topics, and summarize recent discussions with citations |

Try “Find the lecture section about scheduling,” “Read this Artemis exercise,”
or “Catch me up on the selected Zulip channel.” Personal records, participation
feedback, and workspace writes require their own explicit permissions.

**0.4.0 is a public pilot.** Remote start, push, submit, and rebuild are disabled.
It cannot post to Zulip or read DMs. A submission preview never submits anything.
macOS ARM64 browser sign-in and live reads are verified; Windows, Intel Mac, and
Linux desktop checks remain incomplete. Bootstrap targets and test evidence are
listed in the [detailed guide](docs/tum-mcp.md#build-and-test-the-local-package).

## Privacy

Sessions stay local and encrypted, with keys in macOS Keychain, Windows Credential
Manager, or Linux Secret Service. There is no plaintext credential fallback.
Relevant excerpts can be sent to your agent's configured AI provider. Zulip chat
text is fetched live; Moodle's document cache is unencrypted and limited to
30 days / 1 GiB. Downloads remain until deleted.

Use the installed `tum-mcp` command for sign-in to keep the requesting runtime
consistent. Your OS may ask for credential-store access. See
[storage details](docs/credential-storage-options.md).

## Update and support

Install the reviewed version you want, then rerun the client setup:

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup --client codex
```

Existing Moodle sessions and downloads are preserved. Customized configurations
are kept for review. `tum-mcp doctor` checks local prerequisites; it does not
verify live authentication.

[Detailed guide](docs/tum-mcp.md) · [Moodle-only setup](docs/setup.md) ·
[Development](docs/development.md) · [Report a problem](https://github.com/jamestesting0/tum-moodle-integration/issues)

## License

[MIT](LICENSE). The TUM logo retains its original rights; see [NOTICE](NOTICE).
No trademark rights are granted.
