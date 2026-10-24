# Setup and troubleshooting

[README](../README.md) · [Tools and scopes](tum-mcp.md) · [Development](development.md)

These instructions apply to **0.5.0**. Upgrade older installations before using
the interactive connection flow below.

## Install

Install Node.js 22.14 or newer and a Chromium browser. No system Python, native
keyring or administrator access is required by TUM MCP. Supported bootstrap
targets are macOS ARM64/x64, Windows ARM64/x64 and glibc Linux ARM64/x86_64.
Linux needs a graphical desktop for native browser sign-in; WSL can use Windows.

```sh
npm install --global @jamestesting888/tum-mcp@0.5.0
tum-mcp setup --client codex
tum-mcp connect
tum-mcp doctor
```

Use `--client claude`, `cursor`, `antigravity`, or `generic` for another client.
Codex needs the plugin enabled and a restart when prompted. Cursor and
Antigravity need their MCP servers reloaded. Generic setup writes configuration
for manual installation. Setup preserves unrelated settings and refuses to
replace customized entries. It does not authenticate or fetch courses.

## Connect

Run **`tum-mcp connect`**, with no arguments, in an interactive terminal:

1. Use up/down to move and Space to select Moodle, Artemis and/or Zulip.
2. Press Enter. If several browsers are installed, choose one and press Enter.
3. Complete TUM sign-in/MFA in the opened window. Only selected service tabs open.
4. Return to the terminal for the saved-connection result.

Moodle uses exactly the same selector and storage flow as Artemis and Zulip.
No API key or Keychain prompt is needed. A temporary browser profile keeps the
connection separate from your everyday browser. Ctrl+C closes it and preserves
connections that already completed. A dumb terminal uses numbered prompts.
Old service arguments and `--service`/`--auth` flags are no longer accepted.

Chrome, Edge, Brave, Chromium, Vivaldi and Opera are detected in their standard
locations. Selected preview channels and Opera GX are detected where installed.
For another Chromium build, set `TUM_MCP_BROWSER` to its executable path before
running connect. Compatible builds must allow Playwright automation. Safari and
Firefox are not supported.

New Artemis/Zulip accounts start without content scopes. Your agent can use
status/discover to show account IDs and available course/channel metadata, then
help you choose [explicit scopes](tum-mcp.md#connections-and-scopes).
An account ID identifies a saved service connection; it is not your TUM login.

## WSL

Install Node.js and the npm package **inside WSL**. WSL 3.x is the application
release; distributions still use engine 1 or 2. See Microsoft's
[release page](https://github.com/microsoft/WSL/releases) and
[version commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
Both engines have dedicated CI checks on the current WSL 3.x runner image.

```sh
npm install --global @jamestesting888/tum-mcp@0.5.0
tum-mcp setup --client cursor --host windows
tum-mcp connect
tum-mcp doctor
```

Replace `cursor` with your client. `--host windows` registers the Windows app
against the WSL backend and shared Linux session paths. It writes the Windows
user's profile using a `wsl.exe` stdio command that pins the distribution and
Linux user. Omit the option for clients running inside Linux. Native Windows
installation also uses the default host. Use `--host windows` on uninstall too.
Reload or restart the Windows client after setup. The WSL distribution and its
managed runtime must remain available at the registered paths.

Connect detects Windows Chromium browsers and opens them on the Windows desktop.
First use downloads a private, checksum-verified Windows Node driver from
nodejs.org into Windows LocalAppData. A separate Windows Python or Node install
is unnecessary. The backend, session keys and encrypted sessions stay in WSL.
The bridge uses binary pipes and a temporary browser profile, without a remote
debugging TCP port. Transport is selected by a runtime pipe test, not a version
string, so a WSL package update does not change that assumption.

Windows interop and its PATH integration must be enabled: `powershell.exe` (or
`pwsh.exe`) and `wslpath` must be available from WSL. Drive paths are translated
with `wslpath`; the package does not assume `/mnt/c`. If interop is disabled,
restore it in your WSL configuration and restart the distribution. A Linux GUI
browser can also be listed when DISPLAY or WAYLAND_DISPLAY is set. Windows
browser discovery still requires functioning interop.

## Diagnose and reconnect

- `tum-mcp doctor` shows services, client registrations, browsers and optional
  tools. Saved sessions are **Not verified** until checked; registration alone
  does not prove a desktop client is running the server.
- `tum-mcp doctor --live` verifies saved local sessions with bounded service
  reads. `--json` provides structured output; combine the flags if needed.
- An expired session uses the same `tum-mcp connect` selector. Reconnecting the
  same identity preserves course/channel scopes.
- If no browser appears, check its installation or `TUM_MCP_BROWSER`. A managed
  or incompatible Chromium build may prevent automation; try another browser.
- Git is optional for assignment workspaces. Docker is optional for approved
  isolated tests. Missing either does not prevent course reads.
- Do not paste passwords, cookies, MFA codes or API keys into chat or bug reports.

Sessions are encrypted with owner-restricted local key files. This avoids native
credential-store prompts, but anyone obtaining both key and ciphertext can
decrypt them. [Storage locations and recovery](tum-mcp.md#connections-and-scopes)
explain migration and backup. Existing Moodle data and downloads are preserved.

## Update and remove

Update with `npm install --global @jamestesting888/tum-mcp@latest`, then rerun
setup. Review conflicts instead of deleting customized client configuration.
`tum-mcp uninstall --client cursor` (or your client) removes unchanged managed
registration while retaining sessions, downloads and personal work. Codex plugin
removal uses its Plugins UI. Remove the npm package separately with
`npm uninstall --global @jamestesting888/tum-mcp`.

## Existing Moodle-only installations

The older `tum-moodle` commands and sixteen `moodle_*` tools remain compatible.
The separate source/plugin installer retains its original native credential
store: macOS Keychain, Windows Credential Manager, or Linux Secret Service.
Its native-store identity, existing session paths and downloads remain intact.
The combined `tum-mcp serve` uses local-file storage and directs all login
requests to `tum-mcp connect`. Reconnect once through that selector to create the
new session; no automatic extraction of older native-store secrets occurs.
Disable the older plugin when activating TUM MCP to avoid duplicate tools.
