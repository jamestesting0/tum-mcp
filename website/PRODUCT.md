# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML, CSS and JavaScript with no framework, built by Node tools into one self-contained HTML file (`website/dist/tum-mcp-walkthrough.html`). esbuild bundles the page and the embedded study app. Confirmed by the user on 2026-11-10.

## Users

TUM students who already use, or are about to use, a coding agent: Codex, Claude Code, Cursor or Antigravity. They arrive from the README, from npm or from a shared link. They want to see, before installing, what TUM MCP does in their own agent and what they get at the end.

## Product Purpose

TUM MCP connects a student's coding agent to Moodle, Artemis, Zulip and TUMonline. It reads course sources with citations and turns them into a private study app with Study, Exercises and Exam workspaces, plus optional Lecture, Audio Notes, Video Notes and Course Memory. This walkthrough is a surface that shows the whole path from installation to a working study app. A visitor should finish knowing how to install it and what they will get.

## Positioning

The agent the student already uses becomes the course assistant, and the result is a real local study app built from the student's own course sources. Campus access is read-only and follows the student's own permissions. It is not a hosted service and has no API keys of its own.

## Operating Context

- Install with `npm install --global @jamestesting888/tum-mcp@latest`, then `tum-mcp setup` (pick coding apps, then optional workflows; nothing is preselected), `tum-mcp login` and `tum-mcp doctor`.
- In a course folder, the student runs `$sync-course` (Codex, Cursor, Antigravity) or `/sync-course` (Claude Code), then asks for study, exercise and exam preparation.
- `tum-mcp study` opens the local app. Optional extensions are installed during setup or with `tum-mcp install`.

## Capabilities and Constraints

- Requires Node.js 22.14+, a Chromium browser and a TUM account.
- Read-only campus access: no submissions, posting or exercise execution.
- Sessions are encrypted locally. The agent uses the student's configured AI provider.
- Unofficial and independent of TUM.
- The walkthrough shows a synthetic course. It must not show real course material, real accounts, or invented model names or results.

## Brand Commitments

- Name: TUM MCP (`tum-mcp` in the lockup).
- Logo: "A2 · Lifted card", a revision card lifted off a stack. It must not resemble TUM's block-letter logo.
- Look: inherits the study app's tokens and Atkinson Hyperlegible Next.
- Copy follows `UI-CLARITY-REQUIREMENTS.md`: minimal text, every string has a job.

## Evidence on Hand

- README, docs and CLI source in this repository. CLI text is captured from the real commands.
- The bundled study app (`src/tum_mcp/bundled/course_app/site`) and the synthetic course in `website/course/`.
- No testimonials, usage numbers or benchmarks exist; none may be invented.

## Product Principles

1. Show the result, not a description of it: the real app, live.
2. One path, one course, one story; every pane agrees.
3. Respect the student's tools: each agent looks like itself.
4. Quiet frame, precise details.

## Accessibility & Inclusion

Captions announced to screen readers, a skip link past the story, reduced-motion support, keyboard paths into and out of the live app, and contrast checked in both themes.
