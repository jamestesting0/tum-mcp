# Teaching through narrated animation

A video is a visual adaptation of one prepared Study unit. It earns its place when
motion shows something the page cannot: a state changing, a quantity moving, a
derivation step transforming, a trace advancing. The prepared unit stays the
reference; flashcards and practice stay in the app.

## Choose units

Recommend a video for units with a diagram that has frames, a plot, a formula
derivation, a code trace or a comparison of mechanisms. Mark definitional,
administrative or prose-only units `text-first` with a short reason; the user may
override. A selection file is `{"units": [{"unit": KEY, "decision": "video" |
"text-first", "reason": TEXT}]}`; `tum-mcp video-notes schema selection` has the
contract. Planning keeps existing video numbers and never renumbers.

## Rules

- **R1 Motivation first.** Open with the problem the unit solves, taken from its
  summary, within about 30 seconds. No invented hook.
- **R2 Concrete before abstract.** Show the course's own worked example, diagram
  frames, plot data or practice givens before the general rule. If the unit has no
  concrete instance, report the gap to prepare-study instead of inventing one.
- **R3 Pre-training.** Name prerequisite notation in a bridge beat before the
  mechanism, following the unit's bridge section.
- **R4 Temporal contiguity.** A visual change happens in the beat whose narration
  names it. The beat timing enforces this; keep each beat to one idea.
- **R5 Redundancy and modality.** Narration explains; the screen shows objects, short
  labels, the key formula and at most one short sentence. Never put the narration on
  screen. Still name every essential visual change aloud, so the transcript works
  without the picture.
- **R6 Signaling.** Highlight or indicate what is being named, never by color alone.
  The same symbol keeps the same color in every video of the course
  (`videos/style.json` `symbol_colors`).
- **R7 Coherence.** No decorative motion, music, sound effects or filler. Every
  animation shows a relationship or a state change.
- **R8 Segmenting.** Chapters of 30 to 120 seconds, one concept each. Aim for 3 to 8
  minutes per video; past 10 minutes suggest splitting the unit in prepare-study.
- **R9 Retrieval.** One or two `question` beats per video, each an existing practice
  question that fits what was shown. Show the givens, narrate the prompt, pause 3 to
  5 seconds (`pause_s`), then answer from the prepared explanation. Label a
  misconception as one. Never turn it into a different question.
- **R10 Rediscoverable steps.** Say why the next step helps and what makes it valid.
  Equation steps transform with matching parts; kept terms stay where they are.
- **R11 Fidelity.** Edge and inequality directions, order, units, signs, monotonicity
  and extrema match the source. Plot only source data or exact source formulas, and
  call interpolation illustrative. Numbers come from storyboard `number` items.
- **R12 Close.** Recap the central relationship in a few sentences and point to the
  unit's Practice. Never claim that watching proves mastery.

Default shape, adapted rather than imposed: hook, bridge, instance, mechanism,
generalize (the abstraction colour-linked to the instance), pitfall, question, recap.
These are the beat `kind` values.

## Storyboards

`tum-mcp video-notes unit PROJECT UNIT` prints every locator with its fingerprint and
the unit hash; copy them, never compute them. Each beat lists the locators it
teaches from. `storyboard check` fails on stale units, changed or missing locators,
unknown questions and objectives without a beat; it warns about objectives left to
practice and missing question beats. A beat with no narration needs a pause of at
least 0.5 seconds. On-screen text, math, numbers and code live in the beat's
`on_screen` items; scene code shows them by key. Math items carry `typst` (no `#`)
and, when copied from a formula block, the original `source_latex` for comparison.

## Provenance

These rules adapt, in our own words: Code2Video's planner, anchor and critic design
([arXiv:2510.01174](https://arxiv.org/abs/2510.01174),
[code](https://github.com/showlab/Code2Video/tree/1142d8e14cdc2806df85aedb0fbb5dca474caa0f));
TheoremExplainAgent's failure analysis
([arXiv:2502.19400](https://arxiv.org/abs/2502.19400),
[code](https://github.com/TIGER-AI-Lab/TheoremExplainAgent/tree/e9ece5db7756b6ded8a812eceeb936cfd02aae21));
the 3brown1blue production and pedagogy rules
([commit](https://github.com/AmitSubhash/3brown1blue/tree/fd9bf9c69ac33519acc00dc7faa21bd14b241e54));
manim-skill's narration-first timing
([commit](https://github.com/Yusuke710/manim-skill/tree/a0048d9e265499038f34a9aa58ff16d306b5034c));
Mayer's multimedia principles ([doi:10.1016/j.jarmac.2021.03.007](https://doi.org/10.1016/j.jarmac.2021.03.007));
and video length findings ([doi:10.1145/2556325.2566239](https://doi.org/10.1145/2556325.2566239)).
The links are provenance, not required reading.
