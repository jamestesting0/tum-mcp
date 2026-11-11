---
name: TUM MCP walkthrough
description: A scroll-driven walkthrough from installation to a live study app, inside the visitor's own coding agent.
colors:
  canvas: "#ffffff"
  surface: "#f7f9fb"
  aside: "#f2f5f8"
  ink: "#072140"
  muted: "#526477"
  line: "#d8e1e9"
  accent: "#3070b3"
  wash: "#eaf2fa"
  mark-front: "#072140"
  mark-back: "#8db0d5"
  dark-canvas: "#101a28"
  dark-surface: "#152236"
  dark-aside: "#0b1420"
  dark-ink: "#e9eef5"
  dark-muted: "#aabbd0"
  dark-line: "#344253"
  dark-accent: "#8cbffa"
  dark-wash: "#203b55"
  dark-mark-back: "#54759c"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible Next, Avenir Next, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(34px, 4.6vw, 58px)"
    fontWeight: 650
    lineHeight: 1.06
    letterSpacing: "-0.028em"
  section:
    fontFamily: "Atkinson Hyperlegible Next, Avenir Next, Segoe UI, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 650
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Atkinson Hyperlegible Next, Avenir Next, Segoe UI, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  ui:
    fontFamily: "Atkinson Hyperlegible Next, Avenir Next, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 500
  small:
    fontFamily: "Atkinson Hyperlegible Next, Avenir Next, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
  code:
    fontFamily: "Menlo, Consolas, Cascadia Mono, Liberation Mono, DejaVu Sans Mono, monospace"
    fontSize: "14px"
    lineHeight: 1.5
rounded:
  r1: "6px"
  r2: "12px"
  pill: "999px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "20px"
  s6: "24px"
  s8: "32px"
  s12: "48px"
  s16: "64px"
components:
  host-tab:
    textColor: "{colors.muted}"
    rounded: "9px"
    height: "40px"
    padding: "0 14px"
  host-tab-selected:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
  command:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.code}"
    rounded: "{rounded.r2}"
    padding: "10px 10px 10px 16px"
  resume:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.pill}"
    height: "40px"
  icon-button:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.r1}"
    size: "40px"
---

# DESIGN

## Overview

The page is quiet so that the stage can carry it. A sticky stage shows the visitor's coding agent (VS Code with Codex, Claude Code in a terminal, Cursor or Antigravity) working through six chapters while the page scrolls. At the end, the real study app runs live in a browser window on top. Around the stage there is only the hero (a centred headline whose last words name the agent picked in the switcher, one subline, the install command with Copy and Start the tour, which glides to the stage and plays), one caption line, the playback bar and the commands. The page uses the study app's palette and type, so the walkthrough and the product feel like one thing.

## Colors

Colours come from `src/styles/tokens.css`. `npm run check` fails when a value shared with the study app drifts from it.

### Primary

- **Accent** (`#3070b3`, dark `#8cbffa`): links, focus rings, chapter progress fill. It is never a large fill.

### Neutral

- **Canvas, surface, aside**: page, raised controls (tabs, commands), sidebars.
- **Ink, muted**: text and secondary text. Muted carries captions and inactive controls.
- **Line**: hairlines and inset borders.
- **Wash**: hover fill on quiet buttons.

### Named Rules

