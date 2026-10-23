# TUM Moodle for Codex

Read, search, and download your TUM Moodle materials directly in Codex.
Runs locally on **macOS, Windows, and Linux**. No Moodle API token is needed.

[Agent setup (recommended)](#agent-setup) · [Manual installation](#install) ·
[Setup by platform](docs/setup.md) ·
[Examples](#use-it) · [Update](#update) · [Development](docs/development.md)

This is an unofficial project, independent of TUM and OpenAI.

## Agent setup

**Use Luna Fast for installation.** Select Luna with Fast mode, where available,
then paste this prompt into Codex on the target computer:

```text
Install https://github.com/jamestesting0/tum-moodle-integration on this computer.
Reuse this matching checkout, otherwise shallow-clone to ~/tum-moodle-integration;
do not scan my computer or overwrite existing files. Check docs/setup.md only
for missing prerequisites; use an existing trusted package manager if needed.
Run uv run scripts/install.py --json and follow its next_actions.
Preserve local changes, other plugins, sessions, and downloads. No developer setup.
Install first, prompt for TUM sign-in/MFA in Chrome, then offer an optional live
course check. Never request credentials in chat or read courses without opt-in.
```

## What it does

- Reads current-semester courses, PDFs, slides, course pages, and forums.
- Searches indexed material and cites Moodle links and page numbers.
- Downloads original files into `Downloads/TUM Moodle/course-<id>/`.
- Uses optional Tesseract OCR for scanned documents.
- Reads your own grades, feedback, submissions, or messages only when requested.

Recordings remain links. It never submits assignments, starts quizzes, posts,
or sends messages. Normal Moodle viewing logs and completion rules still apply.

## Install

For manual installation, follow these steps.

You need **Git, uv, Google Chrome, your TUM account**, and a Codex client with
local plugin support. A separate Python installation is not needed.
See [platform prerequisites](docs/setup.md#prerequisites) first.

Run these commands in Terminal or Windows PowerShell:

```text
git clone --depth 1 https://github.com/jamestesting0/tum-moodle-integration.git
cd tum-moodle-integration
uv run scripts/install.py
```

1. Follow any enablement or restart step printed by the installer.
2. Ask **“Sign in to TUM Moodle.”** Complete sign-in and MFA in Chrome.
3. Optionally ask **“List my current-semester courses to check the connection.”**

The installer checks local tool startup and uses the Codex CLI to enable the plugin
when supported. It reuses healthy installations and cached downloads. First-time
Python/dependency downloads depend on your connection. Each user signs in separately.

**Testing:** automated checks cover macOS, Windows, and Ubuntu. Interactive
Codex installation and TUM sign-in have been verified on macOS; Windows/Linux
desktop sign-in still needs a hands-on check.

## Use it

- “Read Lecture 1 and cite the PDF page numbers.”
- “Index this course, then find mentions of scheduling.”
- “Show the latest discussions in its announcements forum.”
- “Download this lecture to my computer.”
- “Show my downloaded Moodle files.”
- “Sign out of Moodle and clear the cache.”

Search uses the local index. Ask Codex to index or refresh a course first;
it follows batch cursors and reports incomplete coverage.

## Privacy and storage

Cookies stay local, encrypted with a key in the OS credential store:
**macOS Keychain**, **Windows Credential Manager**, or **Linux Secret Service**.
There is no plaintext credential fallback. Relevant excerpts are sent to your
configured Codex model.

| Platform | Runtime, session, and cache |
| --- | --- |
| macOS | `~/Library/Application Support/TUMMoodle/` |
| Windows | `%LOCALAPPDATA%\TUMMoodle\` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/TUMMoodle/` |

The cache is unencrypted, limited to **30 days / 1 GiB**. Explicit downloads
remain until deleted; signing out or clearing the cache does not remove them.
Files are limited to **50 MiB** each. OCR may misread equations or diagrams.

## Update

Paste this one-line prompt into Codex:

```text
Update my TUM Moodle plugin from https://github.com/jamestesting0/tum-moodle-integration: find my checkout, preserve local changes and session data, get scripts/update.py with a fast-forward-only pull if needed, run it with uv, and tell me whether I need to restart Codex or complete a manual step.
```

Or run this from your checkout:

```sh
uv run scripts/update.py
```

This pulls the latest code and runs the same checked installer. It stops if you
have local changes and preserves your session and downloads. Follow any printed
restart/action step. Older checkouts need `git pull --ff-only` once to
get the updater. [Update details](docs/setup.md#updates).

[Problems?](docs/setup.md#troubleshooting) · [Uninstall](docs/setup.md#uninstall) ·
[Tests and architecture](docs/development.md)

## License

[MIT](LICENSE). The TUM logo retains its original rights; see [NOTICE](NOTICE)
and [logo source](plugin/assets/README.md). No trademark rights are granted.
