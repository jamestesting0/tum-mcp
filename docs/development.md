# Development

The npm package is the distribution. Its wheel contains one Python package,
`src/tum_mcp/`, with peer `moodle/`, `artemis/` and `zulip/` provider packages.
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
npm run test:package-lifecycle
```

Python 3.13 is the managed runtime. Install Tesseract for OCR tests. Default tests
use synthetic sources and credentials. No language-server installation is needed.
Studocu fixtures must likewise use synthetic documents and local transports, never
browser cookies, personal account details or live downloaded PDFs. The extension
is off by default; validate both selected and unselected skill packs.
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
| Public upgrade | Published 0.9.0, repair, ownership conflicts and removal |
| Native platform | OS credential/ACL behavior; WSL Windows browser transport on both engines |

Study integration fixtures build the private rich regression fixture once, then copy it into a fresh
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
Upgrade checks start from public 0.9.0 and cover all five clients, optional-extension
retention, customized-file conflicts, failed preparation, runtime repair and
removal that preserves work/credentials. Earlier releases are outside this matrix.
The package-lifecycle check uses a local synthetic registry and real isolated
global npm prefixes to verify downloads, backend validation, replacement,
failure ordering and one-command removal. It does not publish a test release.
All five jobs must pass on the exact pushed commit before completion is claimed.
Desktop jobs additionally install the optional hash-locked CPU recognizer and
transcribe the synthetic speech fixture; supported Apple Silicon runners also
exercise MLX. This explicit test downloads public pinned model files, never campus
recordings. Ordinary test runs skip it unless `TUM_MCP_LECTURE_ASR_INTEGRATION=1`.
Recognition runs before package lifecycle checks to expose native dependency
failures early. Windows also runs the affected browser/UTF-8 fixture checks first.
Its complete job budget is 35 minutes for native ACL and subprocess coverage;
the macOS and Linux budgets remain 25 minutes.

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
| `src/tum_mcp/bundled/skills/` | Canonical versioned source of reading, study, audio and video skills and their references/assets |
| `src/tum_mcp/video_*.py`, `bundled/video_runtime/` | Video Notes contracts, lint, media checks, orchestration and the isolated render worker |
| `npm/` | Private-runtime installation, updates, integrity and cleanup |
| `tests/` | Synthetic backend, package and owned-browser checks |

Client setup installs managed copies of the repository's skills; those copies are
outputs, not another source tree. Use `skills customize` for a personal override.
The Codex adapter generates a small host plugin to load skills and MCP together.

Extraction uses bounded subprocesses. POSIX enforces CPU/process-group limits;
Windows terminates the worker and observed children. Study imports and preview
paths are confined to the chosen project. Course sources never become agent rules.
The preview's only write endpoint accepts bounded same-origin comment operations.
Comments use private project files and optimistic revisions; comments and quoted
material remain untrusted data for the skill.

## Study renderer

Author `app/content.json` and optional `app/exercises.json`; legacy `study/` remains supported. Formula blocks use LaTeX compiled locally into safe
native MathML; legacy MathML remains accepted. Unit `path` labels group the outline
without changing learning-progress revisions. Shared modules render all units;
content changes do not require a framework or per-unit HTML.

Shared renderer assets live in `src/tum_mcp/bundled/course_app/site/`; they are the
source of truth for layout, styling and interaction. Design tokens sit at the top of
`styles.css`, and the owned-browser fixtures in `tests/integration/` hold the UI
regressions. The preparation skills describe content and point to the app instead
of restating its styling, so app changes need no skill edits unless an authored field
or its meaning changes. Remove a template file by moving it to
`RETIRED_TEMPLATE_FILES`: builds then delete unedited copies and publication removes
them from managed sites. The shipped component preview is deliberately minimal;
richer learning pilots live in `tests/fixtures/course_app/`. Local agent notes and
screenshots belong in ignored `docs/local/` or `.omo/`. Keep real course projects,
session files, databases, downloads and environment files out of artifacts.

## Manual checks

Use an installed artifact outside the checkout. Confirm host discovery, complete
Chromium sign-in/MFA, read a PDF and forum, download a file, then restart and check
session reuse. Automated synthetic sign-in does not certify human SSO on every OS.
For UI changes, exercise the generated app at narrow/wide widths in both themes;
check keyboard navigation, reduced motion, source links and retained progress.

## Optional Video Notes runtime

`install video-notes` only selects the workflow. `tum-mcp video-notes runtime install`
creates a uv venv per lock under the data directory from
`bundled/video_runtime/requirements.lock` (universal, hash-pinned). Everything is a
wheel except `pycairo`, `manimpango` and `srt`, which build from hashed sources; the
locked `pkgconf` wheel is installed first and provides `pkg-config`. Regenerate the
lock with the command in its header. Helper code (`vnotes/`, `worker.py`, fonts) runs
from the package, so changing it never reinstalls the runtime; it does change the
render profile and therefore the chapter cache. Default tests use a fake worker and
the synthetic media in `tests/fixtures/video/` (`generate.py` recreates them). Set
`TUM_MCP_VIDEO_RENDER_INTEGRATION=1` to install the real runtime into a temporary
data directory and render, mix, check and publish a synthetic video; the browser
playback tests also run WebKit when Playwright's WebKit is installed.

## Optional Lecture extension

Base setup exposes five workflows and no `tum_live_*` tools. `install lecture`
records explicit selection, refreshes managed clients and provisions the optional
recognizer only when requested/supported. `--no-asr` keeps captions/imported WebVTT.
Heavy recognition dependencies and model weights stay outside the base environment
and package artifacts. `lecture_processing/` owns bounded media/ASR evidence;
`lecture_content.py`, `lecture_data.py` and `lecture_assets.py` validate the notes
and figures used by the static app. See [the workflow guide](lecture-notes.md).

Use `skills validate --all` to check the packaged optional workflow without installing
it; default validation checks the selected workflows. Activation statistics remain
unmeasured until genuine fresh-session trial records exist. Default tests use
synthetic media and course data. `test:consumer` and `test:upgrade` exercise optional
install/update/export/removal from an actual local npm artifact. Never publish or
stage npm as a test.