- **Agent chrome keeps its own colours.** Editor and terminal colours come from `references/editor-themes.json` (taken from the installed editors; Antigravity's from its official imagery). Page tokens never tint an agent's window.
- **Logo colours are tokens.** The lifted-card mark uses `--mark-front` and `--mark-back`, so it follows the theme.

## Typography

Atkinson Hyperlegible Next for everything the page itself says; the system UI font only inside rebuilt window chrome (title bars, address bar), where the real apps use it; monospace for commands.

### Hierarchy

- **Display**: the single h1, balanced, at most 15ch.
- **Section**: "Get started".
- **UI / small**: caption, tabs, chapter links, copy buttons.
- **Code**: the Get started commands.

## Layout

- The page is at most 1240px wide with 24px gutters. The header is sticky at 60px.
- The story is one tall track (`steps × 78vh + 100vh`) with a sticky stage below the header. Scroll position maps to a step and a progress `t` within it. Every step is a complete state, so any position renders directly.
- The stage is a 1280 × 800 desk scaled to fit. The agent window fills it. The browser window sits at 1060 × 704, offset like a real window over the editor.
- Phone (≤ 760px): the header is 56px, steps are 70svh, the stage shows the focused part of the agent at full width, the agent switcher becomes a 2 × 2 grid, and the playback bar shows only the current chapter's name. Commands wrap.

## Elevation & Depth

Only two things float: the agent window (`--shadow-stage` plus a 1px hairline) and the study app's browser window (a deeper shadow that lifts it above the agent). Everything else is flat, with inset 1px borders.

## Shapes

6px for small controls, 12px for windows and command rows, 9px for host tabs inside their 12px track, pill for Resume. The traffic lights and window radii follow macOS.

## Components

### Navigation

- **Header**: GitHub, npm and the theme toggle sit in one outlined pill (hover fills, a turning sun/moon); Get started is the solid button beside it. Phones keep the toggle and Get started.
- **Pages**: the story and Get started are two pages in one file. A view transition carries the clicked Get started button into the page heading while the story blurs back. On Get started the same header button reads Back to tour; Back reverses the transition and restores the story position. The footer is one row with a Disclaimer link that opens a small panel (notes and credits).
- **Scrolling**: native, with no rubber-band bounce at the page edges; the page scrolls itself only while Play is on. Scroll chooses the scene and the scene plays by itself at a calm, fixed pace, speeding up to keep up when the visitor scrolls ahead within it, and replaying whenever it comes back on stage; while it plays and the visitor is not scrolling, the page scrolls forward with it through its own part of the step (never into the next scene, and not after the visitor scrolls back in it), so its end lines up with the next scene: commands type, pickers step through their real keystrokes, the agent's work rows arrive one by one. Scrolling ahead queues scenes (played a little faster); three or more steps ahead, or any step back, shows the scene finished behind a short fade. Guide beats follow the scroll but each finishes its motion and stays at least 0.9 s; small back-and-forth near a boundary keeps the current beat. Clicks that open a menu or change page play as one motion with the beat after them. Each step's scroll length follows its content, about 6 s per scroll unit (a viewport's 78%), with beats placed where their content plays.
- **Sign-in**: `tum-mcp login` steps through the recorded service checklist (Moodle ticked) and browser list, then a Chrome window opens over the editor with Chrome's "controlled by automated test software" bar (the CLI starts it through Playwright): TUM-Moodle (always light, as the site is), With TUM ID, then TUM Login (light or dark with the theme, as login.tum.de follows the system), a made-up `go42tum` typed in, LOGIN, a loading bar, and the window closes as the terminal prints Moodle connected. TUM Login MFA is optional (go.tum.de/mfa), so no MFA screen is shown.

- **Agent switcher**: a tablist. The selected tab is a raised canvas chip with the agent's mark; arrow keys move between tabs. The choice is remembered.
- **Playback bar**: a round Play/Pause button (Replay at the end) and one track of six chapter segments sized by play time, 4px rails that fill in accent; `aria-current` marks the active chapter. Names show under their segments while they fit, otherwise only the current one. Hover or scrub shows the scene name; click or release seeks to that scene; the track is a slider for the keyboard.
- **Play**: one clock moves the tour at its own pace and scrolls the page to match, waiting at every guide beat and scene end until the stage has shown it. The visitor's wheel, touch, scroll keys or scrollbar, handing over the app, leaving the page, the disclaimer or a hidden tab pause it; then scrolling works as before from that point. Only the button, K or Space plays. It never starts by itself (WCAG 2.2.2).

### Buttons

- **Theme**: a 40px icon button; it themes the page, every agent and the live app together.
- **Copy**: a quiet text button inside each command row; it confirms with "Copied".
- **Resume tour**: an ink pill shown only while the visitor uses the live app.

### Live app (signature component)

The study app runs in a same-origin `srcdoc` frame. It keeps answers for the visit only, so a stale value in the browser never changes what the tour shows. Until the visitor clicks, a transparent shield keeps focus and scrolling with the tour. A click hands the app over (and activates what was clicked), Space or Enter on the shield hands it over without a click, and Esc, Resume or a click outside hands it back, snapping the app to the tour's current view.

### Guide

While the app is on screen, scroll plays two or three beats per section. Each beat:

1. dims the app slightly around one control and rings it in accent, with a soft halo pulse;
2. moves the lens there: it shrinks to a small accent disc, travels, and widens into the highlight around the control while the rest dims;
3. shows an ink callout with a label, one line on what the control offers, and dots for the section's beats;
4. on click beats, briefly brightens the lens's fill without moving it; a page-changing click gathers it into a disc first, and when the click reveals something (a new page's title, a menu, a panel) the lens glides on to it. The dimming stays steady while the guide shows, and the lens follows its control every frame while the app scrolls or reflows.

Scrolling back rebuilds the view and replays earlier clicks instantly, so every scroll position shows the same state. On phones, a beat falls back to the narrow layout's version of its control (the menu button for the sidebar, the map's list). The guide hides while the visitor uses the app and returns on Resume. With reduced motion, beats appear in place.

## Do's and Don'ts

### Do:

- **Do** show the result in the real app rather than describing it.
- **Do** keep each caption to a title and one short line.
- **Do** rebuild agent UIs from captured references (`references/hosts.md`) and real CLI captures (`content/cli/`).
- **Do** keep reduced motion complete: each step renders in its final state.

### Don't:

- **Don't** add marketing copy, statistics, testimonials or invented model output.
- **Don't** repeat a label the page already shows.
- **Don't** use page accent colours inside agent windows.
- **Don't** show real course material or accounts; the course is synthetic.
