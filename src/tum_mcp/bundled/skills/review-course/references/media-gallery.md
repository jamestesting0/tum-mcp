# Media calibration

Play the assets before opening the verdicts. Compare the same underlying meaning;
score the named dimension, not duration or overall attractiveness. These are
course-independent synthetic cases, not learner-outcome evidence. Intended scripts
and sentence-level generation recipes are in [generate.py](media-gallery/generate.py);
[encode.sh](media-gallery/encode.sh) assembles the actual speech/video assets.

| Pair | Source meaning and task |
| --- | --- |
| [Clear referents](media-gallery/referents-clear.m4a) / [dense referents](media-gallery/referents-dense.m4a) | A fair die conditioned on even leaves 2, 4, 6; one is above 4, so the probability is 1/3. Listen without a page and directly enter the passage. |
| [Complete condition](media-gallery/delivery-clear.m4a) / [missing negation](media-gallery/delivery-broken.m4a) | Removal requires a nonempty queue. Compare the actual spoken negations against this source meaning. |
| [Aligned construction](media-gallery/synchrony-aligned.mp4) / [early result](media-gallery/synchrony-early.mp4) | Build the six outcomes, restrict to even, identify the favorable outcome, then divide. Compare speech to visible state throughout. |
| [Opaque solution](media-gallery/worked-opaque.mp4) / [worked demonstration](media-gallery/worked-clear.mp4) | Solve \(2x+3=11\), justify the operations and independently verify \(x=4\). The repaired version is longer. |

<details><summary>Verdicts and owning checks</summary>

- Clear referents anchor Clarity 3. Dense referents anchor Clarity 2 under
  `clarity.spoken_referents`: the facts are accurate given the source, but “second
  set”, “it”, “that” and “this” cannot be recovered on entry. Also use this passage
  as an audio chapter-entry case; do not double-charge the same defect.
- The complete condition anchors the intended correct delivery. The broken
  version deliberately loses “not” and reverses the instruction: 1 under
  `delivery.complete` when comparing synthesized output to the intended source
  script. If reviewing that erroneous script itself, own the defect under
  `correctness.source_match` instead. A nice voice cannot rescue the missing word.
- Aligned construction anchors Synchronization 3 and shows the sustained visible
  restriction/renormalization. The early version shows the answer from the start:
  Synchronization 1, `synchronization.reveal`. Use its missing visible construction
  as a separate concept-profile exercise: a correct endpoint alone cannot establish
  `intuition.visual_construction`. Identify the symptom being scored once.
- Opaque algebra has the correct result but omits the reason/state transitions:
  Intuition 1 under `intuition.local_mechanism`. The repaired demonstration
  subtracts equally, divides into two equal groups and substitutes back. It anchors
  the intended Intuition 3, despite being longer. Judge its actual rendering and
  sound; do not award unrelated dimensions from this single example.

These are designed anchors, not a claim that this session has auditioned them.
If sound perception is unavailable, do not claim calibration or score Delivery.
Actual source/script/frame checks can still be recorded separately.
</details>

## Reproduction

Use an existing authorized local kokoro-onnx 0.6.1 environment, Kokoro v1.0 fp32,
af_heart, en-us, speed 1, and its short shared eSpeak data path. No cloud service
or install-time generation. Supply real local paths; do not download per course.

```text
KOKORO_PYTHON generate.py speech --work WORK --model MODEL --voices VOICES --espeak DATA
DEV_PYTHON generate.py video --work WORK --font ATKINSON_TTF
bash encode.sh WORK
```

`WORK` is an absolute private scratch path. The bundled Video Notes runtime has
the Atkinson TTF; the dev environment needs Pillow and ffmpeg. Sentence durations
are measured from actual samples, with 0.35 s automatic continuation gaps. Frames
change on those boundaries. Outputs are AAC M4A and H.264/AAC MP4. The gallery's
light colors record the app palette at creation, not a second runtime theme store.
Raw WAVs, timings and frames stay in WORK; only eight compact final assets ship.
