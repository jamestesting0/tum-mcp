# Narration and voice

## Writing for video

The narrator explains while the picture shows. Speak to the viewer in a natural,
conversational tone. Use short sentences with one idea each. Refer to what is on
screen by name plus a non-color cue ("the circled frontier node c"), never "this"
alone. Do not read on-screen text aloud word for word, and do not narrate the
production. Write symbols and acronyms the way they should be spoken; keep a
pronunciation map in `videos/voice.json` and apply it when writing sentences.
About 130 to 150 words per minute is a starting point, not a target. Each storyboard
sentence becomes one audio file and one caption cue, so keep sentences under about
25 words.

## Voice provider

Honor the user's provider preference and any existing course voice first. Otherwise
prefer the free ElevenLabs text-to-speech website when it really generates the
supplied text and lets you download it; check one short sentence first and confirm
the download speaks that text. Use local Kokoro (kokoro-onnx in a uv environment
outside the course) when ElevenLabs is unavailable, exhausted or blocked, unless the
user restricts the provider. Never create accounts, pay, spend existing credits,
solve CAPTCHAs or rotate identities to get around a limit. Send only reviewed
narration text to a cloud service.

Kokoro has no German voice. For a language no authorized voice supports, keep
narration pending with the precise reason, render a silent draft
(`timing --silent`) for visual review only, and do not translate. Silent drafts are
never published.

Shared Kokoro model files and runtimes belong in host user storage, never in the
course: macOS `~/Library/Caches/tum-mcp/tts/kokoro/`, Windows
`%LOCALAPPDATA%\tum-mcp\Cache\tts\kokoro\`, Linux `$XDG_CACHE_HOME/tum-mcp/tts/kokoro/`
(default `~/.cache/...`). Upstream publishes no digest for the Kokoro release files, so
record their SHA-256 in a receipt at the first download, verify against it and reuse
them; never per course. eSpeak NG ignores a data path longer than about 160
characters and falls back to a build path (`Error processing file
'/Users/runner/.../phontab'`); the macOS runtime path exceeds that, so copy
`espeak-ng-data` once into the shared cache (for example
`~/Library/Caches/tum-mcp/tts/espeak-ng-data`) and pass it as kokoro-onnx's
`EspeakConfig(data_path=...)`.

## Profiles and files

Add the actual voice to `videos/voice.json` under `profiles` before synthesis: key,
`provider`, `route` (for example "anonymous website" or "local"), `voice`,
`language`, `model` (or "unknown") and `settings`. One profile per video. The
profile's settings are part of every chunk's name, so changing them regenerates
audio.

`tum-mcp video-notes narration PROJECT STEM --profile KEY` lists each sentence with
the exact file to write under `videos/.build/STEM/audio/` (any of wav, mp3, m4a,
flac, ogg; exactly one per sentence). Files that already exist are reused. Then
`timing PROJECT STEM --profile KEY` measures them, rejects missing files and flags
implausible speech rates (likely truncated or garbled audio), and writes the beat
timing the scenes use. Changing any sentence means writing its new file and running
timing again; unchanged sentences keep their audio.
