# Synthetic lecture recording

The fixture uses scripted speech rendered with macOS Samantha and generated
slide images. The recording contains no campus material or personal audio.
These files match the seed saved by all three runs in `fai-reliability-026`.

The seed copies the binary and its receipts together. Generating speech anew
can change the length of an utterance and the resulting transcript and media
digests. The fixture tests decode the recording to verify voice energy and
the captured frames at the key moments.

| File | SHA-256 |
| --- | --- |
| `recording.mp4` | `c513034d6665dae3930581b127de1a4747421bea9dea9db855ed293da4559249` |
| `transcript.json` | `679cb4689494394bb502bcd1795684711ec4645b3126bf71de94c09569c56e60` |
| `frames.json` | `41c39f0f75ece09b8f414699c2600dfdb6468902acf02b9c9d0c4c6ecb29f7ec` |
