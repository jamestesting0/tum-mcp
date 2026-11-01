# Evidence acquisition and cost

Read this when evidence is missing, stale or unclear. Begin with the bound course,
selected recording URLs and local receipts. Do not enumerate unrelated courses.
The installed extension exposes `tum_live_courses`, `tum_live_recordings` and
`tum_live_recording` for bounded read-only metadata. Signed media capabilities
remain inside the host processor; browser authentication is a connection step,
not a browser download workflow. Do not export cookies or pass tokens to yt-dlp,
youtube-dl, FFmpeg or subprocess arguments.

The processor uses recording-scoped HLS retrieval directly. It prefers timed
captions, including imported original-time WebVTT, before optional local ASR:

```sh
tum-mcp lecture inspect PROJECT
tum-mcp lecture runtime status
tum-mcp lecture prepare PROJECT --recording https://live.rbg.tum.de/w/SLUG/ID
# For one selected recording with a supplied original-clock caption file:
tum-mcp lecture prepare PROJECT --recording URL --transcript lecture.vtt
```

Use `--language en` only when the language is known. `install lecture` provisions
an isolated, hash-locked local recognizer: MLX on Apple Silicon macOS 15+, NVIDIA
CUDA on Windows x64 and Linux/WSL x86_64 with a CUDA 12 GPU of compute capability 7.0+,
otherwise CPU int8 on Windows x64, Intel macOS 13+, Apple Silicon macOS 14 and glibc
2.28+ Linux/WSL x86_64/ARM64. Native Windows ARM64 and musl/32-bit systems use captions
or imported WebVTT. `runtime status` reports actual support and installation;
`install lecture --no-asr` skips provisioning. FFmpeg/ffprobe on PATH are needed
for audio extraction/frames, but not imported captions or cached text. On Windows,
the CPU runtime also needs the Microsoft Visual C++ runtime.

Models load lazily from pinned public revisions. An advanced
`TUM_MCP_LECTURE_ENGINE=cpu` override selects CPU instead of Metal or CUDA, and
`cuda` requires the GPU; keep it the same during installation and preparation. A GPU
that fails its install check leaves automatic selection on CPU. Missing native libraries/runtime/model
access stops shared recognition early; it does not repeatedly download a long
recording for failing recognition attempts. Respect capability errors instead of
substituting an unreviewed recognizer or paid API. Recognition can mishear technical
terms even with good sentence confidence; compare consequential wording with the
materials and source audio.

Whole-recording silence markers are terminally invalid. Where duration metadata
is absent, bounded playlist metadata can establish it before the silence decision.
Do nothing further with invalid content, including cached transcripts/images.
Partial silence/cuts are excluded while original recording time is retained.
Three quiet samples cannot prove that a whole recording is silent. Other quiet or
uncertain audio stays a coverage/review gap; do not fabricate speech from it.

Read compact text pages; `next_offset` continues the same time selection:

```sh
tum-mcp lecture transcript PROJECT --recording KEY --start 0 --end 28800 --limit 200 --offset 0
```

Continue until `next_offset` is null, retaining passage intervals and the returned
uncertain intervals. `--words` adds word timings/probabilities only for alignment
or repair. A transcript page is not proof of full lecture coverage. Compare with
the receipt's processed/missing/uncertain spans and make a full topic map first.

Classify before acquiring images: text notes need no frame, every highlight needs
a thumbnail, and a visual note may need an informative frame. Capture selected
frames in one call, then stage each and check the evidence:

```sh
tum-mcp lecture prepare PROJECT --recording URL --frame-at 772 --frame-at 1402
tum-mcp lecture frames PROJECT --recording KEY --start START --end END --limit 10
tum-mcp lecture thumbnail PROJECT --recording KEY --at 772
tum-mcp lecture thumbnail PROJECT --recording KEY --at 1402 --crop X,Y,WIDTH,HEIGHT
tum-mcp lecture check PROJECT
```

`--at` names the requested `--frame-at` time; the frame's measured capture time may
differ slightly. `lecture thumbnail` writes a lossless PNG of at most 960 px to
`.tum-mcp/lecture-assets/` and prints the thumbnail object plus a frame evidence item
ready to paste once you give it a key and review it. For a note, use the object as
`image` with a descriptive `alt`. `--crop` uses original frame
pixels. `lecture check` reports each highlight's opening and closing speech, boundary
errors (`start_off_passage`, `end_off_passage`), overlap with unclear speech
(`uncertain_speech`) and the share of processed time the highlights cover. Its
`note_items` prints the supporting speech and uncertainty for each note, without
imposing clip boundaries. It exits 1 on boundary errors or missing note speech.

If a visual moment cannot be located from text, explicitly requesting
`prepare --previews` fetches cheap approximate seek candidates. A candidate timestamp
is not a measured capture. Review a selected full frame's actual capture time and
visible bytes; never infer frame content from a damaged image, caption or recognizer
vote. Repeated preparation reuses verified media/chunks and preserves prior selected
frames. There is no frame-by-frame model loop and no reason to send all word
probabilities to an LLM.

Cached notes and highlights can be prepared offline, with the as-of date disclosed. A requested
refresh needs the selected recording's live metadata; use the established campus
connection if needed. Preserve existing authoring on denied access or failures.
