# Desktop setup

This page covers the preserved **Moodle-only** installer. For the combined
Artemis/Zulip/Moodle package, use [campus setup](../README.md#quick-start) and
the [TUM MCP guide](tum-mcp.md). Its unified `tum-mcp connect` uses local-file
keys without native-store prompts; the native-store requirements below apply
only to this older Moodle-only installation path.

[README](../README.md) · [macOS](#macos) · [Windows](#windows) · [Linux](#linux) ·
[Updates](#updates) · [Troubleshooting](#troubleshooting) · [Uninstall](#uninstall)

## Prerequisites

Use your own TUM account and a Codex client that supports local plugin marketplaces.
This package runs on the local computer; it does not connect ChatGPT web.

### macOS

Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), and
[Google Chrome](https://www.google.com/chrome/). Homebrew users can run:

```sh
brew install git uv
brew install --cask google-chrome
```

Git can also come from Apple's Command Line Tools: `xcode-select --install`.
No system Python is needed. For scanned PDFs, optionally install `brew install tesseract`.
Unlock your login keychain if macOS asks. Apple Silicon has been tested locally;
Intel uses the same setup, but has not had a hands-on test.

### Windows

Use a normal, non-administrator PowerShell window. Install prerequisites if missing:

```powershell
winget install --exact --id Git.Git
winget install --exact --id astral-sh.uv
winget install --exact --id Google.Chrome
```

Open a **new PowerShell window** after installation so PATH is refreshed.
uv supplies Python; a separate Python installation is not required. Ensure
`uv --version` works before running the installer. Codex then launches the private
interpreter directly, so it does not depend on PowerShell's PATH.

Windows Credential Manager stores the session-encryption key. Optional OCR needs
[Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html), with its
installation directory on PATH. Restart Codex after changing PATH.

### Linux

Use a graphical desktop session with Google Chrome, Git, uv, and an
unlocked **Secret Service** keyring, such as GNOME Keyring. The keyring must be
available in the same D-Bus session as Codex. A headless SSH session is insufficient
for interactive Moodle sign-in.

For Ubuntu/Debian prerequisites:

```sh
sudo apt-get install git gnome-keyring
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Chrome](https://www.google.com/chrome/) using their official installers.
For OCR, optionally install `sudo apt-get install tesseract-ocr`.
On other distributions, use the equivalent packages. KWallet-only setups need
a running Secret Service provider; the plugin deliberately avoids plaintext
or arbitrary third-party credential backends.

## Install and sign in

Run these commands on the target computer so packaging generates the correct launcher:

```sh
git clone --depth 1 https://github.com/jamestesting0/tum-moodle-integration.git
cd tum-moodle-integration
uv run scripts/install.py
```

Do not copy a Mac's generated plugin or session files to Windows/Linux.

The installer preserves existing marketplace entries and registers the source
under `~/.codex/plugins/local/tum-moodle/`. In PowerShell, `~` refers to your user
profile. You can also install through the Codex CLI:

```text
codex plugin add tum-moodle@personal-local
```

If you renamed your personal source, use its marketplace name instead.
When the installer requests it, restart the desktop app completely: **Cmd+Q** on macOS;
exit all app windows/background instances on Windows/Linux, then reopen it.

After installation, ask **“Sign in to TUM Moodle.”** The agent checks the existing
session before opening Chrome. Complete any TUM login/MFA there. Once connected,
the agent offers an optional course-list check; declining it leaves setup complete.

### Installer results and repair

`uv run scripts/install.py --json` returns one structured result. Progress goes to
stderr; `next_actions` tells the agent exactly what remains.

| Result | Meaning |
| --- | --- |
| `ready` | Local checks pass and the installed plugin is current. Sign-in is separate. |
| `restart_required` | Software setup passed; fully restart Codex once to load it. |
| `action_required` | Follow the prerequisite, keyring, or manual enablement instruction. Completed software stages are retained. |
| `error` | A stage failed; the result includes the failed stage and error. |

Exit codes are 0 for software success, 2 for a required user action, and 1 for an
error. A local MCP check does not prove tools have reloaded in the current chat.
Do not keep restarting or reinstalling while waiting for the user.

If the runtime is damaged, run `uv run scripts/install.py --repair`. This reinstalls
locked runtime packages without removing sessions or downloads. Healthy reruns
check the existing runtime and reuse uv's cache. Native tools can work after the
original checkout is moved/deleted; keep a checkout for future updates.

## Updates

Run `uv run scripts/update.py` from your checkout and follow the printed actions.
It uses your branch's configured upstream and a fast-forward-only pull; it never
stashes edits, switches branches, or creates a merge commit.

The shared installer refreshes TUM Moodle using the Codex CLI on PATH or in a standard
macOS app bundle. If it cannot find the CLI, it updates the code/runtime and tells
you to reinstall the plugin from your personal source in the Plugins screen.
Custom marketplace names are preserved. A failed step stops the update and
reports the error; fix that issue and rerun the command.

For a checkout created before the updater was added, first run `git pull --ff-only`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| No personal plugin source | Repeat packaging with `--register`, then fully restart Codex. Check that your client supports local marketplaces. |
| Skills appear but tools do not | Repeat bootstrap, reinstall the plugin from your personal source, and restart Codex. Check loader errors before repeating restarts. |
| `uv` is missing | Install uv and open a new terminal/app session. Bootstrap also checks `~/.local/bin` and standard Homebrew locations. |
| Windows opens Microsoft Store for Python | Rerun the installer. The generated manifest must point to the private runtime's `Scripts/python.exe`. |
| Native credential store unavailable | Unlock the OS store. Linux needs Secret Service in the current desktop D-Bus session; there is no plaintext fallback. |
| Chrome fails to open | Install Google Chrome, then ask the plugin to sign in again. Chromium-only installations are not selected automatically. |
| Session expired | Ask Codex to sign in to Moodle again. |
| Scanned material fails | Install Tesseract and put it on PATH, then restart Codex and retry. Text PDFs do not require OCR. |
| Search returns little | Ask Codex to index/refresh the course and check coverage. |

Downloaded originals are in `~/Downloads/TUM Moodle/`. To use a different folder,
set `TUM_MOODLE_DOWNLOAD_DIR` in the environment inherited by Codex.
`TUM_MOODLE_DATA_DIR` overrides the session/cache location. The installed runtime
stays in the standard platform data folder.

For [bug reports](https://github.com/jamestesting0/tum-moodle-integration/issues),
include OS/client versions and the error message. Remove credentials, cookies,
personal records, and course content.

## Data locations

| Platform | Moodle runtime, session, and cache |
| --- | --- |
| macOS | `~/Library/Application Support/TUMMoodle/` |
| Windows | `%LOCALAPPDATA%\TUMMoodle\` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/TUMMoodle/` |

Campus settings and encrypted credentials use a separate `TUMMCP/` folder beside
`TUMMoodle/`. Existing Moodle data remains in place when switching to TUM MCP.

## Uninstall

1. Ask Codex to sign out and clear the cache, then remove the plugin in Plugins.
2. To remove the personal catalog entry, delete only `tum-moodle` from
   `~/.agents/plugins/marketplace.json`, preserving the other entries.
3. Delete `~/.codex/plugins/local/tum-moodle/` and the
   [platform data folder](#data-locations) if no longer needed.
4. Remove the `tum-moodle-integration` credential entry using the OS credential
   manager: Keychain Access, Windows Credential Manager, or the Linux password/keyring app.

Delete downloaded files separately if desired. Signing out removes this plugin's
saved session; it does not sign you out of other browsers or revoke TUM sessions.
