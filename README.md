# TUM MCP

Connect your coding agent to Moodle, Artemis and Zulip. Read course content and
build a private, source-backed study workspace. Unofficial; independent of TUM.

**Latest release: [0.6.0](https://www.npmjs.com/package/@jamestesting888/tum-mcp).**
[Release notes](CHANGELOG.md).

## Agent setup

Paste this into your coding agent to install the published package:

```text
Install @jamestesting888/tum-mcp on this computer. Check Node.js is 22.14+.
Run npm install --global @jamestesting888/tum-mcp@latest, then:
  tum-mcp setup --client codex
Use --client claude, cursor, antigravity, or generic for a different client.
Preserve existing settings and customized skills. Follow the activation steps.
Help me run tum-mcp connect in an interactive terminal and choose services.
I will complete sign-in/MFA in the browser. Never request secrets in chat.
Run tum-mcp doctor to explain what is available and what still needs setup.
```

## Connect

You need **Node.js 22.14+**, **a Chromium browser**, and your TUM account.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup --client codex
tum-mcp connect
tum-mcp doctor
```

Select services with **Space**, then **Enter**. Choose an installed browser and
complete sign-in there. Only selected tabs open; Zulip needs no API key.
Enable the [course and channel scopes](docs/tum-mcp.md#connections-and-scopes) you want to use.

| Client | Setup |
| --- | --- |
| Codex | `--client codex` · plugin and skills; enable/restart when prompted |
| Claude Code | `--client claude` · MCP registration and skills |
| Cursor | `--client cursor` · MCP registration and all five skills; restart |
| Google Antigravity | `--client antigravity` · MCP registration and all five skills; restart |
| Other MCP clients | `--client generic` · configuration for manual installation |

For existing Cursor and Antigravity setups, run `tum-mcp update` to add the skills.
Updates and uninstall preserve customized files and report them for review.

Supports macOS, Windows, glibc Linux x86_64/ARM64 and WSL 3.x. In WSL, sign-in
opens a Windows browser. Add `--host windows` to setup for a Windows client that
uses the WSL backend. [Browser and WSL setup](docs/setup.md#wsl).

Setup supplies a private Python runtime. New connections use encrypted local
files and need no native keyring, Git or Docker.

## Read and study

| Source | Available content |
| --- | --- |
| Moodle | Materials, pages, announcements, forums, original downloads and cited PDF pages |
| Artemis | Lectures, text/online/video units, student slide PDFs, released exercise statements and permitted own feedback |
| Zulip | Selected course channels, discussion search and cited catch-up |

Campus access is read-only. Exercise start, deployment, execution, submission,
posting and read-state changes are unavailable.

### Skills and example requests

The package includes five skills. Once you've chosen a course from
your connections, try requests like these:

| Skill | Use it to | Example request |
| --- | --- | --- |
| `read-content` | Read and explain course sources with citations | "Can you explain what we covered in last week's lecture?" |
| `sync-study` | Create or refresh a course project | "Set up a study project for this course." |
| `prepare-study` | Build lessons, flashcards and practice | "Make me a study website with flashcards and practice questions." |
| `publish-study` | Put a prepared website on GitHub Pages | "Put my study site online so I can open it on my phone." |
| `audio-notes` | Save spoken lessons under `audio/` | "Turn this into audio notes I can listen to on the go." |

Useful follow-ups in an existing project:

- "Did I miss anything important on Zulip this week?"
- "There's new course material. Can you update my study site?"
- "I've left some comments on the site. Can you fix those parts?"
- "Can you update the audio notes too?"

Client setup installs managed copies of the
[skill sources](src/tum_mcp/bundled/skills/). Develop or review skills in this repository.

### Recommended study flow

1. **`sync-study`**: Set up a project for your course and collect its material.
   Use it again when new material is available.
2. **`prepare-study`**: Turn that material into a study website with explanations,
   flashcards and practice questions.
3. **`publish-study`** (optional): Put the website online so you can study on your
   phone. Check the [publishing requirements](#publish-for-phone-access-optional) first.
4. **`audio-notes`** (optional): Turn the prepared content into spoken lessons.
   Use them to revisit prepared topics while walking or commuting.

Each project holds one course. To open the website locally, run this from the
course project folder:

```sh
tum-mcp study
```

Your browser opens at `http://127.0.0.1:8765`. Press **Ctrl+C** in the terminal to stop.
See the [study guide and local demo](docs/study.md) for more examples.

### Publish for phone access (optional)

Publishing requires [GitHub CLI](https://cli.github.com/) on the computer where
your agent runs and an eligible paid GitHub plan. Sign in locally, then check it:

```sh
gh auth login --hostname github.com
tum-mcp doctor --live
```

`doctor` checks CLI availability; `--live` also verifies GitHub authentication.
A coding platform's GitHub connector does not sign in the local CLI. No token
needs to be pasted into the agent or stored by TUM MCP.

**The repository is private. The website is public.** Review the lesson text,
quotations and source links before asking your agent to publish.

Later builds update the same site. `tum-mcp study` also prints its hosted URL.
See [publishing details](docs/study.md#publish-a-study-website).

## Sign-in and session privacy

Sign-in and MFA happen in a temporary browser window. Only service-owned session
cookies are retained; identity-provider cookies are discarded when it closes.
Sessions stay on your computer in encrypted files with owner-restricted keys.
Configured local clients share those connections and selected scopes.

## Your study project

The agent keeps each course in its own folder. After preparing the website,
your project looks like this, with audio added when requested:

```text
my-course/
├── AGENTS.md                 Course overview and source index for your agent
├── materials/
│   ├── content/              Lectures, slides and reading
│   ├── exercises/            Exercise sheets and practice material
│   ├── exams/                Available exam and revision material
│   └── other/                Announcements and course information
├── study/
│   ├── content.json          Lessons, flashcards and practice questions
│   └── index.html            Your study website
├── audio/                    Optional audio notes
│   ├── scripts/              Narration text
│   └── tracks/               Audio lessons
└── .study/
    ├── state.json            Course identity and source versions
    └── comments.json         Passage comments, when added
```

Your agent uses your configured AI provider to work with course material.
Publishing uploads only the generated website; materials, audio and comments
stay local. Study progress is saved in your browser.

## Update

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp update
```

`update` prepares the invoked package's runtime and refreshes configured clients.
Sessions, scopes and downloads carry forward. User-edited entries and skills are
preserved and reported for review. Reload the client; refresh its cached plugin
if needed. Study sites are updated separately through the study workflows.

## Remove

```sh
tum-mcp uninstall --all
npm uninstall --global @jamestesting888/tum-mcp
```

Managed registrations and unchanged skills are removed. Settings, sessions,
downloads and study projects are preserved. After closing clients, add
`--purge-runtime` to remove generated runtimes or `--forget-credentials` to
remove saved local sessions and historical Git tokens. [Removal details](docs/setup.md#update-and-remove).

[Guide](docs/tum-mcp.md) · [Setup](docs/setup.md) · [Study workflows](docs/study.md) · [Development](docs/development.md)

[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
