# TUM Moodle for Codex

Read, search, and download your TUM Moodle course materials from Codex on your Mac.
Sign in through Google Chrome with your own TUM account; subsequent requests use
that session locally. No Moodle API token or paid API key is required.

This is an unofficial, independent project. It is not affiliated with or endorsed
by the Technical University of Munich or OpenAI.

## Features

- Find enrolled courses for the current semester using explicit semester labels.
- Read lecture PDFs, Word documents, PowerPoint slides, text, course pages,
  folders, books, wikis, announcements, and forum discussions.
- Cite source links, PDF pages, slide numbers, and forum-post permalinks.
- Search a local full-text index, with explicit reporting of indexing coverage.
- Extract scanned material with optional local Tesseract OCR.
- Download original files to `~/Downloads/TUM Moodle/course-<id>/` and find them later.
- Read your own available grades, assignment feedback, submitted files, and
  message conversations when explicitly requested.
- Return recording and external-player links without downloading video or audio.

The plugin does not submit assignments, start quiz attempts, post to forums, send
messages, or change grades. Opening Moodle content can still affect normal view
logs, unread markers, and completion rules based on viewing.

## Requirements

- macOS with a current Codex desktop app that supports local plugins.
- A TUM account with access to [TUM Moodle](https://www.moodle.tum.de/).
- Google Chrome, used only for interactive TUM sign-in and MFA.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.
- `python3` for the small installation scripts. The runtime uses Python 3.13,
  which uv downloads automatically if needed.
- Optional: Tesseract for scanned PDFs and images. OCR currently uses English.

Homebrew users can install the prerequisites with:

```sh
brew install uv
brew install --cask google-chrome
```

For scanned material and the OCR test, also run `brew install tesseract`.
If `git` or `python3` is missing, install Apple's Command Line Tools with
`xcode-select --install`. [Homebrew](https://brew.sh/) itself is optional; uv and
Chrome also have their own installers.

Apple Silicon is tested locally. The installer also handles standard Intel
Homebrew paths; Intel hardware has not been tested locally.

## Agent setup

Paste this prompt into Codex on your Mac. Codex can perform the terminal setup;
you still complete TUM sign-in/MFA and any required app restart or plugin-UI step.

```text
Set up https://github.com/jamestesting0/tum-moodle-integration on this Mac
so I can use TUM Moodle directly in Codex.

Read the repository's README and setup scripts, then carry out the installation:

1. Reuse a matching local checkout if one exists, otherwise clone the repository
   into a new folder under my home directory. Preserve existing files and changes.
2. Check Git, python3, uv, Google Chrome, and Tesseract. Install missing prerequisites
   using an existing trusted package manager. If macOS requires a manual approval
   or a prerequisite cannot be installed automatically, give me the exact next step.
3. From the checkout, run:
   python3 scripts/package_plugin.py --register
   python3 "$HOME/.codex/plugins/local/tum-moodle/scripts/bootstrap.py"
   Preserve my other plugins and existing Moodle session.
4. Install/enable TUM Moodle from the personal local marketplace. If the Codex CLI
   is available, use `codex plugin add tum-moodle@personal-local`; otherwise guide
   me through the Plugins screen. If a restart is needed, tell me to quit with
   Cmd+Q, reopen Codex, and return to this chat. Resume when I reply.
5. Verify that the native Moodle tools are available in this chat, then call
   moodle_auth_status. If sign-in is needed, call moodle_login and let me complete
   TUM sign-in and MFA in Chrome. Never request or display passwords, cookies,
   session tokens, or MFA codes in chat.
6. Use the native tools to list my current-semester courses and read one page of
   an accessible lecture file. Do not bulk-download content or fetch private
   grades/messages for this setup check. Report any access or extraction limits.

Continue through the automatic steps without unnecessary confirmations. If tools
are missing, inspect the plugin loader errors before requesting another restart.
Only report setup complete after native tool calls work in Codex; a successful
terminal-only test is not enough. Summarize what was installed and any remaining
manual action.
```

## Install

### 1. Clone and prepare the plugin

Run in Terminal:

```sh
git clone https://github.com/jamestesting0/tum-moodle-integration.git
cd tum-moodle-integration
python3 scripts/package_plugin.py --register
python3 "$HOME/.codex/plugins/local/tum-moodle/scripts/bootstrap.py"
```

The first script builds `dist/tum-moodle/`, copies the plugin to
`~/.codex/plugins/local/tum-moodle/`, and adds it to your personal plugin
marketplace. Existing marketplace entries are preserved. The checkout may be
outside your home folder and may contain spaces.

The second script installs the locked dependencies into a separate runtime at
`~/Library/Application Support/TUMMoodle/runtime/`. It does not install packages
into your system Python. The plugin can run after the checkout is moved or deleted.

### 2. Enable it in Codex

1. Quit the desktop app completely with **Cmd+Q**, then reopen it.
2. Open **Plugins**, choose the **Personal local plugins** source, and install or
   enable **TUM Moodle**. If your personal marketplace has a custom name, use that source.
3. Let the setup skill finish if Codex offers it. Repeating setup is safe.
4. If the tools are not yet available, quit and reopen the app once more.

The exact Plugins navigation can vary by app version. This is a local desktop
plugin; installing it does not connect ChatGPT web. See the
[official local-plugin instructions](https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually).

### 3. Sign in

Ask Codex:

> Sign in to TUM Moodle, then list my current-semester courses.

Complete TUM sign-in and MFA in the Chrome window. Keep passwords, cookies, and
MFA codes out of the chat. The plugin reuses a valid saved session and asks you to
sign in again when it expires. Each person signs in to their own account;
authentication state is never distributed with this repository.

## Use it

Example prompts:

- “List the materials in my Real Time Systems course.”
- “Read Lecture 1 and cite the PDF page numbers.”
- “Index this course, then find mentions of scheduling.”
- “Show the latest discussions in its announcements forum.”
- “Download this lecture to my Mac and give me the local file.”
- “Show the Moodle files I have already downloaded.”
- “Sign out of Moodle and clear the local cache.”

Course names depend on your enrollment. Real Time Systems is an example, not a
required course. Ambiguous semester labels are reported separately.

Search uses the existing local index. Ask Codex to index or refresh a course first
when necessary. Indexing proceeds in batches of at most five items; Codex follows
the returned cursor until complete. An incomplete index is reported as partial.
Reading a folder, book, or wiki can reveal child materials for subsequent reads.

## Privacy, storage, and limits

| Location | Contents | Lifetime |
| --- | --- | --- |
| `~/Library/Application Support/TUMMoodle/` | Encrypted session, document cache, search database, runtime | Session until logout/expiry; cache up to 30 days and 1 GiB |
| macOS Keychain | Session-encryption key | Managed by macOS Keychain |
| `~/Downloads/TUM Moodle/` | Explicitly downloaded original files | Until you delete them |
| `~/.codex/plugins/local/tum-moodle/` | Installed plugin source | Until removed or replaced during update |

Only Moodle session cookies are retained, encrypted with a key in macOS Keychain.
The document cache and search database have owner-only permissions but are not
encrypted by this application. Relevant returned excerpts are processed by your
configured Codex model. There is no additional LLM, embedding service, or telemetry
endpoint in this plugin.

Files are limited to 50 MiB each. Extraction has time and memory limits. OCR,
equations, diagrams, and handwriting may require checking against the original.
DOCX and PPTX are supported; older Office formats and interactive activities may
only expose metadata or descriptions. Restricted content stays restricted.

Private records are fetched only on an explicit request and are excluded from
ordinary course search. Course requests are limited to HTTPS on the Moodle host;
external recording links do not receive your Moodle cookies.

Signing out removes the plugin's saved session, not sessions in other browsers.
Clearing the cache does not delete files you explicitly saved in Downloads.

## Update

From your checkout:

```sh
git pull --ff-only
python3 scripts/package_plugin.py --register
python3 "$HOME/.codex/plugins/local/tum-moodle/scripts/bootstrap.py"
```

Quit and reopen Codex so it picks up the updated package. If the installed copy
still looks old, install TUM Moodle again from your personal source in Plugins.
Updating preserves your local session and downloaded files.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| Personal plugin source is missing | Rerun the registration command, quit with Cmd+Q, and reopen Codex. Check that your app supports local plugin marketplaces. |
| Plugin skills appear but tools do not | Run bootstrap again, reinstall from the personal source if needed, and restart Codex. The manifest must use `python3`, not an absolute executable path. |
| `uv` is missing | Install uv. The setup script checks PATH, `~/.local/bin`, and both standard Homebrew locations. |
| Chrome cannot open | Install Google Chrome in the standard Applications location, then retry sign-in. |
| Keychain error | Unlock your macOS login keychain and retry; the plugin deliberately requires the macOS Keychain backend. |
| Session expired | Ask Codex to sign in to Moodle again. |
| Scan cannot be read | Install Tesseract and retry. Ordinary text PDFs do not require OCR. |
| Search finds little or nothing | Ask Codex to index or refresh the course and check the reported coverage. |

For a local diagnostic, run:

```sh
"$HOME/Library/Application Support/TUMMoodle/runtime/bin/tum-moodle" status
```

When reporting a problem in [GitHub Issues](https://github.com/jamestesting0/tum-moodle-integration/issues),
include your macOS/app versions, the command you ran, and the error message.
Remove credentials, cookies, personal records, and course content from reports.

## Uninstall

Ask Codex to sign out and clear the cache before removing the plugin in Plugins.
To remove it from the personal catalog as well, remove only the `tum-moodle` entry
from `~/.agents/plugins/marketplace.json`, preserving your other entries.

After the plugin is disabled, you can delete its source at
`~/.codex/plugins/local/tum-moodle/` and its runtime/data directory at
`~/Library/Application Support/TUMMoodle/`. Delete exported files in
`~/Downloads/TUM Moodle/` separately if you no longer want them. The Keychain entry
uses the service name `tum-moodle-integration` and can be removed in Keychain Access.

## Development

```sh
uv sync --locked
uv run ruff check src tests plugin/scripts scripts
uv run ruff format --check src tests plugin/scripts scripts
uv run pytest -q
uv run python scripts/package_plugin.py
uv build
```

Install Tesseract to run the OCR test. The ordinary suite uses synthetic fixtures
and requires no Moodle account. GitHub Actions runs these checks on macOS.
To test the separately installed runtime:

```sh
python3 dist/tum-moodle/scripts/bootstrap.py
TUM_MOODLE_PACKAGED="$PWD/dist/tum-moodle/scripts/launch.py" uv run pytest tests/integration/test_package.py -q
```

The optional live tests require your own saved session and enrollment in Real Time
Systems. They read that course; the installed-runtime test also downloads a lecture.
Run them deliberately, never with credentials supplied to public CI:

```sh
TUM_MOODLE_LIVE=1 uv run pytest tests/live -q
```

Architecture: `server.py` defines the tools; `service.py` coordinates retrieval;
`http_client.py` owns the network boundary; `auth.py` owns sessions. Moodle parsers,
private records, document extraction, SQLite indexing, and downloads have separate
modules in `src/tum_moodle/`. Packaging scripts live in `scripts/` and `plugin/scripts/`.

Keep changes focused, add tests for behavior changes, and run the checks above.
Do not commit session files, course materials, local databases, or `.env` files.
No language-server installation is required.

## License

The code and original documentation are licensed under the [MIT License](LICENSE).
The TUM logo is excluded and retains its original rights; see [NOTICE](NOTICE)
and the [logo source](plugin/assets/README.md). This project grants no trademark rights.
