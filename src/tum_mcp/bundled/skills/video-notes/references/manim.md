# Scene code: helpers and pinned Manim

The runtime pins Manim Community 0.22.0 with the Cairo renderer and Typst. It is not
ManimGL (`manimlib`), and 0.22 removed several older flags. Rendering settings are
fixed by the pipeline; scene code never touches `config`.

## File shape

`videos/scenes/STEM/chapters.py` holds one class per chapter, named after the
chapter key in upper case (`c01` → `C01`), extending `NotesScene`. Module level may
hold imports, constants and small helper functions only.
Keep chapter-specific drawing helpers as methods on that chapter class.
Module-level helpers are shared cache inputs: changing one invalidates every
chapter that shares the scene file, even if its own construction did not change.

```python
from manim import *
from vnotes import NotesScene


class C01(NotesScene):
    def construct(self):
        with self.beat("b01") as b:
            node = Circle(radius=0.6, color=self.color("accent"))
            name = self.label("start").move_to(node)
            self.play(Create(node), FadeIn(name), run_time=b.share(0.5))
        with self.beat("b02") as b:
            rule = self.math("rule").to_edge(UP, buff=1)
            self.play(Write(rule), run_time=b.share(0.6))
```

Every beat of the chapter appears once, in storyboard order, as a `with self.beat`
block; time outside beats is not allowed.

## Timing

A beat's duration comes from measured narration. `b.duration` is that budget,
`b.share(f)` a fraction of it (0 < f ≤ 1) and `b.remaining` what is left. When the
block ends the scene waits out the rest exactly, frame for frame. Running more than
one frame past the budget fails with "animations run Ns past the narration": shorten
`run_time` values or split the beat. Leave a little slack; Manim rounds each
animation up to whole frames.

Use `with self.cue(1) as cue:` inside a beat to start at its first measured
sentence; indices are one-based. `cue.duration`, `cue.share(f)` and `cue.remaining`
use that sentence's budget. The context pads to its end; do not also wait manually.
Cues must increase, cannot nest, and cannot start after their measured time.
Place each reveal/highlight in the cue that actually names it, not at the beat's
beginning because the whole beat mentions it eventually.

## Helpers

| Call | Returns |
| --- | --- |
| `self.label(key, size=32, color=None, width=None)` | Plain-text label in the house font; an explicit scene width wraps without shrinking. |
| `self.math(key, size=40, color=None)` | Typst math (LaTeX only if the course style opts in). |
| `self.number(key, size=32, color=None)` | Formatted storyboard number with its unit. |
| `self.value(key)` | The number as a float, for geometry or `tracker.set_value(self.value("k"))`. |
| `self.code(key, size=24)` | `VGroup` of code lines; `lines[i]` is line i + 1. |
| `self.color(token)`, `self.symbol(name)` | Colors (see visuals). |
| `self.anchor(row, column)`, `self.region(name)` | Layout positions. |
| `self.asset(name)` | An SVG from `videos/assets/`. |

Keys and tokens are string literals, including in helper functions: build a palette
as `[self.color("c1"), self.color("c2")]`, never `self.color(f"c{i}")`. Module-level
helpers take `self` as their first parameter so the same checks apply. Size
arguments below the minimums raise. `self.code(key)` keeps indentation and blank
lines; `lines[i]` is line i + 1 even when that line is blank.

## Forbidden by lint

Imports other than `manim`, `numpy`, `math` and `vnotes`; `open`, `exec`, `eval`,
`getattr` and similar; `os`, `sys`, `subprocess`, `pathlib`, `Path`; dunder
attributes; numpy file I/O (`np.load`, `tofile`, ...); `config` changes; and any text
or number class used directly: `Text`, `MarkupText`, `Paragraph`, `Tex`, `MathTex`,
`Typst`, `MathTypst`, `Code`, `DecimalNumber`, `Integer`, `Title`, `Table`,
`BulletedList`, labelled shapes, `ImageMobject`, `SVGMobject`. Use the helpers.

`FadeIn(m, shift=v)` ends where `m` already is and starts at `m - v`; place `m` at its
final position first. Known wrong names: `ShowCreation` (use `Create`), `TexMobject`, `TextMobject`,
`ShowCreationThenDestruction`, `CONFIG = {...}`, `self.embed()`, `add_sound`,
`add_subcaption` (captions come from timing). Removed CLI flags such as
`--write_to_movie`, `-i`, `--flush_cache` and `--custom_folders` do not apply; the
pipeline runs Manim for you.

## Typst math

Typst math differs from LaTeX: `frac(a, b)` or `a/b`, `sum_(i=1)^n`, `x_i`, `x^2`,
`overline(x)`, `hat(x)`, `sqrt(x)`, `vec(a, b)`, `mat(1, 2; 3, 4)`, `->`, `<=`,
`!=`, `dot`, `times`, Greek by name (`alpha`, `Delta`). Multi-letter names need
quotes or a space-free function form: `"cost"(v)`. A conditional bar is `|`
(`P(A | B)`); words such as `mid` or `given` render as plain text, not operators. Group parts for coloring with
`{{ a^2 + b^2 : lhs }}`. `#` is rejected. Always compare the rendered formula with
the source LaTeX in the render report.
