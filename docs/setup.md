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
`audio-notes` skill and `tum-mcp audio-notes` commands for prepared Study and Exam
content; synthesis is set up when used, publishing uses the Video Notes render
runtime (`tum-mcp video-notes runtime install`) and `listen` uses the Lecture speech
recognizer (`tum-mcp lecture runtime install`).
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
keyboard controls as login. Nothing is preselected; Esc cancels. Bare setup lists the
installed clients, then the optional workflows that are not installed yet; Enter with
nothing selected skips either step. Without a supported client it shows no client
picker and says so. `setup --client NAME` registers clients only. Uninstall
also offers **Everything (remove TUM MCP)**, which removes the package and managed
client setup after one confirmation that lists what is removed and kept.
Personal notes, sessions and customized files are retained. Scripts can name extensions:
`tum-mcp uninstall lecture audio-notes --json`.

Course Memory is disabled by default. Run `tum-mcp install course-memory`, reload
the client, then ask a relationship or study-planning question in a bound course.
The agent reads the links the course already holds; it writes nothing while answering.
Installation does not scan courses or read PDFs.
`tum-mcp uninstall course-memory` disables retrieval and maintenance while retaining
private graph files and notes. Reinstall validates current evidence before reuse.
Customized client files are preserved and reported; disabled graph calls remain
blocked even if old instructions survive. A fresh chat may be needed to clear
context already read before uninstall. See [course memory](study.md#local-course-relationships).

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

1. Services marked Needs action are preselected. Use up/down to move and Space to
   change the selection. Installed Lecture adds TUM-Live.
2. Press Enter, choose a browser and press Enter. A saved profile shows its name in
   parentheses, e.g. `Google Chrome (TUM)`; a plain browser name opens a temporary
   profile. Your last selected browser or profile appears first and is selected
   by default; if it is unavailable, the first available choice is selected.
3. Complete TUM sign-in/MFA in the opened window. Only selected service tabs open.
4. Return to the terminal for the saved-connection result.

In a numbered prompt, Enter accepts the displayed defaults; entering numbers
replaces them. Esc cancels. Login verifies saved sessions when their diagnostic
result is missing or at least 8 hours old, or the credential key has changed.
Fresh results are reused. `tum-mcp doctor` checks again.

Run `tum-mcp logout` to choose saved connections to remove. Nothing is preselected
and no network check runs. Removing a connection clears
its local credentials, retaining settings, TUMonline permissions, downloads and
other connections. Remote sessions are not revoked. The explicit
`tum-mcp logout SERVICE [ACCOUNT]` form works without a terminal, e.g.
`tum-mcp logout moodle`; ACCOUNT is needed only when several accounts of that
service are saved.

Campus services use browser sign-in and encrypted session storage. No API key is
required. Temporary login uses a fresh profile.
Ctrl+C closes the window and preserves connections that already completed.
A dumb terminal uses numbered prompts, with Enter accepting the first browser.

Choose **Set up a saved profile…** to create a dedicated Chromium profile.
Setup asks for its browser and name; complete sign-in
in the opened window. Later, choose `Google Chrome - saved` (or your browser) to
reuse its sign-in. Every saved choice shows its profile name in parentheses.
No browser skill or extension is required. Saved profiles do not inherit passwords
from your everyday profile, and expired sessions still require sign-in or MFA.

Profiles are created and managed only by TUM MCP; existing browser profiles cannot
be added. TUM MCP locks each saved directory against concurrent use and never
reads saved passwords.

Run **`tum-mcp manage browsers`** to create, open, rename or remove profiles.
Choose a profile, then **Open**, to keep its window open while you save passwords
or manage browser settings. Close all its windows to return to the menu. This
uses the browser's native password storage; TUM MCP does not read saved passwords.
The managed-profile lock prevents simultaneous login or removal while it is open.
Removing a profile deletes its browser data and encrypted session copy. Interactive logout
offers to clear the selected services' sign-in from available saved profiles too,
including shared TUM sign-in. Otherwise profiles remain signed in and can reconnect.
Explicit `logout SERVICE [ACCOUNT]` retains browser profiles. Uninstalling with
`--all --forget-credentials` removes managed profiles and TUM MCP's saved sessions.
Other browser profiles are never changed.

Managed browser data uses owner-only permissions and the browser's native storage.
TUM MCP additionally encrypts campus cookies so session-only sign-ins survive a
browser restart. Unrelated site cookies are not copied into that encrypted store.

Chrome, Edge, Brave, Chromium, Vivaldi and Opera are detected in their standard
locations. Selected preview channels and Opera GX are detected where installed.
For another Chromium build, set `TUM_MCP_BROWSER` to its executable path before
running login. Compatible builds must allow Playwright automation. Safari and
Firefox are not supported.

After sign-in, Moodle, Artemis and Zulip can read content available to your campus account.
No local course/channel grants are required. Your agent uses MCP status/discovery and
course metadata to prefer current-semester material for unspecified requests, then makes
bounded reads. Moodle discovery defaults to current-semester courses and Artemis to
active courses. For an explicit semester such as WS23, the agent sets `include_past=true`
to discover older offerings, then uses the selected IDs to read retained materials,
lectures, student slides and released exercise statements while the service grants access.
An account ID identifies a saved service connection; it is not your TUM login.
TUMonline additionally has a local policy: `tum-mcp manage tumonline --show`
shows it, `tum-mcp manage tumonline` changes its permissions,
and `tum-mcp logout tumonline` removes its saved local session.
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
The bridge uses binary pipes, without a remote
debugging TCP port. Transport is selected by a runtime pipe test, not a version
string, so a WSL package update does not change that assumption.
Saved Windows-browser profiles live under Windows LocalAppData; their extra
encrypted campus-session copies and keys stay in WSL. Both WSL engines use the
same path translation and Windows owner-only ACL protection.

Windows interop and its PATH integration must be enabled: `powershell.exe` (or
`pwsh.exe`) and `wslpath` must be available from WSL. Drive paths are translated
with `wslpath`; the package does not assume `/mnt/c`. If interop is disabled,
restore it in your WSL configuration and restart the distribution. A Linux GUI
browser can also be listed when DISPLAY or WAYLAND_DISPLAY is set. Windows
browser discovery still requires functioning interop.

## Diagnose and reconnect

- `tum-mcp doctor` shows services, client registrations, browsers and optional
  tools. It verifies saved sessions with bounded service reads and checks optional
  GitHub CLI authentication. `--live` remains an explicit way to request this default.
- `tum-mcp doctor --static` uses cached verification and local checks. Successful
  verification remains current for 8 hours. After that, the session appears as
  **Not checked** until a fresh check. `--json` provides structured output with
  either mode.
  Setup also installs course completion hooks for Codex, Claude Code, Cursor and
  Antigravity, preserves unrelated hooks, and checks the owned MCP transport.
  Codex setup obtains hook identities from the installed runtime and registers only
  those exact trust hashes, then verifies that they are enabled and trusted. It does
  not use a global trust bypass. Other clients use native settings without Codex
  trust entries. Workspace trust, explicit disabling and administrator policies
  remain in effect. Unsupported runtimes receive a specific next step; manual hook
  approval is only needed when the host cannot complete that setup automatically.
  Setup explains the guard before client selection and prints the actual verification
  result for each client, including any action still needed. Reload the client and
  open a new chat after setup; `tum-mcp doctor` rechecks the registration and hooks.
  The guard continues only a batch owned by that chat, preserves its approved
  review budget and pauses on interruption.
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
# Choose Everything to remove TUM MCP and its managed client setup.
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

### Client verification boundaries

`doctor` reuses successful client checks for up to 24 hours, showing their age.
Registration, installed-file, hook and host configuration checks still run every
time. Configuration, environment, package or executable changes invalidate the
cache; failed checks retry immediately. Use `tum-mcp doctor --refresh-clients` to
force a fresh check. Setup always checks afresh. Cached transport success never
promotes unverified native host loading to Ready.

When a fresh check is needed, `doctor` initializes the owned MCP registration and lists its tools without a model
request or campus tool call. It checks installed-file ownership before executing
the launcher. Codex additionally reports native plugin loading and hook trust;
Claude Code health-checks its TUM registration through `claude mcp get tum`, and
Cursor uses `cursor-agent mcp list-tools tum` when that CLI is already installed.
Doctor never installs a client CLI, signs in, enables a disabled hook, or writes
trust entries. Native CLIs may maintain their own normal metadata and cache logs
while performing these health checks. `--static` launches none of these checks.

A working transport alone is reported as **Not checked** when native host loading
cannot be checked, including an unavailable Antigravity CLI. WSL can inspect Windows
registration files; run doctor on the Windows host for its native live result.
These global registration checks do not prove workspace-specific permissions or
that a model will select the right skill.

The installer uses documented native configuration for
[Claude Code](https://code.claude.com/docs/en/hooks),
[Cursor](https://cursor.com/docs/hooks) and
[Antigravity](https://antigravity.google/docs/hooks). Codex's exact-hash trust state
is obtained through its installed app-server protocol rather than duplicating the
hash algorithm. User-level hooks avoid bundled-hook discovery incompatibility in
Codex 0.164.0; the managed bridge remains inside the local TUM package. If that
runtime API is unavailable, setup preserves the files and identifies the required
[Codex hook review](https://learn.chatgpt.com/docs/hooks).
