# Development

[README](../README.md) · [Setup](setup.md)

For the combined 0.4.0 campus pilot, see the [TUM MCP guide](tum-mcp.md) and
[current verification limits](tum-mcp.md#build-and-test-the-local-package). This page also
covers the preserved Moodle-only installer.

## Checks

```sh
uv sync --locked
uv run ruff check src tests plugin/scripts scripts
uv run ruff format --check src tests plugin/scripts scripts
uv run pytest -q
uv run python scripts/package_plugin.py
uv build
node npm/build.mjs
npm test
npm pack --ignore-scripts --pack-destination dist
npm run test:consumer -- dist/jamestesting888-tum-mcp-0.4.0.tgz
```

Python 3.13 is the managed runtime on every platform. Install Tesseract for the
OCR integration test. Ordinary tests use synthetic materials and in-memory
credentials; no Moodle login is needed. No language-server installation is required.

GitHub Actions runs the suite on macOS, Windows, and Ubuntu, including packaged
MCP startup, PDF/OCR extraction, downloads, and real native credential-store
round trips. The Linux job starts its own D-Bus/Secret Service session.
The campus additions configure fresh npm consumer checks on all three runners;
those checks must pass for the release commit before claiming release coverage.

To test an installed package, set `TUM_MOODLE_PACKAGED` to its
`scripts/launch.py` path before running pytest. Set `TUM_MOODLE_SYSTEM_KEYRING=1`
to enable the native-store test; it creates and removes a unique synthetic entry.

Live Moodle checks are separate: `TUM_MOODLE_LIVE=1 uv run pytest tests/live -q`.
They require the developer's saved session and Real Time Systems enrollment;
one test downloads a lecture. Never supply personal credentials to public CI.

## Architecture

| Module | Responsibility |
| --- | --- |
| `platforms.py` | Shared OS data/runtime paths; also imported by bootstrap and launcher |
| `auth.py`, `login.py` | Encrypted sessions, native credential stores, Chrome sign-in |
| `server.py`, `service.py` | MCP tools and retrieval coordination |
| `http_client.py` | Read-only Moodle network boundary |
| `parsing.py`, `forums.py`, `personal_records.py` | Moodle content and explicit private-record reads |
| `extraction.py`, `extract_worker.py` | Document/OCR extraction with process limits |
| `library.py`, `downloads.py` | Local search/cache and persistent exports |

The stdlib-only `scripts/install.py` owns packaging, runtime checks, activation,
and structured handoff. The updater pulls safely, then delegates to that installer.
Packaged `scripts/runtime_setup.py` is shared with bootstrap; its content receipt
and offline dependency check permit healthy reruns without synchronization.
Source changes force a package refresh even if the version/metadata timestamp
is unchanged. `--repair` reinstalls the locked runtime. The MCP smoke check lists
tools without reading a Moodle session or making Moodle requests.

Generated manifests launch the absolute private Python path on every OS.
Portable source templates contain no machine paths. Rebuild on each target
computer; moving/deleting the checkout does not affect the installed runtime.

CI enables `TUM_MOODLE_INSTALLER_INTEGRATION=1` for a real isolated-cache install,
offline rerun, same-version source update, damaged-runtime detection, and repair.
Set `TUM_MOODLE_INSTALLER_EVIDENCE` to write stage timings. The external Codex CLI
is synthetic in those tests; dependency installation and MCP startup are real.
Timings exclude agent latency, user sign-in/MFA, and application restart time.

Credentials use explicit OS backends. Unsupported or unavailable stores fail
with `SETUP_REQUIRED`; environment-selected plaintext alternatives are ignored.
Keep the existing macOS service name and account path to preserve saved sessions.

Extraction runs in a subprocess with a 60-second wall limit and 512 MiB aggregate
memory monitoring. POSIX also enforces a CPU limit and kills the process group;
Windows terminates the worker and its observed child processes.

## Manual desktop verification

Automated tests do not replace a desktop check. On each target OS, verify:

1. Register/install from a checkout with spaces in its path; restart the client.
2. Confirm native tools appear, then complete Chrome sign-in and MFA.
3. List current-semester courses, read a PDF, and check a forum.
4. Download one material and open the returned file locally.
5. Restart the client and confirm session reuse, then test logout and sign-in.

macOS has had a live course/sign-in test. Windows and Linux still require this
interactive check before claiming equivalent desktop verification.

Keep changes focused. Never commit session files, course materials, databases,
or `.env` files. The cache/search database is local and unencrypted; private
records are excluded from ordinary search. External recording links receive
no Moodle cookies.
