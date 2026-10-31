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
It also shows unprepared Study topics and exercise sheets. Unknown coverage and
optional backlog are demonstrated in the private agent report.

## What students see

- **Course home:** the course introduction, a Start or Continue link, topics in course
  order with their progress, and a link to review missed items. Full rows are clickable.
  The coverage ledger adds “Not prepared yet” for known core learning-outcome gaps,
  separate from the student's progress. Unknown coverage and optional backlog stay
  in private agent reports. Hosted queues include only sources referenced by the
  published Study units.
- **Units:** Content, Flashcards and Practice. A Next link leads through the three
  views and on to the next unit; the last unit leads to Revision. A conditional
  **Explore** tab follows Practice only for units with authored supporting reading.
  It opens directly on the reading, returns to Content, and does not affect
  core minutes, progress, cards, questions or Start/Continue. See [Explore](explore.md).
- **Revision:** cards and questions pooled from chosen topics (all topics until the
  student chooses), optionally only the cards marked Again and questions missed at the
  first attempt. A retry after seeing the answer does not clear a miss; a later correct
  answer from a fresh start does. Pooled items keep their original progress.
- **Connections:** a unit's header links its Lecture, the exercises whose
  prerequisites name it and the Exam patterns whose entries cite it. Marked terms
  open their definition in place; an exercise prerequisite opens its Study block beside
  the exercise. In the local preview, a citation opens the stored course file at its page.
- **Exercises and Lecture:** separate workspaces in the same app when prepared.
  Lecture lists lectures newest first. The sources of each passage and figure
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
| block `title`, `level`, `sources` | A section, subsection or detail heading with a sources icon; an untitled block continues the current passage |
| flashcard `front`, `back` | One card that flips; its sources appear after reveal |
| question `prompt`, `blocks`, `options`, `explanation`, `hint` | Practice and Revision; the blocks sit between prompt and options, options appear in a stable shuffled order, the hint is one optional button before checking; after a check the app marks the chosen and correct options, shows the chosen option's feedback and the explanation, and keeps the other options' feedback on request |
| `definition` block | The term in bold above its full-width meaning, inside the section before it; consecutive terms form one list; `{{term}}` mentions open it in place |
| text `steps` | A numbered sequence after the paragraphs, one action per step; a step or point opening with a short `Label: ` shows the label in bold |
| `figure` block | The drawing or image at full width with its caption; the `alt` text names it for screen readers |

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
