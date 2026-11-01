# Choose notes and watchable explanations

Read this after the full transcript map and the relevant course materials.

## Selection

For each candidate, decide:

1. Is it useful for this course? Otherwise omit it.
2. What does it add to the available materials? Compare assumptions, intermediate
   steps, their justification and the interpretation, not merely titles or formulas.
3. Can a concise note preserve that contribution, with a formula or frame if needed?
   Prefer a note.
4. Does following the reasoning or demonstration itself teach something? Consider a
   highlight. Judge for a student learning the topic, not an expert who can supply
   the missing steps.
5. Are the content, context and evidence verified? Resolve uncertainty before making
   a confident claim; neither importance nor length establishes correctness.

| Contribution | Treatment |
| --- | --- |
| Brief clarification, condition, correction, convention or explicit exam instruction | Note, preserving its scope |
| Worked example, calculation, proof or derivation with useful reasoning beyond the materials | Highlight |
| Method choice, counterexample, failed attempt or debugging process | Highlight when the diagnosis is worth following |
| Sustained intuition, analogy, connection between ideas, demonstration or simulation | Highlight when following it adds understanding |
| Student question | Note for a concise conclusion; highlight for substantial reasoning, including the question |
| Brief visual moment | Note with a meaningful frame when needed; the source link can open the recording |
| Repetition, slide read-aloud, greetings, irrelevant asides or logistics without consequence | Omit |

A question already printed in the materials may still need its missing working or
justification. Conversely, a new fact may need only a note. Do not create both a note
and a highlight description saying the same thing; retain both only for distinct
purposes, such as a condition to remember and a walkthrough applying it.

Missing comparison materials mean "comparison unavailable", not "absent from slides".
Do not infer exam predictions from emphasis. Include consequential administrative
instructions only when explicit and not already adequately available in course sources.
Notes-only, highlights-only and no selected additions are valid outcomes. Record
omission reasons in the private review map, not as filler on the page.

## Size and boundaries

- One idea per highlight. Merge adjacent stretches on the same idea; split where the
  topic changes.
- Highlights normally run a few minutes (often 2–10). A ten-second remark is a note;
  passages below roughly a minute default to notes. These are editorial guides, not
  schema cutoffs: never pad a passage to qualify.
- Start at the passage that opens the explanation (the question or the example's
  setup) and end with the passage that concludes it, including the correction after
  a mistake. Resolve pronouns and necessary prerequisites; do not begin at
  "therefore this is zero" without its setup. Use the passage times exactly.
- Split interleaved discussion into coherent, independently understandable ranges,
  or omit it; do not join disconnected moments into a fabricated continuous clip.
  Mention a necessary earlier explanation briefly rather than inventing context.
- Review the total watching time reported by `lecture check`. Every passage must
  earn its time; neither a count nor a percentage is a quota.

## Writing

- A note states one useful claim, usually in one or two sentences. Include its
  conditions and concrete mathematical objects; use inline formulas or a frame
  rather than describing a visual object only in words. Do not turn notes into
  long lessons or add a thumbnail merely for decoration.
- A highlight title names the particular question, example or explanation
  ("Tracing duplicate enqueues through a shared neighbour"), not a generic topic.
- *Teaches* is one sentence that states what the student learns, with its condition.
- Points: at most three, one claim each: the key step, the example's numbers, a
  condition or pitfall. A point never repeats the teaches line. Explain what watching
  adds without reproducing the entire worked solution below its preview.
- State ideas directly. Never narrate the recording ("In this part", "The professor
  says"). Attribution is useful for stated exam scope or course instructions; preserve
  it there. Quote only verified wording. The app supplies highlight ranges and hides
  note times in their source controls.
- Write symbols and formulas as inline LaTeX `\( ... \)`. Take names, terms and
  notation from the slides or the frame, not from recognized speech alone.
- The lecture summary is one to three sentences about the lecture's scope.
- Name the slides or script pages a highlight relates to in its sources, with their
  real page locator.

## Frames

- Every highlight has one thumbnail. Capture it at the highlight's start, or later
  where the slide or board shows the topic (speech cues such as "as you can see",
  "this diagram", "on the board"). It must lie inside the highlight.
- Look at each captured frame. When it shows something else (the lecturer only, the
  previous slide), capture another time. Crop to the slide or board when the frame
  is mostly room.
- Thumbnails carry no caption; the highlight's text does the teaching.
- A note image is optional and informative, not a decorative thumbnail. Stage a
  verified frame with `lecture thumbnail`, use it as the note's `image` and add a
  descriptive `alt`. Its capture must fall inside the note's speech evidence.
  Crop to the relevant object and check its labels at phone width; a full slide
  shrunk into a note may be illegible even when the original frame is clear.
  If motion cannot be represented by the still, keep the recording source accessible.

## Uncertainty and review

Never describe what you could not verify. Confirm highlights over unclear speech with
the slides or a frame, or keep the evidence marked uncertain. Names and notation are
high-impact recognition failures; resolve them from verified materials or a legible
frame, not from agreement between recognizers.
Check notes just as carefully. Do not silently reconcile a conflict between the
lecturer and the materials, or retain an early error without the later correction.
Keep unresolved claims out of confident notes/highlights and disclose the review gap.

Keep a compact private review map, for example
`.tum-mcp/lecture-review/LECTURE_KEY.md`: the topic/time map, the compared material
locators and hashes, each Note/Highlight/Omit decision, the added value of every
highlight, rejected candidates, unresolved speech and each frame choice. It is not
browser content.

## Basis

- Transcript first, frames chosen from it: [Chapter-Llama](https://arxiv.org/abs/2504.00072)
  (CVPR 2025) found speech carries most of the chaptering signal and a few
  speech-selected frames beat many evenly spaced ones.
- Boundary and description checks: [LVSum](https://arxiv.org/abs/2604.10024) (2026)
  found that multimodal models pick important moments but give imprecise timestamps
  and descriptions that drift from the interval.
- Quote-anchored segments with per-segment frames:
  [Cuepoint](https://github.com/caomaocao/cuepoint).
- Writing: [ASD-STE100 skill writing rules](https://github.com/danyuchn/asd-ste100-skill/blob/8da6b6340aa22faf46fd07db8efbdea010cd38d9/references/writing-rules.md)
  (clear references, direct actors, stable terminology; not certified STE) and the
  [LearnHarness teaching guide](https://github.com/amosblomqvist/learnharness/blob/3dc88472eea41eed0d5e5f29c2f16f8d063c415b/src/agent/prompts/teacher/20-teaching.md)
  (preserve prerequisites, justified inference and useful examples).

These sources shape selection and checks; they do not establish a measured learning
benefit of watching highlights instead of the full lecture.
