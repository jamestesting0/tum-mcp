# Lecture Notes

Install the optional extension only when needed:

```sh
tum-mcp install lecture
# Captions/imported WebVTT without provisioning recognition:
tum-mcp install lecture --no-asr
```

Restart the coding client to load Prepare Lecture and the three TUM-Live metadata
tools. Base setup keeps its five skills and existing services. Removing the option
with `tum-mcp uninstall lecture` preserves course notes, evidence, sessions,
model caches and customizations. Reinstalling can reuse them.

Ask: “Prepare Lecture Notes from this recording and these slides, focusing on
what the professor explains beyond the material.” It adds Lecture Notes to the
same course app, alongside Study and Exercises. Notes have coherent explanations,
examples, important qualifications, formulas and selective source images. The
sources of each passage and figure open the recording at the measured time, so the
text carries no timestamps, and the Contents button lists the lecture's sections. Attribution
review stays private, so the reading flow is clean.
Lecture Notes has no quizzes or flashcards; broader teaching/practice stays in Study.

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
   verified slides/materials. Select additional reasoning, examples, corrections,
   caveats and advice; do not claim novelty when comparison materials are missing.
4. Use only a few critical recording frames when text/materials leave a consequential
   visual question unresolved. No default previews or frame-by-frame model calls.
   Captures use measured times and verified image bytes. Supporting diagrams use
   normal content blocks, with private attribution review.
5. Review the notes, citations and selected figures, then build a coherent batch.

Vision cost depends on the chosen model and image size. This workflow reduces
unnecessary images and model context; it does not promise a fixed price or a
measured accuracy improvement. In the selected 81-minute retained-audio experiment,
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
| Windows x64 | CPU int8; Microsoft Visual C++ runtime required |
| Linux/WSL x86_64 or ARM64, glibc 2.28+ | CPU int8 |

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
to bypass Metal; the default `auto` retains existing MLX runtimes and model caches.
An engine switch uses separate caches. No cloud transcription API is configured.

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
# Only after identifying an unresolved visual question:
tum-mcp lecture prepare PROJECT --recording URL --frame-at SECONDS
tum-mcp lecture frames PROJECT --recording KEY --start START --end END
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

The agent authors `app/lectures.json` using real source hashes and coverage; the
legacy `study/` layout stays supported. Captured images stage in
`.tum-mcp/lecture-assets/` and copy only when selected. Source freshness and note
semantic revision are separate, preserving passage comments through harmless
receipt/image updates. Local comments support `--view lectures --lecture KEY`.

Open with `tum-mcp study` from the course folder. For a credential-free synthetic
preview after installing the extension, use `tum-mcp study demo PROJECT --lectures`.
The default demo still has only Study and Exercises. Synthetic teaching/timestamps
exercise the product and do not establish real lecture accuracy.

## Publication

Lecture Notes is excluded from publication by default, including old saved
configurations. After reviewing public exposure, use the existing publish-course
workflow with `--include-lectures`; Exercises has a separate choice. Exclusion
removes lecture text, lecture-only sources/math and referenced images from exports,
and removes previously managed remote images while preserving unrelated files.
Raw media/transcripts, comments and private review metadata are never exported.
The entire export, including its ownership marker, must fit 16 MiB and 100 files.
Essential figures are not silently omitted/compressed; a notes-only app excluded
from publication cannot produce an empty site.
