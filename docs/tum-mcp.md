# TUM MCP guide

Package: `@jamestesting888/tum-mcp`, CLI: `tum-mcp`, backend: Python 3.13.
The package combines read-only course retrieval, managed client installation and
five base course workflows and three optional extensions.

## Current capabilities

The sixteen `moodle_*` tools provide materials, announcements, forums and
own grades, feedback and submission reads. Artemis adds
available-course metadata, lectures and learning units, student PDF attachments,
released non-quiz statements and permitted exact-commit feedback. Zulip provides
bounded channel/topic search and cited discussion reads.

Website access is read-only. There are no public exercise workspace, test-run,
submission, start, deployment, rebuild or push workflows.
Local downloads, source inventories, study-site builds and checkpoint storage
are local operations; they do not post, submit or mark campus content as read.

Artemis lecture reads use the student overview/detail endpoints, verify the
selected course and omit unreleased units and personal completion records.
`artemis_get_attachment` retrieves a bounded page range from the student PDF,
which excludes hidden slides, and optionally saves that copy locally. Original
staff links are never fetched. Video/online links remain cited references;
unsupported or external content is reported as a retrieval gap.

Lecture routes were checked against the
[Artemis source](https://github.com/ls1intum/Artemis/blob/88824427f7ea38512606824c58b8858e539eb2eb/src/main/java/de/tum/cit/aet/artemis/lecture/web/LectureResource.java)
and the
[student file boundary](https://github.com/ls1intum/Artemis/blob/88824427f7ea38512606824c58b8858e539eb2eb/src/main/java/de/tum/cit/aet/artemis/core/web/FileResource.java).
Synthetic fixtures are the default. Live checks remain private and relevant to the requested task.

## Build and test the local package

For normal installation, use `npm install --global @jamestesting888/tum-mcp@latest`
and `tum-mcp setup --client codex`. The following commands are for maintainers.

```sh
uv sync --locked
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
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
recorded separately. Campus sessions use permission-restricted local keys.
CI checks clean installation, updates, removal, MCP discovery and synthetic
browser workflows on macOS, Windows, Linux and both WSL engines. See the
[development guide](development.md#checks) for the verification layers.

`update` downloads and validates the latest release, replaces the invoked npm
installation and refreshes previously configured clients. `update --local`
refreshes the installed version without npm. Retained runtimes keep pinned
clients working, and newer installed versions are not silently downgraded.
[Update and removal behavior](setup.md#update-and-remove) covers ownership
receipts, conflict handling and explicit cleanup. `uninstall` removes managed
clients and npm; `--client NAME` or `--keep-package` retains the package.
Customized files and saved data are preserved. If interrupted setup leaves `setup.lock`,
confirm that no setup process is running before removing that directory locally.
An invalid or incomplete runtime is never selected for serving. Failed validation
clears its ready marker so explicit setup can rebuild it; older runtimes remain
available to existing client registrations. Use an older reviewed package and
rerun its setup to restore that runtime, reviewing any client configuration diff.

For platforms outside the bootstrap targets, the source installation needs
Python 3.13+, uv, and Git: run `uv sync --locked`, then
`uv run tum-mcp setup --client generic` from the checkout. An installed Chromium browser is needed for
browser onboarding. See [setup](setup.md) for browser choices and WSL.

<a id="connections-and-scopes"></a>

## Connections and read access

```sh
tum-mcp login
tum-mcp doctor
tum-mcp discover artemis ACCOUNT_ID
tum-mcp discover zulip ACCOUNT_ID
tum-mcp --help
tum-mcp study build --help
```

`login` takes no arguments or connection options. Move with up/down, toggle
services with Space, and press Enter. Choose a browser when more than one is
installed. Only selected tabs open in one temporary browser context. Moodle,
Artemis, Zulip and TUMonline all follow this flow.
Sign-in/MFA stays in the browser. `TERM=dumb` uses numbered prompts. Ctrl+C
cancels and retains completed connections.

Detection covers Chrome, Edge, Brave, Chromium, Vivaldi, Opera and selected
preview channels. Set `TUM_MCP_BROWSER` to an executable path for another
compatible Chromium build. Browsers must permit Playwright automation. Firefox
and Safari use different protocols and are outside this integration.
Only service-owned cookies are saved; identity-provider cookies are discarded
when the temporary browser closes. Existing browser profiles are never imported.

Zulip uses its read-only `/json/` routes with the browser session; no API key is
required. Reconnect through the same selector when a session expires.
See [Zulip's dispatcher](https://github.com/zulip/zulip/blob/12.0/zerver/lib/rest.py).
For Moodle, Artemis and Zulip, read access follows the authenticated account's server permissions. No local course,
channel, private-channel or personal-feedback grant is required. Older saved grant
fields remain readable for compatibility and do not restrict read access. Agents
prefer relevant current-semester courses and channels, inspect metadata first, and
page through only the content needed for the request. Explicit older-course requests
remain supported. Server-denied content, staff-only material and remote writes stay unavailable.

### TUMonline permissions

TUMonline has a separate, account-specific policy. New connections allow study
names and degrees, public course catalog metadata and public curriculum positions
for a selected course by default. The position endpoint is anonymous: no student
session or identifier is sent. These positions are a partial view, not a full
program curriculum or personal enrollment list; page order can change upstream.
Course catalog searches accept a title or course number using 2–80 letters,
numbers, spaces, dots, underscores, plus signs, slashes or hyphens; continue pages
with the same query.
Full curriculum structure is unavailable because its public API requires a separate
service account. Grades and progress need
separate consent, but their readers are not yet available; exams, admission,
account, other IT and miscellaneous readers are also unavailable. No campus write
operations are provided.

Run `tum-mcp manage tumonline --show` to inspect the policy and
`tum-mcp manage tumonline` in a terminal to select permissions with Space and
save with Enter. Studies and courses can be allowed or revoked; the remaining
categories are shown as unavailable and cannot be selected. On basic terminals,
the command offers a numbered text prompt instead.
When multiple accounts exist, add `--account ACCOUNT_ID`. Reconnecting preserves
the policy. `tum-mcp manage tumonline --disconnect` removes the local TUMonline
credential and retains the policy; it does not revoke remote sessions. An expired
session requires `tum-mcp login` again. If the policy is missing or corrupt, use
`tum-mcp manage tumonline --account ACCOUNT_ID --disconnect` to remove that saved
session without resetting permissions or affecting other providers.

The policy governs what these TUMonline tools return to all MCP clients sharing
the same local configuration. A local program running as the same user can access
local files independently, and this policy does not govern other providers' tools,
including Moodle's own grades tools. Study names are personal and permitted results
may be transmitted to your configured agent or its AI provider. TUMonline's study
chooser can contain extra personal fields in its upstream response; the integration
holds that bounded response only in memory, projects the permitted fields, and does
not save the response body. Revoking a permission prevents subsequent reads, but
cannot recall a response already delivered to a client.

Settings live outside the installed package in `TUMMCP/config/preferences.json`.
Moodle sessions live under `TUMMoodle/local-session/`; Artemis, Zulip and TUMonline credentials
live under `TUMMCP/credentials/local/`. Each directory has an independent `session.key`.
Encrypted records and keys have owner-only permissions: 0700 directories / 0600
keys on POSIX; protected current-user DACLs on Windows through PowerShell. No
administrator privileges are requested. This avoids native credential-store
prompts but protects less than a native store. A copy of both ciphertext and key
is sufficient to decrypt a session. Do not share, sync publicly, or package them.

Missing or damaged keys fail closed. Restore the matching key from a private
backup. To start fresh, stop clients and move the affected **local storage folder**
to a private backup before reconnecting. Keep downloaded course materials when
repairing a login.

Zulip message text is retrieved live and is not persisted. Retrieved excerpts may
be transmitted to the coding agent's configured AI provider. Moodle caches
documents and extracted text locally in plaintext.

Course nicknames can be mapped in `mappings` using explicit per-service IDs.
The tools resolve one exact mapping; ambiguity never grants broader access.

## Diagnostics

`doctor` reads local configuration and checks runtime prerequisites. It does not
open a browser, contact campus services, decrypt sessions, or read native stores.
Saved sessions are **Not verified** until checked. Git and Docker are not
prerequisites. Client registration is distinguished
from activation; the host must confirm a running MCP connection after setup.

Use `doctor --live` for bounded authenticated identity checks on saved local
sessions and optional GitHub CLI authentication. Campus checks read Moodle's
course overview and Artemis/Zulip identity only;
it does not change server permissions. `doctor --json` emits schema-versioned JSON
without terminal styling; combine both flags for live automation. Paths appear
in JSON for troubleshooting. Default diagnostics do not create state folders.

## Study workflows

`read-content` retrieves course information across the three websites. `sync-course`
uses read-only local status to initialize an explicitly chosen available course or
reconcile an existing project. Incomplete state is preserved for recovery.
`prepare-study` authors lessons; `prepare-exercises` authors guided released sheets
in the same local app. See the
[study guide](study.md) for examples, state structure and helper commands.

One project holds one course. Source revisions, coverage and course knowledge
avoid unnecessary rereads. Edited files and customized site templates are kept;
changed sources invalidate dependent units. Study projects, originals and learner
progress are preserved during package updates/removal.

## Client and skill setup

`setup --client codex` prepares a local plugin/marketplace entry using the
portable Agent Plugins schemas. Enable it in Codex Plugins, restart, and verify
real tool and skill loading. Setup reports required UI steps and never equates
writing files with activation.

The Codex adapter uses a contained Node launcher to pin the managed Python in
isolated mode; portable stdio manifests require a bare or contained executable.
The base pack contains five skills: `read-content`, `sync-course`,
`prepare-study`, `prepare-exercises` and `publish-course`. Optional extensions add
`prepare-lecture`, `sync-studocu` and `audio-notes`; choose them with `tum-mcp install`.
Website-specific retrieval guidance is loaded from references within read-content.
Teaching and content guidance lives with prepare-study; the course app and its
synthetic example ship as reusable assets and define the site's design.
Audio Notes converts prepared content into category tracks and maintains coverage,
scripts, voice settings, candidates and archives under the course's `audio/` root.
Publish Course uses host GitHub CLI authentication to create a private repository
and a public Pages website after explicit publication consent. It chooses a course
and semester name, updates the same site after successful study builds, and shows
the hosted URL alongside the local launcher URL. No tokens or original course
downloads are uploaded. See [publishing](study.md#publish-a-study-website).
Old seven-skill, three-site and separate init/update packs are retired only when
managed copies remain unchanged. Personal overrides are preserved and require a deliberate merge into
the consolidated workflows before export.

`scripts/verify_campus_clients.py` checks real host discovery in disposable
profiles without running a model or changing actual user profiles. Host/model
routing quality is a separate evaluation from structural and discovery checks.
Claude's invocation metadata follows each workflow's selected policy; automatic
selection is enabled by default and never grants permission for a mutation.

`setup --client cursor` writes `~/.cursor/mcp.json` and installs the active skills
under `~/.cursor/skills/`.
`setup --client antigravity` installs the same skills under `~/.gemini/config/skills/`
and writes `~/.gemini/config/mcp_config.json`; an existing
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

Both adapters install complete skill bundles, including references and website
assets. Existing MCP-only registrations gain skills through setup or `tum-mcp update`.
Ownership receipts track installed files: updates replace only unchanged managed
files, and uninstall removes only unchanged managed files and the MCP entry.
An edited managed file blocks that client's update or uninstall for review.
Unrelated skills, extra user files, sessions and personal work stay intact.
Without an ownership receipt, uninstall preserves manually installed skills.
Restart the client and verify that its skills and MCP tools appear; writing files
does not establish model-routing quality or native desktop activation.
See the official [Cursor skills guide](https://cursor.com/help/customization/skills)
and [Antigravity skills guide](https://antigravity.google/docs/skills?app=antigravity-ide).

Manual export remains available for other clients or a separate reviewed copy:

```sh
tum-mcp skills list
tum-mcp skills inspect read-content
tum-mcp skills customize read-content
tum-mcp skills diff read-content
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

The activation corpus covers the reading, study and audio workflows, with
development and held-out partitions. It covers explicit/implicit requests, unrelated
negatives, missing credentials and unsupported-action negatives. Old trial
results must not be reused against the consolidated skill labels. `skills evaluate TRIALS.jsonl` scores supplied fresh-session
records separately by host/version/model. Each record follows `Trial` in
`skill_validation.py` and references its retained raw trace by SHA-256. The scorer
does not launch other agents or certify the supplied traces, summary quality,
or platform acceptance. Inspect traces and backend effects before approving a
release; no measured activation accuracy is claimed by the structural checks.

## Verification and release scope

Local source validation, real MCP protocol discovery, installation/migration
checks and browser study-site QA are separate gates. Model-routing accuracy and
human SSO/MFA on every desktop are not established by schema tests or generated
configuration. No measured skill-selection accuracy is claimed.

The existing desktop/WSL CI matrix must pass on the exact pushed revision before
it is described as verified. Test data and public fixtures are synthetic. Real
course material, local agent notes and screenshots stay under ignored local paths.
Maintainer checks include a reviewed tarball inventory, integrity checks and an
isolated consumer install. Never publish or stage npm packages as a test. Registry
publication is an explicit maintainer action.
`tum-mcp doctor` reads local configuration and does not check the npm registry.
