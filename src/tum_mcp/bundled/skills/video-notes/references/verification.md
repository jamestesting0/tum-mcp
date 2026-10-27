# Verification

Checks prove what they check. A passing render is not a teaching review, and a
teaching review is not proof that students learn.

## Before audio

- `storyboard check` has no errors; its warnings are deliberate.
- Teaching review, written to a file you will pass to `publish`: every beat traced to
  its locators; R1 to R12 from [teaching](teaching.md) applied; every formula's
  `typst` compared with its `source_latex`; numbers, directions, units and conditions
  matched; objectives left to practice named. Fix problems first.

## After each render

- The JSON lists `lint`, `failures`, `layout` and `check`. Fix the reported line,
  then the beat, then the chapter.
- Open every contact sheet in `sheets` and look at each beat's last frame: readable
  text, no overlap, nothing in the caption band, the right state shown for the
  narration, and the formula entries in `formulas` matching the source. Use `frames`
  for any moment the user mentions. If you cannot view images, publish with
  `--visual-review not-performed` and say so.
- `check` must pass every rule for a final run: H.264 and AAC, faststart, size and
  frame rate, duration within 0.5 s of timing, audio within 0.1 s of video,
  -16 ± 1 LUFS, true peak at most -1.4 dBTP, ordered captions and chapters inside the
  video, a poster and no unwaived layout issue.

## Report

Say which videos were created, updated, reused or left text-first; the narrator
profile; durations; which checks ran; whether visual review was performed; and what
is pending (for example narration in a language without a voice). Never call a
video verified, accurate or effective beyond what was checked.
