# TUM MCP guide

Package: `@jamestesting888/tum-mcp`, CLI: `tum-mcp`, backend: Python 3.13.
Version **0.5.1** provides interactive service and browser selection, local-file
credential keys, richer diagnostics, Cursor/Antigravity adapters, and WSL-backed
Windows client setup. The package supports campus reads and local assignment
assistance; remote-action tools remain disabled.

## Current capabilities

The campus server preserves all sixteen `moodle_*` tools and the existing Moodle
session/keychain identity. It adds scoped Zulip channel search/topic reads,
released Artemis programming statements, exact-revision visible feedback,
participation-bound workspace preparation, approved container test recipes,
submission previews, and three website skills.

Remote start, push, submit, rebuild, Zulip posting, and DMs are unavailable.
An internal, release-gated executor covers exact-action fingerprints, encrypted
expiring one-use grants, account/scope/credential revalidation, and durable
unknown-outcome receipts. Synthetic tests cover one POST or exact-commit push,
copied/fabricated approvals, changed targets, and lost responses. No MCP write
tool, approval issuer, or preference can open this version's gate.
The internal executor is groundwork for Phase 5; no live-action certification is claimed.
Revision 3 Phase 5 needs a demonstrated trusted approval/credential boundary and
safe practice-exercise verification before those tools can be exposed. A
submission preview never performs a commit or remote action. Native Git/browser
tools available to an unrestricted host remain outside the MCP enforcement
boundary; the server does not claim to prevent every host-level push.

The verified public origins are `https://artemis.tum.de` and
`https://zulip.cit.tum.de`. Public discovery on 24 October 2026 reported Artemis
10.4, source revision `d8594cc5fb2f2ec276bd123861be7ff20c1b3cc0`, and Zulip 12.0,
feature level 498, with TUM Shibboleth. No account permission follows from that
public discovery. Provider routes were checked against that Artemis revision.

## Build and test the local package

For normal installation, use `npm install --global @jamestesting888/tum-mcp@latest`
and `tum-mcp setup --client codex`. The following commands are for maintainers.

```sh
uv sync --locked
uv run ruff check src tests plugin/scripts scripts
uv run ruff format --check src tests plugin/scripts scripts
uv run pytest -q -m 'not live'
node npm/build.mjs
npm test
npm pack --ignore-scripts --pack-destination dist
npm run test:consumer
npm run test:upgrade
```

The npm artifact has an explicit file allowlist, a bundled backend wheel,
hash-pinned dependency requirements, backend integrity metadata, and pinned uv
artifacts with SHA-256 checksums. `npm install` has no lifecycle setup/login
hooks. uv's generated output-directory ignore file is overridden specifically so
the required backend enters the tarball. Inspect the tarball before distribution.

Install the tarball into a temporary directory for testing, then run its binary:

```sh
npm install --prefix /path/to/test-profile --ignore-scripts /path/to/package.tgz
/path/to/test-profile/node_modules/.bin/tum-mcp setup --client generic
```

Use `TUM_MCP_DATA_DIR` and `TUM_MCP_CONFIG_DIR` to isolate testing from real campus
state. Never change the maintainer's actual client configuration just to test
packaging. Setup provisions a private, versioned Python runtime using uv 0.12.5
and Python 3.13.15; an existing matching uv, including the verified cached download,
is reused. Source checkouts and system
Python are unnecessary for consumers. Supported bootstrap targets are macOS
arm64/x64, Windows arm64/x64, and glibc Linux arm64/x64; hands-on verification is
recorded separately. New campus sessions use permission-restricted local keys and need no Secret Service.
Clean consumer bootstrap, idempotent setup, diagnostics, and skill validation
passed on macOS ARM64 and in Linux ARM64 and x86_64 containers. The x86_64 check
ran through Docker amd64 emulation on an ARM64 Mac; packaged MCP protocol checks
and an encrypted credential round trip through a real GNOME Secret Service in an
isolated D-Bus session also passed. Real Linux desktop browser sign-in, macOS x64,
and Windows hands-on checks remain open. New storage and terminal behavior need
the current checkout’s test evidence; earlier native-store results do not certify them. The installer targets glibc Linux
x86_64/amd64 and aarch64/ARM64.

