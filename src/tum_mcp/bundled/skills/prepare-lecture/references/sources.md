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

Use `--language en` only when the language is known. The private pinned MLX runtime
is supported on native Apple Silicon macOS 15+; other hosts can use captions and
imported WebVTT. `install lecture --no-asr` skips ASR provisioning. Models load
lazily. Missing runtime/model access stops shared recognition early; it does not
repeatedly download a long recording for failing recognition attempts. Respect
capability errors instead of substituting an unreviewed recognizer or paid API.

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

Frames are a targeted escalation after text/material comparison:

```sh
tum-mcp lecture prepare PROJECT --recording URL --frame-at SECONDS
tum-mcp lecture frames PROJECT --recording KEY --start START --end END --limit 10
```

Use a frame only when it settles a consequential unresolved question. If a visual
moment cannot be located from text, explicitly requesting `prepare --previews`
fetches cheap approximate seek candidates. A candidate timestamp is not a measured
capture. Review a selected full frame's actual capture time and visible bytes;
never infer final frame content from a damaged image, caption or recognizer vote.
Repeated preparation reuses verified media/chunks and preserves prior selected
frames. There is no reason to send every frame or all word probabilities to an LLM.

Cached notes can be prepared offline, with the as-of date disclosed. A requested
refresh needs the selected recording's live metadata; use the established campus
connection if needed. Preserve existing authoring on denied access or failures.
