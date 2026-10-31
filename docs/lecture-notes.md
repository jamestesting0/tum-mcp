# Lecture

Install the optional extension only when needed:

```sh
tum-mcp install lecture
# Captions/imported WebVTT without provisioning recognition:
tum-mcp install lecture --no-asr
```

Restart the coding client to load Prepare Lecture and the three TUM-Live metadata
tools. Base setup keeps its five skills and existing services. Removing the option
with `tum-mcp uninstall lecture` preserves course notes/highlights, evidence, sessions,
model caches and customizations. Reinstalling can reuse them.

Ask: “Prepare Lecture from this recording and these slides.” It adds Lecture to the
same course app, alongside Study and Exercises. Notes preserve useful short remarks,
conditions, corrections and explicit instructions. They show the information directly,
with sources tucked behind a source control and an optional meaningful recording frame.
Highlights are substantial worked explanations worth following: an example, derivation,
demonstration, method comparison or conceptual explanation that adds to the materials.
A highlight shows its time range and duration, a frame from the recording, a title,
one sentence on what it teaches and up to three points; the range and the frame open
the recording at its start. Notes appear first, without prominent timestamps or required
thumbnails. The lecture list shows note/highlight counts and highlight watching time.
The Contents button follows the Notes/Highlights hierarchy.
Either section may be absent; a reviewed lecture may have no worthwhile additions.
Attribution review stays private, so the reading flow is clean.
Lecture has no quizzes or flashcards; broader teaching/practice stays in Study.

## Processing order and cost

1. Validate the selected recording. Whole-recording silence markers make it invalid;
   stop before content, including cached transcripts/images. Missing duration can
   be resolved from bounded playlist metadata. Partial silence/cuts retain the
   original recording clock.
2. Prefer existing captions or supplied original-time WebVTT. Otherwise the optional
   pinned local recognizer scans retained audio in resumable chunks. It checks all
   channels, preserves coverage gaps and flags uncertain/repetitive recognition.
   Three quiet samples alone cannot invalidate a recording.
3. Read compact transcript passages, map the full retained lecture and compare with
   verified slides/materials. Classify contributions as Note, Highlight or Omit.
   A ten-second remark becomes a note, not a watch card. Most highlights last a few
   minutes and include their setup through their conclusion; never pad a passage.
   Compare the explanations, not just matching topic names: a printed question may
   lack the reasoning supplied live. Missing materials mean comparison is unavailable.
4. Capture one recording frame per highlight, chosen from the transcript, and look at
   each one: it confirms the topic and notation; speech establishes clip boundaries. `lecture
   thumbnail` stages it as a 960 px thumbnail. No default previews or frame-by-frame
   model calls; captures use measured times and verified image bytes. Capture a note
   image only when it carries necessary visual information, and give it descriptive alt text.
5. Run `lecture check`, which verifies each highlight's boundaries against the
   transcript and prints its opening and closing speech for review. It also prints
   each note's supporting speech without treating it as a clip. Then build a coherent batch.

Vision cost depends on the chosen model and image size: one frame per highlight,
not per second. This workflow keeps images and model context small; it does not
promise a fixed price or a measured accuracy improvement. In the selected 81-minute retained-audio experiment,
compact text for 200 passages used 39,412 bytes versus 372,519 with word details,
with identical text/times. An unchanged preparation reused 12 recognition
checkpoints with zero inference and fetched about 456 KB of playlist metadata.
These are observations from that source and cache, not universal benchmarks.
A direct media playlist offered no separate audio rendition; the processor used
bounded muxed segments rather than guessing alternative download URLs.

## Host commands

Use the existing course binding and campus connection. Authentication is separate
from HTTP media retrieval; do not export cookies or pass signed URLs to download
commands. Captions and imported original-time WebVTT work without a recognizer.
Automatic ASR installs separately with hash-locked CPython 3.13 wheels and lazy,
revision-pinned public model weights; neither is part of the base runtime.

| Host | Local recognizer |
| --- | --- |
| Apple Silicon macOS 15+ | MLX acceleration by default |
| Apple Silicon macOS 14 | CPU int8 |
| Intel macOS 13+ | CPU int8 |
| Windows x64 | NVIDIA CUDA when a GPU is detected, otherwise CPU int8; Microsoft Visual C++ runtime required |
| Linux/WSL x86_64, glibc 2.28+ | NVIDIA CUDA when a GPU is detected, otherwise CPU int8 |
| Linux ARM64, glibc 2.28+ | CPU int8 |

