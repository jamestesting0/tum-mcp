# Plots

A plot earns its place when the shape of a relation is the point: growth, decay, a
threshold, how two cases compare. Write its message in one sentence; the description says
it and the plot shows it.

## Choose the marks

| The idea | Series `style` and extras |
| --- | --- |
| A function's shape | `function` (sampled at build), drawn as a line |
| Measured or computed values over a continuous x | `points` drawn as a `line` |
| Values at whole steps (iterations, time steps) | `markers`: a dot per step joined by a guide line |
| A probability mass function | `stems` with `values: true`: one dot on a line per value |
| A cumulative distribution | `steps`: each value holds until the next x |
| A probability as an area | an `areas` entry under the density, with its value as `label` |
| Growth over orders of magnitude | `y_scale: log` |
| The value the text is about | a `notes` entry: a marked point with a short label |

## Rules

- **Never join discrete values with a line that suggests values in between.** A binomial
  PMF has mass only at whole k: it is stems, not a curve.
- **Never plot log values on a linear axis.** Use `y_scale: log`; the app labels its ticks
  with the real values (1, 10, 100, …), and the axis title names the quantity, not "log₁₀".
- **Functions come from a formula.** Write `function` in x with numbers, `+ - * / ^`,
  `exp`, `log`, `ln`, `log2`, `log10`, `sqrt`, `sin`, `cos`, `tan`, `abs`, `floor`,
  `ceil`, `min`, `max`, `pi` and `e`. The build samples it, breaks the line at poles and
  jumps, and keeps only what lies inside the axes. Never hand-sample a formula.
- **Bounds that read.** Pick axis bounds the reader can name (−6 to 6, 0 to 1). Give
  `x_ticks` for whole-number axes or special values; otherwise the app picks round ticks.
- **Labels in Unicode.** Axis labels are short and use Unicode (`σ(z)`, `γᵗ`, `P(X = k)`);
  LaTeX belongs in the text around the plot.
- **Room for labels.** Leave headroom above the highest value (`y_max` about a tenth
  above it) so notes and value labels fit inside the frame. A note that finds no clear spot
  is drawn on a small knockout box: move its point or widen the range.
- **Few series, labelled.** At most four, each with a label. With two or three that end
  apart, `legend: direct` writes the labels at the line ends; otherwise the legend shows
  them.
- **Values from the source.** Every point comes from the source or from a formula the
  source gives. Recompute values with code.

## Check

Build, then run `tum-mcp study visuals PROJECT --unit KEY` and open the plot's contact
sheets at phone and desktop width. The check reports labels that overlap or sit on a curve
and text under 12 px. The message should be visible within five seconds, every label
should sit clear of the lines, and the scale should not mislead. review-course scores the
plot on its [visual rubric](../../review-course/references/visuals.md#rubric).

## Sources

- Wilke, [Fundamentals of Data Visualization, ch. 3](https://clauswilke.com/dataviz/coordinate-systems-axes.html):
  label log axes with the original values and title them with the variable.
- [SciPy's binomial distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binom.html)
  draws a PMF as markers on vertical lines.
- [seaborn's ECDF plot](https://seaborn.pydata.org/generated/seaborn.ecdfplot.html) draws a
  cumulative distribution as a connected staircase.
- Rougier et al. 2014, *Ten simple rules for better figures*: know the message, do not
  trust defaults, do not mislead.
