# The course app

The package ships one shared course app. `tum-mcp study build` installs it into the
project's app folder and generates `data.mjs` from your authored files;
`tum-mcp study template` lists its files and revision. The app decides layout,
typography, colors, components, keyboard behavior and responsive design, so new
releases improve every course without content changes. Author content, not markup
or styles, and do not restate the app's appearance in teaching text.

To see every component with synthetic data, run `tum-mcp study demo PROJECT` in a
separate directory and open it with `tum-mcp study serve PROJECT`. The demo shows
formats; it is not a model of good teaching or question design.

## What students see

- **Course home:** the course introduction, a Start or Continue link, topics in course
  order with their progress, and a link to review missed items.
- **Units:** Content, Flashcards and Practice. A Next link leads through the three
  views and on to the next unit; the last unit leads to Revision.
- **Revision:** cards and questions pooled from chosen topics (all topics until the
  student chooses), optionally only the cards marked Again and questions answered
  incorrectly. Pooled items keep their original progress.
- **Exercises and Lecture Notes:** separate workspaces in the same app when prepared.
  Lecture Notes lists lectures newest first. The sources of each passage and figure
  link to the recording at the measured time; the text itself carries no timestamps.
- **Contents:** a button lists the current page's headings in every workspace; wide
  screens can keep the list beside the text. Clear, short block titles make it useful.
- **Progress** stays in the student's browser. Passage comments work in the local
  preview only, never on a published site.

## Where authored fields appear

| Field | Appears as |
| --- | --- |
| `introduction` | The opening text on the course home |
| unit `path` and `label` | Outline groups and the unit's eyebrow line |
| `title`, `minutes` | Outline, home topic list, unit header and Next link |
| `summary`, `objectives` | The Content view's header |
| block `title`, `sources` | A section heading with a sources icon |
| flashcard `front`, `back` | One card that flips; its sources appear after reveal |
| question `prompt`, `options`, `explanation` | Practice and Revision; after a check the app marks the chosen and correct options, shows the chosen option's feedback and the explanation, and keeps the other options' feedback on request |

Keep titles and labels short enough to scan in an outline. Long text wraps, but it
crowds navigation. Questions must stand alone because Revision pools them; see
[practice](practice.md).

## When a course needs more

Course authoring never edits the installed app. If a course genuinely needs a block
type or behavior the app lacks, report it instead of working around it. App changes
belong in the package's shared modules, with a validated schema field, safe rendering,
an accessible fallback and the package's browser tests, so every course gains them.
Build preserves and reports project files that differ from the installed app; review
whether such customized files support the content before extending it.
