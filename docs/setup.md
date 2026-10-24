# Setup and troubleshooting

[README](../README.md) · [Tools and scopes](tum-mcp.md) · [Development](development.md)

Use the latest package for the connection, managed update and removal flows below.

## Install

Install Node.js 22.14 or newer and a Chromium browser. No system Python, native
keyring or administrator access is required by TUM MCP. Supported bootstrap
targets are macOS ARM64/x64, Windows ARM64/x64 and glibc Linux ARM64/x86_64.
Linux needs a graphical desktop for native browser sign-in; WSL can use Windows.

```sh
npm install --global @jamestesting888/tum-mcp@latest
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
npm install --global @jamestesting888/tum-mcp@latest
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

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp update
```

`update` activates the backend bundled in the invoked npm package and refreshes
previously configured clients. It does not fetch a newer npm version itself,
connect services, change scopes or register additional clients. `setup --client
NAME` explicitly registers one client and can also refresh that client's managed
files. WSL Windows registrations keep their distribution/user/data paths.

Ownership receipts track the entries and files installed by TUM MCP. Unchanged
managed files advance; unrelated settings and extra files stay intact. Direct
edits to an entry or skill stop that client's update and are reported for review;
other clients can still advance. Old runtime generations remain available for
existing pinned clients. Interrupted setup can recover a stopped lock owner;
an ownerless/unknown legacy lock requires local review. A failed new runtime is
not selected, and a damaged runtime is repaired into a fresh generation.

0.4.1/0.5.0 installations without receipts are adopted only after matching their
retained runtime's canonical client output. The seven former workflow skills
become three website skills. Personal overrides under retired names remain in
the config `skills/` directory; review and merge them into `tum-moodle`,
`tum-artemis` or `tum-zulip` before exporting a replacement pack.
Reload MCP servers in Cursor/Antigravity, restart Claude as appropriate, and
update/reinstall TUM MCP from the personal source in Codex Plugins if its cached
copy still shows the older skills. Writing source files does not activate a host.

Remove a single client with `tum-mcp uninstall --client cursor` (replace the
client as needed; add `--host windows` from WSL for a Windows client). To remove
all managed registrations before uninstalling npm:

```sh
tum-mcp uninstall --all
npm uninstall --global @jamestesting888/tum-mcp
```

Custom edits and user-added files are preserved. Codex's local source/catalog
entry can be removed, but its cached/active plugin must also be removed or
disabled through Codex Plugins. No npm uninstall hook deletes user data.

For explicit cleanup, **close coding clients first**, then run:

```sh
tum-mcp uninstall --all --purge-runtime --forget-credentials
npm uninstall --global @jamestesting888/tum-mcp
```

`--purge-runtime` deletes verified managed runtime generations after the Python
helper exits, and removes unchanged managed bootstrap/browser-driver caches.
Active tracked backends or unrecognized runtime files stop automatic removal.
Paths overlapping configured assignment work, downloads or Moodle data are
protected. `--forget-credentials` removes local encrypted service sessions, keys
and participation Git tokens; it does not revoke remote credentials. Native
Keychain/Credential Manager/Secret Service records and legacy Moodle sessions
stay intact. Settings, custom skills, course cache, downloads and assignment
work are retained by these commands. No command recursively deletes the campus
data root. If removal is interrupted, run npm `setup` to recover before reuse.

## Existing Moodle-only installations

The older `tum-moodle` commands and sixteen `moodle_*` tools remain compatible.
The separate source/plugin installer retains its original native credential
store: macOS Keychain, Windows Credential Manager, or Linux Secret Service.
Its native-store identity, existing session paths and downloads remain intact.
The combined `tum-mcp serve` uses local-file storage and directs all login
requests to `tum-mcp connect`. Reconnect once through that selector to create the
new session; no automatic extraction of older native-store secrets occurs.
Disable the older plugin when activating TUM MCP to avoid duplicate tools.
