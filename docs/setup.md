# Desktop setup

[README](../README.md) · [macOS](#macos) · [Windows](#windows) · [Linux](#linux) ·
[Troubleshooting](#troubleshooting) · [Uninstall](#uninstall)

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

Git and `python3` can also come from Apple's Command Line Tools:
`xcode-select --install`. For scanned PDFs, optionally install `brew install tesseract`.
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
uv supplies Python; a separate Python installation is not required. The generated
Windows plugin uses `uv` to launch its private runtime. Ensure `uv --version` works
before opening Codex.

Windows Credential Manager stores the session-encryption key. Optional OCR needs
[Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html), with its
installation directory on PATH. Restart Codex after changing PATH.

### Linux

Use a graphical desktop session with Google Chrome, `python3`, Git, uv, and an
unlocked **Secret Service** keyring, such as GNOME Keyring. The keyring must be
available in the same D-Bus session as Codex. A headless SSH session is insufficient
for interactive Moodle sign-in.

For Ubuntu/Debian prerequisites:

```sh
sudo apt-get install git python3 gnome-keyring
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Chrome](https://www.google.com/chrome/) using their official installers.
For OCR, optionally install `sudo apt-get install tesseract-ocr`.
On other distributions, use the equivalent packages. KWallet-only setups need
a running Secret Service provider; the plugin deliberately avoids plaintext
or arbitrary third-party credential backends.

## Install and sign in

Follow the [four installation commands in the README](../README.md#install).
Run them on the target computer so packaging generates the correct launcher.
Do not copy a Mac's generated plugin or session files to Windows/Linux.

The installer preserves existing marketplace entries and registers the source
under `~/.codex/plugins/local/tum-moodle/`. In PowerShell, `~` refers to your user
profile. You can also install through the Codex CLI:

```text
codex plugin add tum-moodle@personal-local
```

If you renamed your personal source, use its marketplace name instead.
Restart the desktop app completely after installation: **Cmd+Q** on macOS;
exit all app windows/background instances on Windows/Linux, then reopen it.

Select **TUM Moodle** and ask it to sign in. Complete the TUM login and MFA in
the private Chrome window. The plugin reuses a saved session until it expires.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| No personal plugin source | Repeat packaging with `--register`, then fully restart Codex. Check that your client supports local marketplaces. |
| Skills appear but tools do not | Repeat bootstrap, reinstall the plugin from your personal source, and restart Codex. Check loader errors before repeating restarts. |
| `uv` is missing | Install uv and open a new terminal/app session. Bootstrap also checks `~/.local/bin` and standard Homebrew locations. |
| Windows opens Microsoft Store for Python | Rebuild/register the plugin on Windows. Its manifest should use `uv`, not the Python Store alias. |
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

## Uninstall

1. Ask Codex to sign out and clear the cache, then remove the plugin in Plugins.
2. To remove the personal catalog entry, delete only `tum-moodle` from
   `~/.agents/plugins/marketplace.json`, preserving the other entries.
3. Delete `~/.codex/plugins/local/tum-moodle/` and the
   [platform data folder](../README.md#privacy-and-storage) if no longer needed.
4. Remove the `tum-moodle-integration` credential entry using the OS credential
   manager: Keychain Access, Windows Credential Manager, or the Linux password/keyring app.

Delete downloaded files separately if desired. Signing out removes this plugin's
saved session; it does not sign you out of other browsers or revoke TUM sessions.
