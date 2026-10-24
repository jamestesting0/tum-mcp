# TUM MCP terminal design system

## 0. Research log

The product surface is a terminal, not a web page. The design references were
reviewed for hierarchy, restrained color, keyboard-first selection, and precise
status language. Raycast, Linear, and Vercel were shortlisted; Raycast's command
palette structure and a minimalist text hierarchy fit a local developer utility.
The existing commands expose raw JSON and separate login prompts; those have no
reusable visual system to preserve. The user explicitly requested this contract.

Browser screen research, bitmap concepts, CSS layouts, React tooling, and
Lighthouse are not applicable to this terminal-only surface. No marketing hero,
SVG icon library, web font, or animation framework is introduced. Terminal QA
uses real pseudo-terminals and rendered console captures; web audit scores are
not claimed. Questionary supplies the keyboard checkbox mechanism; Rich supplies
layout and terminal-aware text. Both share the semantic tokens below.

## 1. Atmosphere and identity

A quiet local command center: clear status first, supporting evidence next,
then one actionable next step. The signature is aligned service rows with
explicit state labels and a compact keyboard legend. Diagnostics describe what
was checked. Configured, installed, reachable, and authenticated are distinct.

## 2. Color

Respect the user's terminal background and foreground. No fixed canvas or
full-width colored panels. ANSI semantic colors adapt to terminal themes:

| Token | Terminal style | Role |
| --- | --- | --- |
| title | bold | Command heading |
| primary | default | Main text and service names |
| muted | dim | Secondary labels, version, and footer |
| accent | cyan | Keyboard focus and commands |
| ready | green | A check that passed |
| attention | yellow | Missing optional capability or action needed |
| failed | red | A failed check |
| rule | dim | Neutral separators |

Color belongs to small status markers; state words and evidence use the default
foreground so a light terminal's ANSI yellow cannot obscure them. Color never
carries status alone. Each row has a word label. Honor NO_COLOR,
TERM=dumb, redirected output, and monochrome terminals. Escape external strings
as text rather than interpreting Rich or prompt-toolkit markup.

## 3. Typography

Use the user's monospace terminal font. Titles are bold, section labels plain
or bold, and explanations normal weight. Avoid all-caps paragraphs, emoji,
decorative logos, and box-drawing-dependent meaning. Commands remain copyable.
The dumb-terminal fallback uses a numbered list and a plain input prompt.

## 4. Spacing and layout

One character cell is the spacing unit. Use two-cell column gaps and one blank
line between sections. Cap the normal content width at 100 columns. At fewer
than 70 columns use stacked rows so descriptions and paths wrap beneath labels.
At 40, 80, and 120 columns, primary content must remain readable without clipping.
The terminal owns scrolling; diagnostics never switch to an alternate screen.
The selector may redraw its short list but must restore the cursor on exit.

## 5. Reusable primitives

### Command header

Command name, package version, and a short purpose line. No decorative border.

### Status row

Label, explicit state, and evidence. Variants: ready, configured/unverified,
missing optional prerequisite, blocked, failed. Long evidence wraps and uses the
default foreground for contrast. An unchecked
remote session is never displayed as connected.

### Service selector

Moodle, Artemis, Zulip, with short descriptions. Nothing selected initially.
Up/down move focus, Space toggles, Enter confirms, Ctrl+C cancels. Empty selection
shows an inline instruction and never opens a browser. Explicit --service options
provide a non-selector route. Open only the selected services.

### Progress and outcome

Show selected service names and waiting/connected/failed state. Save completed
logins independently. Browser-close, timeout, and cancellation produce sanitized
messages with a retry command, never tracebacks or credential values.

### Next action

One short explanation plus an exact command, deduplicated by action. Optional
Docker absence does not mark read-only Moodle, Artemis, or Zulip tools as broken.

## 6. Motion and interaction

Selection feedback is immediate; no animated entrances. An indeterminate wait
indicator may show only while work is active, with no invented percentage.
No animation in redirected, dumb, or no-color output. Cancellation closes the
temporary browser and restores terminal state. JSON mode emits only JSON.

## 7. Depth and surface

Text hierarchy and neutral spacing provide grouping. Avoid nested boxes,
colored edge stripes, accent outlines, decorative cards, gradients, and shadows.
This is a terminal adaptation; web surface and radius tokens are inapplicable.

## 8. Accessibility constraints and accepted debt

All interaction is keyboard reachable. Instructions stay visible, errors have
text labels, and success does not depend on color. Ctrl+C returns a conventional
cancel result. Plain text works in a pipe; --json supports automation. Paths and
long service errors wrap without terminal-control injection.

Known platform limits are reported as unverified rather than success. Desktop
client configuration and actual host activation remain separate checks. No claim
of a screen-reader audit or equivalent native onboarding is made without evidence.
The QA record belongs under docs/local/ so machine-specific evidence is not shipped.
