# Setup and troubleshooting

[README](../README.md) · [Tools and access](tum-mcp.md) · [Development](development.md)

Use the latest package for the connection, managed update and removal flows below.

## Install

Install Node.js 22.14 or newer and a Chromium browser. No system Python, native
keyring or administrator access is required by TUM MCP. Supported bootstrap
targets are macOS ARM64/x64, Windows ARM64/x64 and glibc Linux ARM64/x86_64.
Linux needs a graphical desktop for native browser sign-in; WSL can use Windows.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup --client codex
tum-mcp login
tum-mcp doctor
tum-mcp --help
```

Run `tum-mcp setup` to choose clients interactively, or pass `--client claude`,
`cursor`, `antigravity`, or `generic` directly. Existing registrations have status dots.
Codex needs the plugin enabled and a restart when prompted. Cursor and
Antigravity setup installs all five base skills and MCP configuration; restart each
client afterward. Existing MCP-only setups gain the skills through `tum-mcp update`
or another setup run. Generic setup writes configuration for manual installation.

Generic clients use
`tum-mcp skills export DESTINATION` to install the active pack manually.
Setup preserves unrelated settings and refuses to
replace customized entries. It does not authenticate or fetch courses.

Audio Notes is optional: use `tum-mcp install audio-notes`. It adds the
`audio-notes` skill for prepared Study content; synthesis is set up when used.
Existing course audio is retained when the extension is disabled.

Video Notes is optional: use `tum-mcp install video-notes`. It adds the
`video-notes` skill and the `tum-mcp video-notes` commands for prepared Study content.
Its render runtime (about 320 MB) installs on first use; `tum-mcp video-notes runtime
status` lists any prerequisite (macOS: `brew install cairo`; Linux/WSL: Cairo and
Pango development packages and a C compiler) without installing it. Course videos are
retained when the extension is disabled. Clients pinned to a runtime generation older
than this release cannot read the enabled Video Notes setting; refresh them with `tum-mcp update` or `setup --client NAME`.

## Terminal output

`tum-mcp doctor` is the overview for saved connections, optional extensions,
client setup and runtime health, including TUMonline. Client rows appear only
for installed clients or existing TUM MCP registrations; unrelated config
folders do not count as installations. Setup detects the same clients and
also offers Generic. Use `--client NAME` for an undetected or nonstandard install.
Green dots mean ready or enabled, blue means not verified, amber means action
needed, red means failed, and muted dots mean inactive. Every dot has a text
label. `NO_COLOR` disables color; narrow terminals use stacked rows.

Bare `tum-mcp setup`, `tum-mcp install` and `tum-mcp uninstall` share the same
keyboard controls as login. Nothing is preselected; Ctrl+C cancels. Uninstall
also offers **All — TUM MCP**, which removes the package and managed client setup.
Personal notes, sessions and customized files are retained. Scripts can name extensions:
`tum-mcp uninstall lecture audio-notes --json`.

Use `--json` for machine-readable status, named extension removal/installation,
skill listing/validation, lecture runtime status or TUMonline permissions.
The default human output changed in 0.9.1; scripts that parsed those commands
must add `--json`. The former `extensions` group is removed; use `doctor` and
`uninstall NAME`. Named client/extension arguments remain suitable for scripts.
Data-oriented course authoring commands retain JSON output.

`login` replaces `connect`, and `doctor` replaces the separate status screen.
The old command names remain hidden compatibility aliases. `status --json`
retains its previous configuration format; new integrations should use `doctor --json`.

<a id="connect"></a>

## Login

Run **`tum-mcp login`**, with no arguments, in an interactive terminal:

1. Use up/down to move and Space to select services. Installed Lecture adds TUM-Live.
2. Press Enter. If several browsers are installed, choose one and press Enter.
3. Complete TUM sign-in/MFA in the opened window. Only selected service tabs open.
4. Return to the terminal for the saved-connection result.

Campus services use temporary-browser sign-in and encrypted session storage.
No API key or native credential-store prompt is needed. A temporary browser
profile keeps the connection separate from your everyday browser. Ctrl+C closes it and preserves
connections that already completed. A dumb terminal uses numbered prompts.

Chrome, Edge, Brave, Chromium, Vivaldi and Opera are detected in their standard
locations. Selected preview channels and Opera GX are detected where installed.
For another Chromium build, set `TUM_MCP_BROWSER` to its executable path before
running login. Compatible builds must allow Playwright automation. Safari and
Firefox are not supported.

After sign-in, Artemis and Zulip can read content available to your campus account.
No local course/channel grants are required. Your agent uses MCP status/discovery and
course metadata to find relevant current-semester material, then makes bounded reads.
An account ID identifies a saved service connection; it is not your TUM login.
TUMonline additionally has a local policy: `tum-mcp manage tumonline --show`
shows it, `tum-mcp manage tumonline` changes its permissions,
and `tum-mcp manage tumonline --disconnect` removes its saved local session.
Use `--account ACCOUNT_ID` if more than one TUMonline account is configured.
Study names, public course metadata and public course curriculum positions are available by default;
grades and progress, exams and fee status need your permission first, and the full
curriculum is unavailable. [Details and limitations](tum-mcp.md#tumonline-permissions).
`tum-mcp --help` lists commands; `tum-mcp study build --help` shows command options.

## WSL

Install Node.js and the npm package **inside WSL**. WSL 3.x is the application
release; distributions still use engine 1 or 2. See Microsoft's
[release page](https://github.com/microsoft/WSL/releases) and
[version commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
Both engines have dedicated CI checks on the current WSL 3.x runner image.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup --client cursor --host windows
tum-mcp login
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
  reads and checks optional GitHub CLI authentication. `--json` provides structured
  output; combine the flags if needed. Default doctor checks only CLI availability.
- For optional study publishing, install GitHub CLI and complete
  `gh auth login --hostname github.com` interactively on the agent's execution host.
  The [publishing workflow](study.md#publish-a-study-website) uses private repositories
  with public Pages websites and requires an eligible paid GitHub plan.
- An expired session uses the same `tum-mcp login` selector. Reconnecting the
  same identity preserves saved preferences.
- If no browser appears, check its installation or `TUM_MCP_BROWSER`. A managed
  or incompatible Chromium build may prevent automation; try another browser.
- Git and Docker are optional. Neither is needed for course reads or the
  GitHub CLI based study publisher.
- Do not paste passwords, cookies, MFA codes or API keys into chat or bug reports.

Sessions are encrypted with owner-restricted local key files. This avoids native
credential-store prompts, but anyone obtaining both key and ciphertext can
decrypt them. [Storage locations and recovery](tum-mcp.md#connections-and-read-access)
explain where sessions are saved and how to back them up.

## Update and remove

```sh
tum-mcp update
```

From 0.6.1, `update` retrieves the latest npm release, validates its backend in a
temporary installation, replaces the invoked package and refreshes previously
configured clients. It preserves the installation prefix and global/local mode.
It does not connect services, change preferences or register additional clients.
It never downgrades a newer installation. `update --local` skips npm and repairs
or refreshes the installed version. Source/pinned builds use this local mode;
temporary npx and linked source installations are not replaced automatically.
Automatic replacement also stops if the package directory contains configured
sessions, downloads or course work; move that data outside the package first.
For 0.6.0 and earlier, first install the newer npm package once.
`setup --client NAME` explicitly registers one client and can also refresh that client's managed
files. WSL Windows registrations keep their distribution/user/data paths.

Ownership receipts track the entries and files installed by TUM MCP. Unchanged
managed files advance; unrelated settings and extra files stay intact. Direct
edits to an entry or skill stop that client's update and are reported for review;
other clients can still advance. Old runtime generations remain available for
existing pinned clients. Interrupted setup can recover a stopped lock owner;
an ownerless/unknown legacy lock requires local review. A failed new runtime is
not selected, and a damaged runtime is repaired into a fresh generation. A newer
managed client is not silently downgraded by an older package; intentional
rollback starts by unregistering that client, then registering the reviewed version.

Reload MCP servers in Cursor/Antigravity, restart Claude as appropriate, and
update/reinstall TUM MCP from the personal source in Codex Plugins if its cached
copy still shows the older skills. Writing source files does not activate a host.

Remove a single client with `tum-mcp uninstall --client cursor` (replace the
client as needed; add `--host windows` from WSL for a Windows client). To remove
the npm package and all managed registrations:

```sh
tum-mcp uninstall
# Choose All to remove TUM MCP and its managed client setup.
```

Custom edits and user-added files are preserved. Codex's local source/catalog
entry can be removed, but its cached/active plugin must also be removed or
disabled through Codex Plugins. Package removal runs only after successful
client cleanup; conflicts preserve npm so you can review and retry. `--all`
is accepted explicitly, and `--keep-package` removes client setup without npm.
No npm lifecycle hook performs cleanup or reads credentials.

For explicit cleanup, **close coding clients first**, then run:

```sh
tum-mcp uninstall --purge-runtime --forget-credentials
```

`--purge-runtime` deletes verified managed runtime generations after the Python
helper exits, and removes unchanged managed bootstrap/browser-driver caches.
Active tracked backends or unrecognized runtime files stop automatic removal.
Paths overlapping configured assignment work, downloads or Moodle data are
protected. `--forget-credentials` removes saved local credentials and session
keys; it does not revoke remote credentials. Settings, custom skills, course
cache, downloads and assignment work are retained by these commands.
No command recursively deletes the campus
data root. Course audio and videos, the optional video render runtime and shared
speech models/runtimes also remain.
Remove a shared speech cache only when explicitly requested and no other course
needs it; its host paths are documented in the audio skill. If removal is
interrupted, run `tum-mcp setup --client NAME` to recover before reuse.