`update` prepares the backend bundled in the invoked package, refreshes
previously configured clients and preserves older runtime generations.
[Update and removal behavior](setup.md#update-and-remove) covers ownership
receipts, legacy adoption, conflict handling and explicit cleanup. To obtain a newer public package after publication,
invoke its reviewed version explicitly. It does not publish a release or replace
customized client skills silently. If interrupted setup leaves `setup.lock`,
confirm that no setup process is running before removing that directory locally.
An invalid or incomplete runtime is never selected for serving. Failed validation
clears its ready marker so explicit setup can rebuild it; older runtimes remain
available to existing client registrations. Use an older reviewed package and
rerun its setup to restore that runtime, reviewing any client configuration diff.

For platforms outside the bootstrap targets, the source installation needs
Python 3.13+, uv, and Git: run `uv sync --locked`, then
`uv run tum-mcp setup --client generic` from the checkout. An installed Chromium browser is needed for
browser onboarding. See [setup](setup.md) for browser choices and WSL. Docker is needed only for isolated assignment tests.

## Connections and scopes

```sh
tum-mcp connect
tum-mcp status
tum-mcp discover artemis ACCOUNT_ID
tum-mcp discover zulip ACCOUNT_ID
tum-mcp scope artemis ACCOUNT_ID --course COURSE_ID --sensitive --workspace
tum-mcp scope zulip ACCOUNT_ID --channel CHANNEL_ID
```

`connect` takes no arguments or connection options. Move with up/down, toggle
services with Space, and press Enter. Choose a browser when more than one is
installed. Only selected tabs open in one temporary browser context. Moodle,
Artemis and Zulip all follow this flow; no separate Moodle login is needed.
Sign-in/MFA stays in the browser. `TERM=dumb` uses numbered prompts. Ctrl+C
cancels and retains completed connections. Old service/campus arguments and
`--service`/`--auth` flags are rejected before any browser opens.

Detection covers Chrome, Edge, Brave, Chromium, Vivaldi, Opera and selected
preview channels. Set `TUM_MCP_BROWSER` to an executable path for another
compatible Chromium build. Browsers must permit Playwright automation. Firefox
and Safari use different protocols and are outside this integration.
Only service-owned cookies are saved; identity-provider cookies are discarded
when the temporary browser closes. Existing browser profiles are never imported.

Zulip uses its read-only `/json/` routes with the browser session; no API key is
required. Reconnect through the same selector when a session expires. Existing
API-key records remain readable for compatibility, but key entry is not part of
onboarding. See [Zulip's dispatcher](https://github.com/zulip/zulip/blob/12.0/zerver/lib/rest.py).
Browser login and Artemis Git access remain
separate capabilities. Existing scopes survive reconnection; new identities start
with empty scopes. Private channels additionally require `--private-channel ID` while
remaining in `--channel ID`. `--sensitive` enables own Artemis participation and
feedback reads; `--workspace` separately enables preparation under the configured
workspace root. Neither authorizes submission.

On 24 October 2026, both saved browser-session credentials passed identity
verification through the actual MCP process. Scoped Artemis exercise listing and
statement retrieval, plus a bounded Zulip channel search, passed. No participation
was started, code pushed, message sent, or read flag changed by these checks.

Settings live outside the installed package in `TUMMCP/config/preferences.json`.
The default data directory is beside the legacy `TUMMoodle` directory on each OS.
Existing Moodle data and its native-store identity are retained in place. New
campus connections deliberately do not read or migrate native-store secrets;
reconnect each service once to use local-file storage. The combined MCP process
uses that storage for all `moodle_*` compatibility tools. The separate Moodle-only
installer keeps its native-store default.
Previously imported Artemis Git tokens also need re-importing into the new store;
browser sign-in does not import them or open the old native store.

New Moodle sessions live under `TUMMoodle/local-session/`; campus credentials live
under `TUMMCP/credentials/local/`. Each directory has an independent `session.key`.
Encrypted records and keys have owner-only permissions: 0700 directories / 0600
keys on POSIX; protected current-user DACLs on Windows through PowerShell. No
administrator privileges are requested. This avoids Keychain/Secret Service
prompts but protects less than a native store. A copy of both ciphertext and key
is sufficient to decrypt a session. Do not share, sync publicly, or package them.

Missing or damaged keys fail closed. Restore the matching key from a private
backup. To start fresh, stop clients and move the affected **local storage folder**
to a private backup before reconnecting; this also resets its stored Git tokens.
Never remove the legacy Moodle directory or downloads to repair a login.
Native-store records remain available to the older installation for rollback.

Zulip message text is retrieved live and is not persisted. Retrieved excerpts may
be transmitted to the coding agent's configured AI provider. Moodle's existing
document cache retains its documented plaintext/expiry behavior.

Course nicknames can be mapped in `mappings` using explicit per-service IDs.
The tools resolve one exact mapping; ambiguity never grants broader access.

## Diagnostics

`doctor` reads local configuration and checks runtime prerequisites. It does not
open a browser, contact campus services, decrypt sessions, or read native stores.
Saved sessions are **Not verified** until checked. Missing optional Git/Docker
capabilities do not prevent course reads. Client registration is distinguished
from activation; the host must confirm a running MCP connection after setup.

Use `doctor --live` for bounded authenticated identity checks on saved local
sessions. This reads Moodle's course overview and Artemis/Zulip identity only;
it does not broaden content scopes. `doctor --json` emits schema-versioned JSON
without terminal styling; combine both flags for live automation. Paths appear
in JSON for troubleshooting. Default diagnostics do not create state folders.

## Assignment workspaces and tests

The user requests `artemis_prepare_workspace` with explicit account/course/
exercise IDs and graded/practice mode. Missing participation returns
`ACTION_REQUIRED`; preparation never starts it. Offline IDE access must be
affirmatively enabled. Import an existing participation-scoped Git token locally:

```sh
tum-mcp workspace connect-git ACCOUNT_ID COURSE_ID EXERCISE_ID
```

The hidden clone URL must match the server-reported participation repository.
It is sanitized before storage/output. A narrow Git credential helper supplies
the token only to that HTTPS repository. Clone uses no inherited credential
helpers, external Git protocols, hooks, submodules, or dependency installers.
Existing unrelated/dirty work is preserved. Local receipt files contain IDs,
workspace, mode, branch, and revision, never tokens.

Configure `test_recipes` locally with a unique `name`, exact `account_id`,
`course_id`, an image pinned as `registry/image@sha256:DIGEST`, an `argv` array,
`timeout_seconds`, and `verification_level` (`targeted` by default, or `full`
after reviewing the complete test command). Submission preflight requires a
passing `full` recipe for the exact content. Review the recipe and obtain its
image/dependencies as a separate step. The runner uses an already-present image (`--pull=never`), no
network, no home/keychain/SSH mounts, a read-only container filesystem, dropped
capabilities, and CPU/memory/process/time/output limits. Only the assignment
workspace is mounted read/write, with its Git metadata mounted read-only.
Receipts record exit status, source fingerprints, recipe, image, timestamps,
and bounded output. A missing engine or recipe fails
closed. Evidence is encrypted/authenticated outside the assignment directory;
editing a workspace JSON file cannot fabricate a passing receipt. Ordinary
host-native testing does not acquire these isolation guarantees.

## Client and skill setup

`setup --client codex` prepares a local plugin/marketplace entry using the
portable Agent Plugins schemas. Enable it in
Codex Plugins, restart, and verify real tool and skill loading. Disable the legacy
TUM Moodle plugin when switching so duplicate tools/skills are not active.
The old installation remains available for rollback. Setup reports required UI
steps and never equates writing files with activation.

The Codex adapter uses a contained Node launcher to pin the managed Python in
isolated mode; portable stdio manifests require a bare or contained executable.
The shipped pack contains exactly three skills: `tum-moodle`, `tum-artemis`
and `tum-zulip`. They share known account/course context instead of repeating
setup, and load task-specific references only when needed. Artemis combines
statement/workspace help, local implementation, feedback and submission preview;
Zulip combines factual research and catch-up. Remote actions remain disabled.

`scripts/verify_campus_clients.py` checks real host discovery in disposable
profiles without running a model or changing actual user profiles. Host/model
routing quality is a separate evaluation from structural and discovery checks.
Claude's invocation metadata follows each site's selected policy; automatic
selection is enabled by default and never grants permission for a mutation.

`setup --client cursor` writes `~/.cursor/mcp.json`.
`setup --client antigravity` writes `~/.gemini/config/mcp_config.json`; an existing
legacy `~/.gemini/antigravity/mcp_config.json` is reused when no current file exists.
Both merge the `tum` stdio entry and preserve unrelated settings.
From WSL, append `--host windows` to any client setup command to target its
Windows profile. The generated `wsl.exe` command pins the distribution, Linux
user, managed Python and data paths, so clients share the WSL connection.
Use the same host option on uninstall. Native Windows uses the default host.
`doctor` in WSL shows local and Windows client registrations separately.
See [the WSL guide](setup.md#wsl) for interop requirements. Conflicting or
invalid configuration is preserved with an actionable error. Reload MCP servers
in the host after setup; actual host activation is not certified by writing files.
See the official [Cursor MCP documentation](https://cursor.com/docs/mcp) and
[Antigravity MCP documentation](https://antigravity.google/docs/mcp).

These two adapters install MCP configuration only. Export the workflow skills
below and install them using the host's documented skill mechanism after review.
This avoids claiming equivalent invocation controls across clients. No new
Cursor/Antigravity model-routing or native desktop activation result is claimed.
`uninstall --client cursor` and `uninstall --client antigravity` remove only an
unchanged managed entry; sessions and personal work stay intact.

```sh
tum-mcp skills list
tum-mcp skills inspect tum-zulip
tum-mcp skills customize tum-zulip
tum-mcp skills diff tum-zulip
tum-mcp skills validate
tum-mcp skills export /path/to/new/export-folder
```

Personal overrides stay in the user configuration directory. Installation
refuses conflicting/customized copies rather than overwriting them. Review an
exported diff and retain a backup when applying an update. Structural validation
checks metadata, real tool references, and invocation policy. It does not measure
model activation precision or recall. The original 95% targets, repeated held-out
trials, and two review passes have not been demonstrated for this pilot.
Export refuses symbolic links and
does not overwrite an existing destination.

The activation corpus contains 140 cases grouped by website, with development
and held-out partitions. It covers explicit/implicit requests, unrelated
negatives, missing credentials and unsupported-action handoffs. Old trial
results must not be reused against the consolidated skill labels. `skills evaluate TRIALS.jsonl` scores supplied fresh-session
records separately by host/version/model. Each record follows `Trial` in
`skill_validation.py` and references its retained raw trace by SHA-256. The scorer
does not launch other agents or certify the supplied traces, summary quality,
or platform acceptance. Inspect traces and backend effects before approving a
release; no measured activation accuracy is claimed by the structural checks.

## Release scope

Version 0.5.1 has automated installation, browser transport, storage and MCP
checks on macOS, Windows, Linux, and both distribution engines on WSL 3.0.3.
These checks use synthetic pages and credentials. Fresh human SSO/MFA and
desktop-client activation on every target remain separate manual checks, as do
host/model skill-selection trials. Remote workflows also need a
trusted approval/host credential boundary and safe practice verification before
they can be exposed. Browser sign-in alone does not establish a saved backend connection.

Maintainer checks include the relevant tests, a reviewed tarball inventory,
integrity checks, and an isolated consumer install. Never publish or stage npm
packages as a test. Review and authorization of a registry upload are separate
from a GitHub source push.
`tum-mcp status` reports registry state as `not_checked`, since it inspects local
configuration without making registry requests.
