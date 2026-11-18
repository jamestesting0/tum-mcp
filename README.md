# TUM MCP

Connect your coding agent to **Moodle, Artemis, Zulip and TUMonline**. Read course
sources with citations and turn them into a private study app. Unofficial and
independent of TUM.

[**npm package**](https://www.npmjs.com/package/@jamestesting888/tum-mcp) ·
[Release notes](CHANGELOG.md) · [Setup guide](docs/setup.md)

## Get started

Requires **Node.js 22.14+**, a Chromium browser and your TUM account.

```sh
npm install --global @jamestesting888/tum-mcp@latest
tum-mcp setup     # Connect your coding clients and pick extensions
tum-mcp login     # Sign in with your TUM account
tum-mcp doctor    # Check that everything works
```

Then create a folder for one course, open an agent chat in it and run `$sync-course`
(Codex, Antigravity, Cursor) or `/sync-course` (Claude Code). You are all set: the
agent collects the course's materials and you get your own learning harness for that
course.

Recommended models:

| Model | Why |
| --- | --- |
| GPT Terra high | Balanced |
| GPT Luna max | Free |
| GPT Sol medium | Cost-effective intelligence |
| Opus medium | Best choice for Claude |
| Cursor Auto | Free |

## Read and study

Ask your agent to explain course material, find announcements or catch up on a
Zulip channel.

- Campus access is read-only and follows your account permissions. Submissions,
  posting and exercise execution are unavailable.
- Moodle and Artemis courses stay readable across semesters while your account has
  access. Requests use the current semester unless you name one, such as "prepare
  Algorithms for WS23" (winter 2023/24).

| Workflow | Example request |
| --- | --- |
| `read-content` | “Explain this week's lecture with source citations.” |
| `sync-course` | “Set up a project for this course and collect its materials.” |
| `prepare-study` | “Build lessons, flashcards and practice in a study website.” |
| `prepare-exercises` | “Add guided exercises from this week's released sheet.” |
| `prepare-exams` | “Make a cheatsheet and practice exams from the past papers.” |
| `review-course` | “Score my lessons and exercises and fix what is hard to learn from.” |
| `publish-course` | “Publish my reviewed study site for phone access.” |

### Your course app

- Each project holds one course. Run `tum-mcp study` in its folder to open the app.
- Ask the agent to refresh the app when sources change, or to address comments you
  left in it.
- To add your own resources, such as past exams from other websites, put them in a
  temporary folder and ask the agent to sort them into the course.
- Study, Exercises and Exam can each be prepared on their own. They link to each
  other once they exist.
- Study lessons go from the source's reasoning to worked steps, then to practice.
- Exercise guides follow the solution step by step. Compare shows the full working;
  Solution shows only the answer.

### Preparation and review

1. The agent checks coverage and completes the draft.
2. It then offers review: approve one round of checking and repair, or ask for more.
3. Browser checks flag formulas that clip, scroll on their own or get too small to read.

[Study guide and demo](docs/study.md)

### TUMonline

- By default: study names and degrees, the public course catalog and partial
  curriculum positions per course.
- After you allow them with `tum-mcp manage tumonline`: grades and progress, exams
  and semester fee status.
- Not available: enrollments and full curricula.

[TUMonline permissions](docs/tum-mcp.md#tumonline-permissions)

## Optional extensions

| Workflow | Example request |
| --- | --- |
| `prepare-lecture` | “Make notes for this week's recording and mark the parts worth rewatching.” |
| `audio-notes` | “Turn my Study lessons into audio tracks I can revise with hands-free.” |
| `video-notes` | “Make a visual walkthrough of this exercise's solution.” |

```sh
tum-mcp install    # Choose extensions, then reload your client
tum-mcp doctor     # See what is installed
tum-mcp uninstall  # Remove them
```

Voice and video tools are set up the first time you use them.

[Lecture and recognition](docs/lecture-notes.md) ·
[Video Notes](docs/study.md#create-and-maintain-video-notes) · [Setup details](docs/setup.md)

## Course project

After initialization, a course project looks something like this:

```text
course/
  .tum-mcp/                 Private course state, comments and lecture evidence
  app/                      Study, Exercises, Exam and optional Lecture website
    exam/                   Exam index, cheatsheet entries, patterns and mocks
    exercises/              Exercise-set index and individual guided problems
    lecture-assets/         Optional: highlight thumbnails and meaningful note images
    lectures/               Optional: Lecture index and individual lectures
    study/                  Course index and individual Study lessons
  audio/                    Optional: scripts, tracks and chapters for Audio Notes
  materials/                Course content, exams, exercises and other sources
  videos/                   Optional: storyboards, scenes and explainer videos for Video Notes
  AGENTS.md                 Course instructions and inventory
```

## Privacy, updates and removal

Sessions are encrypted locally. Your agent uses your configured AI provider to
process selected material. Publishing requires local GitHub CLI authentication
and an eligible GitHub plan: **the repository is private; the website is public**.
Say "publish the study app" and the agent handles setup, all prepared workspaces,
image export, updates and deployment verification. Local-document references are
removed; external lecture timestamp links remain. Review content before publishing.
[Publishing details](docs/study.md#publish-a-study-website).

```sh
tum-mcp update    # Upgrade the package and refresh managed clients
tum-mcp uninstall
```

Sessions, downloads, course projects and edited skills are preserved. Reload the
client after updates. [Update and removal options](docs/setup.md#update-and-remove).

[Command guide](docs/tum-mcp.md) · [Development](docs/development.md) ·
[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
