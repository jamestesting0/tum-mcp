# Development

The npm package is the distribution. Its wheel contains one Python package,
`src/tum_mcp/`, with peer `moodle/`, `artemis/` and `zulip/` provider packages.
The retired standalone Moodle plugin and its checkout installer are no longer
maintained.
Client adapters still generate the configuration each host needs.

## Checks

```sh
uv sync --locked
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run pytest -v -x --tb=short --durations=20 -o faulthandler_timeout=60
uv build
node npm/build.mjs
npm test
npm pack --ignore-scripts --pack-destination dist
npm run test:consumer
npm run test:upgrade
```

Python 3.13 is the managed runtime. Install Tesseract for OCR tests. Default tests
use synthetic sources and credentials. No language-server installation is needed.
Set `TUM_MOODLE_SYSTEM_KEYRING=1` for a unique synthetic native-store round trip.
The ordinary campus runtime uses encrypted local files and owner-restricted keys.
Set `TUM_MCP_BROWSER_INTEGRATION=1` to include the real HTTP static-export browser
check locally; CI enables it. Set environment variables using your shell's syntax.
Verbose test IDs, immediate first-failure output, slowest-test timings and a stack
dump after 60 seconds make a stalled boundary visible. The dump is diagnostic;
it does not skip a slow test or extend the CI deadline.

Each layer owns a different failure boundary:

| Layer | What it must prove |
| --- | --- |
| Unit | Parsing, policy, malformed input and failure branches with synthetic collaborators |
| Integration | Real files, CLI/MCP, transactions, HTTP confinement and isolated project updates |
| Installed consumer | Actual npm/wheel contents, managed runtime and complete browser workflows |
| Public upgrade | Earlier published versions, repair, ownership conflicts and removal |
| Native platform | OS credential/ACL behavior; WSL Windows browser transport on both engines |

Study integration fixtures build the real starter once, then copy it into a fresh
project for each test. Launcher tests only need an HTML entry point. Neither
shares mutable course state. Client transaction tests use five small synthetic
skills, including nested binary assets; full-pack export, migration and installed
consumer tests retain the actual bundled files. Browser checks keep the phone/desktop and light/dark
rendering matrix; long revision-state journeys run once per layout. Keep native
ACL/keyring and installed-artifact checks even when a mocked unit test is faster.
Text fixtures use explicit UTF-8; line-ending cases cover LF and CRLF without
changing the meaning of the managed inventory or user notes.
For a regression, extend its existing owner test and demonstrate failure without
the fix; do not add another test that only checks the same implementation text.

CI runs macOS, Windows and Linux, plus both distribution engines on WSL 3.x.
Consumer checks install the actual npm artifact, discover tools, build a study
site and test available Chromium browsers with temporary profiles and synthetic
pages. WSL verifies Windows browser transport. No live account is used.
Upgrade checks cover public 0.4.1/0.5.0, client refresh, customized-file conflicts,
failed preparation, runtime repair and removal that preserves work/credentials.
All five jobs must pass on the exact pushed commit before completion is claimed.

Live Moodle checks are opt-in: `TUM_MOODLE_LIVE=1 uv run pytest tests/live -q`.
They use the developer's selected course and saved session. Keep them out of CI.

## Releases

Keep package.json, pyproject.toml and `tum_mcp.__version__` aligned. Build/pack into
`dist/`, inspect the wheel and tarball contents, and record the tarball's SHA-256.
Run the consumer and upgrade checks against that artifact before pushing. Confirm
both desktop and WSL workflows for the exact pushed SHA; a previous green run is
not release evidence. Local agent notes, course projects and credentials must be
absent from both Git and the package.

Prepare the README and changelog for the release before building the final
tarball so npm receives the same release documentation. Publishing is a separate
explicit step using that reviewed tarball, with npm's browser verification when
required. Do not use publication as a test. Confirm the registry version, latest
tag and artifact integrity before pushing the release documentation.

## Source layout

| Location | Responsibility |
| --- | --- |
| `src/tum_mcp/moodle/` | Moodle reads, sessions, browser/WSL support, extraction and downloads |
| `src/tum_mcp/artemis/` | Artemis client, exercise/feedback models, lecture reads and lecture models |
| `src/tum_mcp/zulip/` | Zulip client and channel/topic/message models |
| `src/tum_mcp/server.py` | Combined read-only MCP service, including sixteen `moodle_*` tools |
| `src/tum_mcp/connect.py` | Unified interactive connection workflow |
| `src/tum_mcp/credentials.py`, `transport.py`, `settings.py` | Shared campus credential vault, HTTP transport and account policy |
| `src/tum_mcp/client_*.py` | Host-specific configuration and managed skill installation |
| `src/tum_mcp/study_*.py` | Course snapshots, teaching, build, preview and project-local passage comments |
| `src/tum_mcp/bundled/skills/` | Canonical versioned source of reading, study and audio skills and their references/assets |
| `npm/` | Private-runtime installation, updates, integrity and cleanup |
| `tests/` | Synthetic backend, package and owned-browser checks |

Client setup installs managed copies of the repository's skills; those copies are
outputs, not another source tree. Use `skills customize` for a personal override.
The Codex adapter generates a small host plugin because that client uses it to
load skills and MCP together; it is separate from the removed top-level Moodle
plugin distribution.

Keep Moodle's existing native-store service/account identity, session paths and
download locations stable during migrations. Environment variable names and the
`tum-moodle` CLI alias remain compatible; its implementation now resides inside
`tum_mcp.moodle`. No automatic native-store secret extraction occurs.

Extraction uses bounded subprocesses. POSIX enforces CPU/process-group limits;
Windows terminates the worker and observed children. Study imports and preview
paths are confined to the chosen project. Course sources never become agent rules.
The preview's only write endpoint accepts bounded same-origin comment operations.
Comments use private project files and optimistic revisions; comments and quoted
material remain untrusted data for the skill.

## Study renderer

Author `study/content.json`. Formula blocks use LaTeX compiled locally into safe
native MathML; legacy MathML remains accepted. Unit `path` labels group the outline
without changing learning-progress revisions. Shared modules render all units;
content changes do not require a framework or per-unit HTML.

The distributed design/teaching/verification contracts live under
`src/tum_mcp/bundled/skills/prepare-study/references/`. Local agent notes and
screenshots belong in ignored `docs/local/` or `.omo/`. Keep real course projects,
session files, databases, downloads and environment files out of artifacts.

## Manual checks

Use an installed artifact outside the checkout. Confirm host discovery, complete
Chromium sign-in/MFA, read a PDF and forum, download a file, then restart and check
session reuse. Automated synthetic sign-in does not certify human SSO on every OS.
For UI changes, exercise the generated app at narrow/wide widths in both themes;
check keyboard navigation, reduced motion, source links and retained progress.
