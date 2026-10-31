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
tum-mcp setup
tum-mcp login
tum-mcp doctor
```

Then create a folder for one course, open an agent chat in it and run `$sync-course`
(Codex) or `/sync-course` (Claude Code). You are all set: the agent collects the
course's materials and you get your own learning harness for that course.

Recommended models to start with: GPT-6.1 Terra at xhigh reasoning in Codex, or
Claude Opus 5.5 at medium effort in Claude Code.

## Read and study

Ask your agent to explain course material, find announcements or catch up on a
Zulip channel. Campus access is read-only and follows your account permissions;
submissions, posting and exercise execution are unavailable.

| Workflow | Example request |
| --- | --- |
| `read-content` | “Explain this week's lecture with source citations.” |
| `sync-course` | “Set up a project for this course and collect its materials.” |
| `prepare-study` | “Build lessons, flashcards and practice in a study website.” |
| `prepare-exercises` | “Add guided exercises from this week's released sheet.” |
| `prepare-exams` | “Make a cheatsheet and practice exams from the past papers.” |
| `review-course` | “Score my lessons and exercises and fix what is hard to learn from.” |
| `publish-course` | “Publish my reviewed study site for phone access.” |

Each project holds one course. Run `tum-mcp study` in its folder to open the app.
Ask the agent to refresh it when sources change or address comments left in the
app. For your own resources, such as past exams from other websites, create a
temporary folder, put them all there and ask the agent to sort them into the course.
[Study guide and demo](docs/study.md).

TUMonline provides study names/degrees, public course catalog metadata and partial
course curriculum positions by default. Your grades and progress, exams and
semester fee status are available once you allow them with `tum-mcp manage tumonline`.
The catalog does not show enrollments, and full curricula are unavailable.
[TUMonline permissions](docs/tum-mcp.md#tumonline-permissions).

## Optional extensions

Run `tum-mcp install` to choose extensions, then reload your client.

| Extension | Skill added | What it offers |
| --- | --- | --- |
| `lecture` | `prepare-lecture` | Concise notes for useful remarks and highlights for worked explanations worth watching, each with a time range and frame. Prefers transcripts and slides; local recognition is optional. |
| `audio-notes` | `audio-notes` | Turn prepared Study into hands-free revision tracks, with checked reasoning, chapter re-entry and coverage. Voice setup happens when used. |
| `video-notes` | `video-notes` | Explain prepared Study concepts in depth or solve selected Exercises with intuitive visual walkthroughs in the local app. Check timing, captions and layout; install the render runtime when first used. |

Use `tum-mcp doctor` to see installed workflows and `tum-mcp uninstall` to remove
them.

[Lecture and recognition](docs/lecture-notes.md) ·
[Video Notes](docs/study.md#create-and-maintain-video-notes) · [Setup details](docs/setup.md)

## Course project

After initialization, a course project looks something like this:

```text
course/
  AGENTS.md                 Course instructions and inventory
  materials/                Course content, exams, exercises and other sources
  app/                      Study, Exercises, Exam and optional Lecture website
    content.json            Study lessons, flashcards and practice
    exercises.json          Guided exercise content
    exam.json               Exam: cheatsheet, exam patterns, practice exams (local only)
    lectures.json           Optional: Lecture
    lecture-assets/         Optional: highlight thumbnails and meaningful note images
  .tum-mcp/                 Private course state, comments and lecture evidence
  audio/                    Optional: scripts, tracks and chapters for Audio Notes
  videos/                   Optional: storyboards, scenes and explainer videos for Video Notes
```

## Privacy, updates and removal

Sessions are encrypted locally. Your agent uses your configured AI provider to
process selected material. Publishing requires local GitHub CLI authentication
and an eligible GitHub plan: **the repository is private; the website is public**.
Review content before publishing. [Publishing details](docs/study.md#publish-a-study-website).

```sh
tum-mcp update    # Upgrade the package and refresh managed clients
tum-mcp uninstall
```

Sessions, downloads, course projects and edited skills are preserved. Reload the
client after updates. [Update and removal options](docs/setup.md#update-and-remove).

[Command guide](docs/tum-mcp.md) · [Development](docs/development.md) ·
[MIT](LICENSE) · [NOTICE](NOTICE) · [Report a problem](https://github.com/jamestesting0/tum-mcp/issues)