Native Windows ARM64, 32-bit systems and musl Linux have no supported locked
runtime. Use captions/imported WebVTT there. CPU inference requires compatible
CTranslate2 instructions (SSE4.1 on x86); installation verifies native imports and
int8 support before selecting the runtime. See the upstream
[CTranslate2 requirements](https://opennmt.net/CTranslate2/installation.html).
Windows, Linux x64 and Apple Silicon recognition have native CI smoke checks;
Intel Mac and Linux ARM64 compatibility also depends on the published wheels.

FFmpeg and ffprobe must be on PATH for recording audio extraction or selected
video frames. They are unnecessary for imported captions and cached text.
`lecture runtime status` reports the selected engine and missing prerequisites.
Use `lecture runtime install` to retry after fixing a prerequisite. Advanced users
can set `TUM_MCP_LECTURE_ENGINE=cpu` consistently for installation and preparation
to bypass Metal or CUDA; the default `auto` retains existing MLX runtimes and model caches.
An engine switch uses separate caches. No cloud transcription API is configured.

On Windows x64 and Linux/WSL x86_64, `auto` uses an NVIDIA GPU of compute capability
7.0 or newer (GTX 16, RTX 20 series and later) when its driver supports CUDA 12
(driver 525 or newer); older GPUs stay on CPU. Only the driver is needed: the runtime
adds a pinned cuBLAS (about 600 MB) and decodes in float16, without a CUDA toolkit
or cuDNN. Installation first creates a cuBLAS handle on the GPU. If that fails,
automatic selection records it (`lecture-runtime/cuda-unusable.json` in the data
directory) and installs the CPU runtime instead, so `tum-mcp update` keeps working.
After a driver fix, `TUM_MCP_LECTURE_ENGINE=cuda tum-mcp lecture runtime install`
retries and, on success, clears that record. `cuda` never falls back silently;
`lecture runtime status` shows when a GPU was declined.

CPU decoding uses int8, one worker and at most four threads. It consumes the full
retained audio, with word timestamps and no VAD retiming. ASR remains fallible,
especially for names and notation; compare important wording with slides and the
recording rather than treating confidence scores as proof.

```sh
tum-mcp lecture inspect PROJECT
tum-mcp lecture runtime status
tum-mcp lecture prepare PROJECT --recording URL
# One selected recording with supplied captions:
tum-mcp lecture prepare PROJECT --recording URL --transcript lecture.vtt
# Read bounded compact pages; continue with returned next_offset:
tum-mcp lecture transcript PROJECT --recording KEY --start 0 --end 28800 --limit 200 --offset 0
# One frame per chosen highlight, then stage each as a thumbnail:
tum-mcp lecture prepare PROJECT --recording URL --frame-at SECONDS --frame-at SECONDS
tum-mcp lecture frames PROJECT --recording KEY --start START --end END
tum-mcp lecture thumbnail PROJECT --recording KEY --at SECONDS [--crop X,Y,WIDTH,HEIGHT]
# Check note evidence and highlight boundaries (exit code 1 on errors):
tum-mcp lecture check PROJECT
```

`--words` adds word alignment details to transcript reads. `prepare --previews`
explicitly requests approximate seek candidates; they are not verified capture
times. `--language en` is appropriate only for a known English recording.

Prepared media, raw transcripts, receipts and review notes stay under `.tum-mcp/`.
Safe source receipts can be reconciled into the shared inventory:

```sh
tum-mcp lecture export-snapshot PROJECT --output snapshot.json
tum-mcp study sync PROJECT --snapshot snapshot.json
tum-mcp study schema lectures
tum-mcp study build PROJECT --local-only
tum-mcp study inspect PROJECT
```

The agent authors `app/lectures.json` (schema version 2) using real source hashes and
coverage; the legacy `study/` layout stays supported. Thumbnails stage in
`.tum-mcp/lecture-assets/` and copy only when selected. Source freshness and the
authored content's semantic revision are separate, preserving comments through harmless
receipt/decorative-thumbnail updates. Note text and meaningful note-image edits change
the revision. Local comments support `--view lectures --lecture KEY`.

Open with `tum-mcp study` from the course folder. For a credential-free synthetic
preview after installing the extension, use `tum-mcp study demo PROJECT --lectures`.
The default demo includes Study, Exercises and Exam. The Lecture option
adds a synthetic 90-minute recording with two short notes and three worked-explanation
highlights with thumbnails.
Synthetic teaching/timestamps exercise the product and do not establish real lecture
accuracy.

## Publication

Lecture is excluded from publication by default, including old saved
configurations. After reviewing public exposure, use the existing publish-course
workflow with `--include-lectures`; Exercises has a separate choice. Exclusion
removes lecture text, lecture-only sources/math and images from exports,
and removes previously managed remote images while preserving unrelated files.
Raw media/transcripts, comments and private review metadata are never exported.
The entire export, including its ownership marker, must fit 16 MiB and 100 files.
Every highlight carries a thumbnail, so many lectures may not fit; thumbnails are not
silently omitted or compressed. A Lecture-only app excluded from publication cannot
produce an empty site.
