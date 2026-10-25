# Local Kokoro across execution hosts

Use Kokoro as the free local fallback described in [voice selection](voices.md).
Detect the OS, CPU architecture, available Python/runtime and writable user storage
on the host that executes synthesis. That may differ from the user's browser or
desktop OS. Set up only the selected engine, reusing compatible installed tools.

## Check compatibility before setup

Use the [Kokoro ONNX implementation](https://github.com/thewh1teagle/kokoro-onnx)
and its supported dependencies for a CPU-based route. Check current
[ONNX Runtime installation support](https://onnxruntime.ai/docs/install/) for the
actual OS, architecture and Python version. Do not assume a wheel for every Intel,
ARM, Windows, macOS or Linux combination. A GPU is optional; do not install GPU
drivers or require administrator/system-package changes as a routine side effect.

Check the model's [language and voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).
Choose a preset for the course language; af_heart is a starting candidate for US
English, not a universal multilingual voice. Do not translate a course to make a
voice work. If this host/language has no viable local route, retain scripts and
pending coverage with the precise reason. A browser-only/mobile client needs an
available execution host; this skill does not implement a mobile or browser runtime.

Run a short passage on the actual host before a whole category. Model file size
does not establish peak RAM or generation speed. Use that sample to check runtime,
pronunciation and capacity, rather than promising operation on every laptop.

## Shared assets, course outputs

Keep model weights, preset voice data and reusable pronunciation resources in one
user cache per execution host. These files contain no course text. Resolve paths
with the host's environment/path utilities rather than copying shell syntax from
another OS. On Unix, use XDG locations only when absolute; otherwise use defaults.

| Execution host | Model-cache base |
| --- | --- |
| macOS | `~/Library/Caches/tum-mcp/tts/kokoro/` |
| Windows | `%LOCALAPPDATA%\tum-mcp\Cache\tts\kokoro\`; if unset, resolve the user's `AppData\Local` folder. |
| Linux | `$XDG_CACHE_HOME/tum-mcp/tts/kokoro/`; default `~/.cache/tum-mcp/tts/kokoro/`. |

Use a version/variant directory under that base, for example kokoro-v1.0-fp32.
Allow an explicitly configured, writable shared cache in a restricted or remote
host. WSL uses Linux paths/runtime unless synthesis is deliberately run on Windows;
do not pass a Windows virtual environment to Linux or the reverse. Ephemeral
containers may need a permitted persistent volume; disclose when reuse lasts only
for that environment. Do not change mounts or escape sandbox permissions.

The runtime is shared too. Prefer an existing compatible tool environment or
an isolated environment managed by [uv](https://docs.astral.sh/uv/guides/scripts/),
outside individual courses. For an explicit persistent virtual environment, use:

| Host | Runtime base |
| --- | --- |
| macOS | `~/Library/Application Support/tum-mcp/tts/runtimes/` |
| Windows | `%LOCALAPPDATA%\tum-mcp\tts\runtimes\`; use the same user-folder fallback. |
| Linux | `$XDG_DATA_HOME/tum-mcp/tts/runtimes/`; default `~/.local/share/tum-mcp/tts/runtimes/`. |

Distinguish environments by engine/dependency versions, Python ABI, OS and CPU
architecture. Never reuse a virtual environment copied from another machine/OS.
Pin and record the actual installed versions; compatible courses reuse that
environment. For example, kokoro-onnx 0.6.1 supports Python 3.10–3.13; check its dependency
wheels for this host before selecting it. A package version is separate from the
model asset version. Host installation
policy applies; keep engine dependencies outside the course's project environment.

Use the pronunciation data/library from the actual runtime. If a packaged eSpeak
loader cannot locate its data, resolve its library/data paths explicitly or repair
that host's shared pronunciation cache before continuing. Avoid hard-coded CI,
Homebrew or system-library paths. Keep such reusable data out of each course.

All course text, speech chunks, final audio, scripts, chapters, provider state and
QA stay under PROJECT/audio/. Keep shared model identities and SHA-256 values in
voice.json; resolve their local paths on each host. The relative paths in manifests
and playlists still identify course files confined to audio/. Do not symlink shared
models into a course or require their previous machine's absolute path.

## Populate once, verify and reuse

Check the shared cache before downloading. Reuse a matching verified model and
voice file, including offline. A verified legacy per-project model can be copied
once into shared storage; preserve the existing project rather than deleting it.
No course text needs to be sent anywhere for local synthesis.

Select artifacts from the publisher/implementation's documented release and
record the exact URLs, model variant and SHA-256 values. Keep a shared asset receipt
beside the versioned files so new courses can verify them independently. Download
missing assets to temporary files inside the shared cache under a cross-platform interprocess
lock. Verify against the selected trusted digest before atomically promoting a
complete version and its receipt. Concurrent courses should wait for or reuse that completed
version, never read a partial download. Use bounded waits and report a genuine
failure. A checksum mismatch is not permission to accept a new digest silently.

Pin a verified artifact receipt when upstream provides no independent digest;
describe that provenance honestly rather than claiming publisher authentication.
Changing weights, voice data, phonemizer or quantization creates a new profile and
invalidates dependent speech chunks. Quantized variants need their own sample
check; do not silently substitute one under a previously verified model identity.

Leave the last usable assets intact on network failure, interruption or disk-full
errors. Clean only the current run's incomplete temporary files. Do not reinstall
or redownload valid assets per category, delete shared models when cleaning one
course, or clear unrelated user caches. Record setup failures under the course's
audio/.build/ and keep its existing published audio usable.
