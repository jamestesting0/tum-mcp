# TUM MCP walkthrough

A one-page walkthrough of TUM MCP. A student installs it, chooses a coding agent and
optional workflows, syncs a course, builds the study workspaces and uses the real study
app, which runs live inside the page. The build produces one self-contained file,
`dist/tum-mcp-walkthrough.html`.

This folder is development-only: npm, the wheel and the sdist do not include it.

## Commands

Run from `website/` with Node.js 22.14+ and the repository's `uv` environment.

| Command | What it does |
| --- | --- |
| `npm install` | Installs esbuild and the VS Code icon font. |
| `npm run build` | Writes `dist/tum-mcp-walkthrough.html`. |
| `npm run dev` | Serves the page at http://127.0.0.1:4310 and rebuilds it on every load. |
| `npm run check` | Checks the built page: size budget, no network requests, tokens shared with the study app, and that every story step names real chapters, terminal screens and course files. |
| `npm run course -- --build` | Re-syncs the synthetic course from `tools/course-sources.mjs` and rebuilds its app with `tum-mcp study build`. |
| `npm run capture-cli` | Records the real `tum-mcp setup` screens for each agent in a throwaway HOME (needs `.venv` from `uv sync`). |

## Layout

```text
website/
├─ PRODUCT.md           Product record for this surface
├─ DESIGN.md            Visual system of the built page
├─ src/
│  ├─ index.html        Page skeleton; the build fills its {{parts}}
│  ├─ styles/           tokens.css (shared with the study app), page, stage, phone, hosts/*
│  ├─ scripts/          main.js, stage.js, story/, hosts/, ui/, app/embed.js, content/cli.js
│  ├─ content/          story.json (all page copy and story steps), cli/ (terminal screens)
│  └─ assets/           brand/ (TUM MCP mark and icons), hosts/ (agent marks + ATTRIBUTION.md)
├─ course/              The synthetic "Graph Search" course project
├─ tools/               build, dev, check, course, capture-cli and lib/
└─ references/          hosts.md (what each agent rebuild is based on), editor-themes.json
```

## How it fits together

- **Story.** `src/content/story.json` holds chapters and steps. Each step names what the
  terminal, chat, explorer, editor and live app show. `story/timeline.js` turns the steps
  into one complete state per step, so any scroll position can be drawn directly.
- **Agents.** `hosts/workbench.js` draws VS Code with Codex, Cursor and Antigravity from one
  layout; `hosts/terminal-app.js` draws Claude Code in a terminal. Editor colours come from
  `references/editor-themes.json`, extracted from the installed editors; the build turns
  them into CSS.
- **Terminal screens.** `content/cli/setup-*.json` are recorded from the real CLI by
  `npm run capture-cli`. `content/cli.js` derives what a safe capture cannot reach (the
  installed workflows, the login screen and Claude Code's signed-in check, which the
  throwaway HOME reports as "Needs action"); `login.json` names its source.
- **Live app.** `tools/lib/app-document.mjs` packs the course's study app (installed by
  `tum-mcp study build`) into one document: ES modules bundled, fonts and images inlined,
  and the local preview's media and comment requests answered in the frame. The page
  embeds smaller copies of the audio and video; the course keeps its published files.
  `app/embed.js` hands the frame to the visitor on click or focus and back on Esc or
  Resume.
- **Guide.** A step's `guide` beats in `story.json` name a control in the app (`target.css`,
  optional `text` regex and `nth`; a list gives alternatives, such as the phone layout's), a
  label and one line, and whether the tour clicks it (`after` names what the click reveals).
  Workspace switches are beats too: a step's `appStart` is the page it opens on, `route` is
  where a click leads (the guide goes there itself if the click cannot happen), and `opens`
  marks a beat that opens a menu for the next one.
  `app/embed.js` plays them as the visitor scrolls; `app/guide.js` draws the lens (a disc
  that travels and widens into the spotlight) and the callout. `npm run check` validates the beats' order and fields.
- **Pacing.** The scroll chooses the scene; the CLI and agent parts of a scene play by
  themselves at the fixed pace in `story/play.js` (`PACE`), never behind where the scroll has
  reached within the scene since it came on stage (`main.js` eases toward it), and a scene
  replays whenever it comes back on stage. While a scene plays and the visitor is idle, `main.js`
  scrolls the page with it through its own part of the step (`contentEnd`: up to its first
  guide beat, else the step end), so no dead stretch is left before the next scene. Neighbouring steps swap at once; stepping back needs the scroll clearly
  inside the earlier step (`BACK_GRACE`), and the playback bar follows the scroll exactly. Terminal blocks are timed events: `command` (typed when `type`), `lines`,
  `frame` (a screen that replaces the one before), `sequence` (screens shown one after
  another, built in `content/cli.js` from the recordings, such as a picker's cursor moves),
  `browser` (milliseconds of the sign-in window, `hosts/signin.js`) and `exits` (the command
  returns to the prompt). `main.js` queues scenes when the visitor scrolls ahead and jumps
  straight to the target, behind a short soft dip, once more than 8 s of scenes are waiting;
  `app/embed.js` plays guide beats one at a time with a minimum dwell (brief after menu and
  page-change clicks) and fades for steps back or long jumps. Step `weight`s follow each scene's content at about
  6 s per unit and beat `at`s sit where their content plays; recompute both after changing
  a scene or `PACE`.
- **Recordings.** `npm run capture-cli` records `tum-mcp setup` for every app and the
  `tum-mcp login` pickers in throwaway homes (`--login` records only the login, which is
  cancelled at the browser list, so no browser opens and no account is used).
- **Player.** `player.js` owns Play/Pause, the clock and the playback bar; `main.js` gives it
  `limit(position)`, how far the clock may move before the stage has shown the next beat or
  finished the scene, using the guide driver's `embed.shown`.
- **Scrolling and pages.** Scrolling stays native and the page moves on its own only while Play is on. While Get started shows,
  the tour page stays laid out but invisible and inert, and the guide starts no new step
  (`embed.suspend()`/`resume()`), so coming back finds the tour exactly as it was left.
  Get started is a second page in the same file (`#get-started`), reached with a view
  transition; there the header's Get started button becomes Back to tour. `npm run dev`
  rebuilds in a fresh process on every page load.

## Course content

`course/` is a real TUM MCP course project made from synthetic sources. Its Study,
Exercises, Exam and Lecture content, Audio Notes track and Video Notes video were produced
with the bundled workflows and pass `tum-mcp study lint`. The formal plan gate and the
review loop were not run, because they need fresh reviewer agents. After changing a
source, run `npm run course -- --build`. After changing the CLI's setup screens, run
`npm run capture-cli`. Then rebuild.
