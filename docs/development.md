# Development

The npm package is the distribution. Its wheel contains one Python package,
`src/tum_mcp/`, with peer `moodle/`, `artemis/` and `zulip/` provider packages.
Client adapters still generate the configuration each host needs.

## Checks

```sh
uv sync --locked
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run pytest -n logical --dist loadfile --tb=short --durations=20 -o faulthandler_timeout=120
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

For a local Study and Exercises draft in a single-author session, first run
`study report PROJECT --section coverage-plan --preparation ID --json`, then
`review plans PROJECT --item ITEM` with one `--item` per batch item. Copy the
packet's answer shape, check and correct the plans, and record the verdicts using
`review plan-record PROJECT --file ANSWERS --provenance same`. This provenance
qualifies for draft readiness. Independent review has its own gate. Run scoped
`study lint` during authoring, `study build PROJECT --local-only` for the combined
draft, then both visual and interaction checks with `--phone` before checking
`study report PROJECT --section readiness --batch BATCH --json`.
`-n logical --dist loadfile` (pytest-xdist) runs one worker per logical CPU and keeps
each file's module-scoped browser on one worker; drop it to debug a test serially.
(`-n auto` counts physical cores and starts only two workers on 4-vCPU hosted runners.)

Every test gets private `TUM_MCP_DATA_DIR`, `TUM_MOODLE_DATA_DIR` and
`TUM_MOODLE_DOWNLOAD_DIR` folders from an autouse fixture in `tests/conftest.py`, so a
developer's real installation, extensions and credentials never change a result;
configuration follows the data folder unless a test sets `TUM_MCP_CONFIG_DIR`. Only
`live` tests use the real profile. On Windows, the same file replaces the PowerShell ACL
call for private folders with a no-op because each call costs about a second; tests marked
`native_acl` (`test_windows_permissions.py`) apply and inspect real ACLs, and the
installed consumer, upgrade and lifecycle checks use the real code path.
Optional extensions are off by default; validate both selected and unselected skill
packs.

For semester/access changes, run the affected provider's checks:

```sh
uv run pytest -q tests/unit/test_parsing.py tests/integration/test_moodle_semesters.py
uv run pytest -q tests/unit/test_artemis_boundaries.py tests/unit/test_artemis_lectures.py tests/integration/test_artemis_semesters.py
uv run pytest -q tests/integration/test_semester_preparation.py
```

These use paginated synthetic enrollments, active/archive listings, authorized older
and unlisted courses, and denied/revoked access through the real HTTP and MCP tool
layers; no campus session is needed. They assert default versus expanded discovery,
request counts, CLI flags and WS23 source-to-project binding when a newer offering
has the same title. Keep the existing transport, session, extraction
and installed-client checks.
The package includes `tzdata` for hosts without an IANA timezone database. The semester
regression disables system timezone paths in a subprocess to cover that Windows boundary.

Set `TUM_MOODLE_SYSTEM_KEYRING=1` for a unique synthetic native-store round trip.
The ordinary campus runtime uses encrypted local files and owner-restricted keys.
Set `TUM_MCP_BROWSER_INTEGRATION=1` to include the real HTTP static-export browser
check locally; CI enables it. Set environment variables using your shell's syntax.
Consumer checks default to full study journeys on every discovered browser.
CI sets `TUM_MCP_STUDY_BROWSER_JOURNEYS=primary`: the first browser on each desktop
OS and WSL engine runs the full installed study journey; every additional browser
runs a short installed UI check. All browsers retain real pipe transport, synthetic
cookie and encrypted-session checks. The shorter journey covers module loading,
content/flashcard/practice views, saved progress after reload, keyboard navigation,
theme switching and phone/desktop overflow under a project URL prefix. Consumer
JSON names each browser's `studyCoverage` and records `studySeconds`. Unset the
variable or use `all` for a browser-specific investigation; other values fail
before consumer installation.

Owned loopback browsers use `launch_loopback_browser`, including local visual
checks and Windows browsers launched through WSL. On Windows it disables
Chromium's `TcpPortRandomizationWin`, which can fail local module requests with
`ERR_NO_BUFFER_SPACE` even when socket resources are available
([upstream issue](https://issuetracker.google.com/issues/572515601)). The launcher
reads and preserves Playwright's default disabled features before adding this
opt-out. A native browser regression checks the effective arguments, and installed
consumer checks verify that the option reaches Windows browsers through WSL.

Desktop checks run two independent jobs per OS so source and installed coverage
proceed concurrently. `Source tests (OS)` runs Ruff (Linux only), the complete pytest
suite in parallel, including native recognition, CUDA libraries, video rendering and
the native keyring, then `uv build`. `Installed package (OS)` builds and inspects the
npm artifact and runs the Node tests, package lifecycle, consumer and 0.9.0 upgrade
checks. WSL keeps one job per engine. All eight exact-revision checks (three source,
three installed, two WSL) are required.

The broad checkout study journey runs on Linux. macOS and Windows deselect only
`tests/integration/test_study_browser.py::test_study_website_journeys_pass_in_the_checkout`;
their full installed journeys still exercise that fixture. Ruff lint/format runs once
on Linux, after dependency installation. Pull requests from this repository's own
`codex/**` branches skip their duplicate campaign: the push run already checks the
exact commit. Pull requests from forks are checked.

During development, run affected tests and focused regressions. Reuse applicable
passing results instead of running a complete local suite immediately before the
same required CI suite. Full integration/release coverage may come from that
exact-revision CI run; a local pass never substitutes for pending or failed native
checks. Relevant source, test, dependency or environment changes invalidate earlier
results. `AGENTS.md` is local and ignored; this tracked document carries the policy
to other checkouts.

Verbose test IDs, slowest-test timings and a stack dump after 120 seconds make a
stalled boundary visible. The dump is diagnostic;
it does not skip a slow test or extend the CI deadline. pytest-timeout fails any test
still running after 300 seconds (configured in `pyproject.toml`); under xdist the stuck
worker is replaced and reported by test name. It exists because a Chromium renderer can
die without Playwright noticing, which otherwise blocks a worker until the job budget.

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
rendering matrix pairwise, `(390, light)` and `(wide, dark)`, so every width and theme
runs without repeating each combination; long revision-state journeys run once per layout. Keep native
ACL/keyring and installed-artifact checks even when a mocked unit test is faster.
Text fixtures use explicit UTF-8; line-ending cases cover LF and CRLF without
changing the meaning of the managed inventory or user notes.
For a regression, extend its existing owner test and demonstrate failure without
the fix; do not add another test that only checks the same implementation text.

CI runs macOS, Windows and Linux, plus both distribution engines on WSL 3.x.
Consumer checks install the actual npm artifact, discover tools, build a study
site and test available Chromium browsers with temporary profiles and synthetic
pages. Every discovered browser also runs a saved-profile restart journey:
encrypted campus-session retention, exclusion of
unrelated cookies, scoped sign-in clearing, temporary-context isolation and removal.
The same journey runs from the installed wheel on all desktop OSes and both WSL
engines. WSL verifies Windows browser transport and Windows-side saved-profile
paths/permissions. No live account is used. Source coverage additionally checks
profile creation/ownership, unavailable-choice fallback and last-selection
defaults in real terminals.

macOS synthetic browser fixtures use Chromium's mock keychain to avoid OS approval
prompts in isolated runner profiles; native OS credential-store round trips remain
separate tests. Production saved profiles use native password storage. Linux source
checks run under Xvfb so the profile manager's visible-window lifecycle is exercised.

Run focused checks with:

```sh
uv run pytest -q tests/unit/test_browser_profiles.py tests/integration/test_cli_terminal.py
TUM_MCP_BROWSER_INTEGRATION=1 uv run pytest -q tests/integration/test_saved_browser_profiles.py
```

Saved profile registrations and the last browser/profile selection live in
`config/browsers.json`. Managed browser directories are owner-restricted; WSL
Windows browsers use Windows LocalAppData, while their encrypted campus-cookie
copies stay with the WSL credentials. Existing profiles cannot be added. Every
WSL persistent launch uses a Windows device path that is absolute to both the
POSIX Python client and Windows Node driver; regression tests exercise both
libraries' path normalization for drive-letter and UNC paths. Every
saved directory is checked against its application-owned location before use or
deletion. Credential forgetting deletes managed browser data and encrypted profile
sessions, retaining other browser data. The browser owns its native profile storage.
Upgrade checks start from public 0.9.0 and cover all five clients, optional-extension
retention, customized-file conflicts, failed preparation, runtime repair and
removal that preserves work/credentials. Earlier releases are outside this matrix.
The package-lifecycle check uses a local synthetic registry and real isolated
global npm prefixes to verify downloads, backend validation, replacement,
failure ordering and one-command removal. It does not publish a test release.
All eight jobs must pass on the exact pushed commit before completion is claimed.
Desktop jobs additionally install the optional hash-locked CPU recognizer and
transcribe the synthetic speech fixture; supported Apple Silicon runners also
exercise MLX. This explicit test downloads public pinned model files, never campus
recordings. Ordinary test runs skip it unless `TUM_MCP_LECTURE_ASR_INTEGRATION=1`.
Linux and Windows jobs also install the hash-locked CUDA runtime and load its pinned
cuBLAS the way CTranslate2 does, without a GPU (`TUM_MCP_LECTURE_CUDA_LIBRARIES=1`);
GPU inference itself runs in the native test only on a host with an NVIDIA GPU.
These native checks run inside the parallel source suite. Windows source and
installed jobs have 25-minute budgets; macOS and Linux have 20 minutes.

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
| `src/tum_mcp/commands/` | CLI command groups and shared terminal presentation |
| `src/tum_mcp/actions/` | Exercise action preflights, approval records, test evidence and the dormant executor |
| `src/tum_mcp/clients/` | Host-specific configuration and managed skill installation |
| `src/tum_mcp/skills/` | Skill registry, loading and validation |
| `src/tum_mcp/course/project/` | Course state, paths, init, sync, status, the agent guide and the recorded schedule |
| `src/tum_mcp/course/sources/` | Page text, search, imports, duplicates and source digests |
| `src/tum_mcp/course/content/` | Per-workspace content models (study blocks, exercises, exam, responses) and the one per-item file loader (`store.py`) |
| `src/tum_mcp/course/ledger/` | Coverage ledger and private, dated or selected preparation scopes |
| `src/tum_mcp/course/checks/` | Report flags, structure map, answer keys (`answers.py`) and structured plans (`plans.py`) |
| `src/tum_mcp/course/review/` | Review loop: check registry, items and fingerprints, ledger v2, packets, checker runner, scorecard and the `review` CLI |
| `src/tum_mcp/course/app/` | Build, preview, visual and interaction checks, comments and publication |
| `src/tum_mcp/course/memory/`, `media/`, `lecture/` | Course memory, audio and video notes, and the Lecture workspace |
| `src/tum_mcp/course/cli.py`, `output.py` | The `study` command group and its compact output |
| `src/tum_mcp/bundled/course_app/site/` | Managed course app with feature modules under `runtime/` and vendor files and fonts under `assets/` |
| `src/tum_mcp/bundled/review/checks.json`, `bundled/exemplars/` | The check registry and the gate-passing exemplar with its plan and answer key |
| `src/tum_mcp/bundled/skills/` | Canonical versioned source of reading, study, audio and video skills and their references/assets |
| `bundled/video_runtime/` | The isolated Video Notes render worker |
| `npm/` | Private-runtime installation, updates, integrity and cleanup |
| `tests/` | Synthetic backend, package and owned-browser checks |

Where to change what:

| Change | Touches |
| --- | --- |
| A new block type | Its model in `course/content/study.py` (and the `Block` union), its renderer in `course_app/site/`, the check registry when a check reads it, the exemplar or demo that shows it, the prepare-study content reference and tests |
| A new review profile or check | `bundled/review/checks.json` (and `review/registry.py` for a profile), the checklist it prints and the review-course profile notes |
| A new report flag | `course/checks/report.py` (or the workspace's flag function), `INVARIANT_FLAGS` in `review/models.py` when it always means a defect, and the check whose `decided_by` names it |
| A new authored file under `.tum-mcp/` | Its model, a `study schema` kind and the skill step that writes it |

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

Author one file per item under `app/` (`app/study/`, `app/exercises/`, `app/exam/`, `app/lectures/`); `course/content/store.py` assembles and validates them. Formula blocks and inline math are LaTeX, validated by
compiling it locally into safe MathML; the app typesets the validated LaTeX with the
vendored KaTeX (`katex.min.js`, `trust` off, rendered through DOM APIs so the strict CSP
holds) and falls back to that MathML. Unit `path` labels group the outline
without changing learning-progress revisions. Shared modules render all units;
content changes do not require a framework or per-unit HTML.

Shared renderer assets live in `src/tum_mcp/bundled/course_app/site/`; they are the
source of truth for layout, styling and interaction, and
[the design contract](course-app-design.md) describes their components and states. Design tokens sit at the top of
`styles.css`, and the owned-browser fixtures in `tests/integration/` hold the UI
regressions. Vertical spacing follows four relationships, each one token: a control to
the panel it opens (`--space-inside`), content to its own control such as Guide,
Solution or Hint (`--space-related`, applied by one shared rule), sibling items
(`--space-between`) and sections (`--space-section`). A new component takes these
instead of its own margins; `test_course_app_spacing_browser.py` fails when one
relationship shows two values. The preparation skills describe content and point to the app instead
of restating its styling, so app changes need no skill edits unless an authored field
or its meaning changes. Remove a template file by moving it to
`RETIRED_TEMPLATE_FILES`: builds then delete unedited copies and publication removes
them from managed sites. Existing flat-layout apps migrate on their next build.
The builder moves only managed, unedited files. If an older runtime or entry point
was customized, it keeps the old app intact and names the files to port. Authored
workspaces, URLs and progress identities keep their existing paths.

For dated Study or Exercises preparation, the author records the source scope with
`tum-mcp study schema preparation` in `.tum-mcp/preparation/ID.json`. Check the
draft with `tum-mcp study report PROJECT --section readiness --preparation ID`.
Before authoring, `study report PROJECT --section coverage-plan --preparation ID`
validates source requirements without reading a draft. New plans name their
`preparation`; the plan packet supplies its coverage and approval records its
fingerprint. A changed source scope reopens that plan check.
The gate requires current build and browser evidence for the mapped items, including
the phone and narrow checks from `study visuals --phone` and `--interact --phone`.
Use `review start PROJECT --preparation ID` to review that scope. A new loop defaults
to one round. Existing review scopes and explicitly requested budgets stay usable.

Mixed-workspace requests declare every expected output with `study schema batch` in
`.tum-mcp/batches/ID.json`. `study report PROJECT --section readiness --batch ID`
requires the complete current draft before `review start PROJECT --batch ID` and adds
course structure to mixed reviews. Recording selections use `study schema lecture-selection`;
their decisions cover every eligible interval and their review includes the full compact
transcript. Content-only authoring asks before formal review; an explicit review request
supplies that approval. More rounds require another request.

Study plans may include solved `practice` contrasts: the question key, how its decision
differs from the worked case, and its result with reasoning. The existing plan checker
checks these before authoring; lint checks their question links. Artifact-only changes
elsewhere in a batch retain source-plan approvals. Changed requests and source demands
still invalidate them.

After a batch round starts, `review repair-scope PROJECT --reason REASON` can adopt
complete split-out items after all original packets are recorded. Retain the original
keys, update plans, mappings and links, and pass readiness first. The command preserves
the original source/request contract and the round budget. New items receive no copied
verdicts; the scorecard exposes their remaining review. It cannot drop reviewed items,
change the original request or remove original past-paper questions. Completion requires
the current batch to match the repaired review scope.
Original source keys are captured at review start so adding a corroborating reference
does not look like changing an original source. Original source removal/revision and
required-demand changes still refuse adoption. Structural repair may finish after a
round closes; its scorecard is regenerated with the new items unreviewed and no extra round.

The shipped component preview demonstrates the three
heading levels, untitled continuations and guides placed beneath their own exercise
parts using validated `part_blocks` anchors. Include the optional Lecture
workspace with `tum-mcp study demo PROJECT --lectures` after selecting the Lecture
extension. The preview remains deliberately minimal;
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

Media source contracts live in `video_content.py`, `video_sources.py` and
`audio_content.py`. Study and Exercise video are explicit variants, not fake units.
`video-notes exercise PROJECT SET/KEY` prints exact permitted source locators.
The worker shares narration timing and rendering; `self.cue(index)` uses measured
sentence bounds. `video_style.py` stages effective app CSS colors; no worker palette
is maintained separately. Contact sheets sample entry/middle/exit frames.

`course/media/inventory.py` discovers optional manifests/plans read-only and verifies actual
artifact hashes; `course/review/media.py` checks score/evidence contracts. Media
averages are separate. Course structure includes source/chapter/coverage links,
not codec bytes. Pruned render caches do not erase published source identities.
Malformed optional media leaves ordinary Study diagnostics available.

Focused checks are `tests/unit/test_study_media.py`,
`tests/integration/test_study_review.py`, `test_video_pipeline.py` and
`test_study_video_browser.py`; the latter uses
`TUM_MCP_BROWSER_INTEGRATION=1`. Native render checks retain
`TUM_MCP_VIDEO_RENDER_INTEGRATION=1`. Recreate the AAC codec fixture with
`bash tests/fixtures/video/generate-audio.sh`. Calibration speech/video recipes
ship beside `review-course/references/media-gallery/`; their binary assets must
survive skill export and both distribution formats. Synthetic observer fixtures
test contracts only. A real teaching-quality review needs complete listening and
playback; unavailable perception remains an incomplete gate.

## Optional Lecture extension

Base setup exposes six workflows and no `tum_live_*` tools. `install lecture`
records explicit selection, refreshes managed clients and provisions the optional
recognizer only when requested/supported. `--no-asr` keeps captions/imported WebVTT.
Heavy recognition dependencies and model weights stay outside the base environment
and package artifacts. `lecture_processing/` owns bounded media/ASR evidence;
`lecture_content.py`, `lecture_data.py`, `lecture_assets.py` and `lecture_thumbnails.py`
validate notes, highlights and recording images used by the static app; `lecture_check.py`
checks note speech evidence and highlight boundaries against the cached transcript.
See [the workflow guide](lecture-notes.md).

Use `skills validate --all` to check the packaged optional workflow without installing
it; default validation checks the selected workflows. Activation statistics remain
unmeasured until genuine fresh-session trial records exist. Default tests use
synthetic media and course data. `test:upgrade` exercises optional lecture, audio and
video install/update/export/removal from an actual local npm artifact on every platform;
`test:consumer` covers the course-memory extension on a fresh installation and logs the
duration of each phase. Never publish or
stage npm as a test.

## Explore maintenance boundary

`ExploreMaterial` uses existing safe blocks and its own versioned sources. Empty
`Unit.explore` is omitted for legacy serialization; `unit_revision` excludes it to
preserve core progress. Full teaching/render reviews include it. The private ledger
records source-backed enrichment classification and separate pending work; classification
changes invalidate course-review structure identity. Default global definitions,
prerequisite maps, Revision and audio/video inputs stay core-only.

`explore.mjs` is a packaged template asset. Routes, tab sets, reading outlines and
comments must be checked with and without optional items. Explore anchors use comment
schema v4 without rewriting legacy files on read. Keep export source/asset closure
complete while removing private paths and classification reasons. Extend the existing
installed browser journey, rather than adding a platform matrix. Focused regressions
live in `test_study_explore.py` and `test_study_explore_browser.py`; run them plus affected
study/course-app/exercise tests and installation/migration checks for integration.

## Knowledge harness verification

Course Memory is an opt-in selection in the shared extension registry. Disabled
graph requests fail before loading course metadata; native structure/review reports
ignore retained graph files. The course review stores its optional semantic binding
separately from the native revision so disabling memory leaves native review intact.
Graph fixtures opt in explicitly; base/default-off tests must remain unselected.
`test_course_memory_extension.py` exercises setup, source sync, client update,
conflict-safe removal, reinstall and stale evidence. The installed consumer runs
the extension lifecycle through the packaged launcher. No model trials are needed.

Knowledge projection is request-local: `course/memory/store.py` captures metadata and
selected source observations; evidence checks reuse lecture receipts/figures through
optional observers; projection preserves native schemas; assertions compute independent
review fingerprints; query and packet modules enforce deterministic traversal and UTF-8
output limits. Resource maps and candidate views are reused only within a request;
selection retains current homes across workspaces without validating every discarded
view. The graph walk still checks reviewed paths and cycle/support dependencies.
Revision-only checks preserve the full reviewed semantic hash and snapshot validation;
explicit knowledge reports also diagnose inactive assertions. No persistent cache or
new runtime dependency is introduced.

The learning record (`course/learner/`) reads item ids through the ungated
`memory.store.read_inputs`, so it works with Course Memory off. Its decisions are
deterministic and covered by `tests/integration/test_learner_record.py`: consent from
setup only, refusal while off, dedupe, forget, the revisit schedule, brief selection and
byte cap, owner-only files and the `study init --learner` requirement. Agent behaviour
(asking nothing, recording in the same turn, staying out of unrelated chats, correcting a
recorded mistake) is not part of the automated suite.

Use `uv run pytest -q tests/unit/test_study_knowledge*
 tests/integration/test_study_knowledge*` (on one shell line) for focused behavior, plus
existing structure/review, lecture freshness, migration and export tests when those
boundaries change. Installed consumer checks exercise schema/context/impact through the
packaged launcher; retain all native installation, upgrade and lifecycle gates.

`test_course_memory_fidelity.py` holds one instance of every authored link family and
checks that each reaches its other end, that exact selectors list authored links before
weaker items, that locators name only the sources an entry cites, and that every key
reference in the four content schemas is either a tested link family or classified as
internal. A new reference field fails that test until it is projected or classified.

Retrieval evaluation uses fixed synthetic typed-reference gold sets, separate authored
lexical/native-map and raw-page finder baselines, the same packet budgets, and explicit
cold extraction versus warm lookup timing. Projection and source verification are timed
separately on 300 synthetic units without a wall-clock CI threshold. CI checks every
case's safety, status and graph completeness and that the control cases' baselines still
find their answers, using one prepared project copied per case. The bridge comparison,
timings, 300-unit profile and `.omo/evidence/study-knowledge-harness/` files run only
with `TUM_MCP_KNOWLEDGE_EVALUATION=1 uv run pytest -q
tests/integration/test_study_knowledge_evaluation.py`. Agent effectiveness
needs paired model trials with exact model/revision/corpus
identity, unsuccessful runs retained and quality, tokens, setup and update latency
reported separately. Retrieval tests alone do not establish student learning gains.

Local Course Memory optimization profiling uses only synthetic inputs:

```sh
TUM_MCP_MEMORY_PROFILE=1 TUM_MCP_MEMORY_PROFILE_OUTPUT="$PWD/.omo/evidence/course-memory-optimization/profile.json" uv run pytest -q tests/integration/test_study_knowledge_efficiency.py -k profile
```

The fixed helper records input/harness identities, candidate views, actual fingerprint
work, stage timings, fresh-process CLI timings and Python memory separately. Normal CI
checks deterministic work and correctness without a timing threshold. Use the same
helper, inputs and output obligations for before/after comparisons. Fresh Python
processes do not imply cold operating-system caches. These measurements and instruction
changes do not establish an agent-response speedup or a learning benefit; no new model
benchmarks are required by this optimization.
