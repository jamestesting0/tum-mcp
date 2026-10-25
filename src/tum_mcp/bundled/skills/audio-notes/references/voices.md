# Free voice selection and repeatable generation

Honor the user's provider preference and an existing verified course voice first.
For a new course without an established profile, prefer ElevenLabs' free anonymous
website route when it demonstrably generates the supplied text and permits saving
the result. Local Kokoro is the authorized automatic fallback when that route is
unavailable or free usage is exhausted. No paid subscription, account creation or
API key is a prerequisite. An explicit provider-only instruction takes precedence.

Keep voice.json under audio/. Record actual provider, access route (for example,
anonymous website versus authenticated API), visible model/voice name or ID,
language/accent, speed, pronunciation map and generation settings. If a website
does not expose the model/version, record it as unknown; never invent a pinned ID.
Record the preferred provider and fallback policy separately from actual profiles.
Keep per-category profiles in the manifest; voice.json may hold several profiles
when fallback leaves the playlist with different narrators. README must disclose
which categories use which engine. Store no credentials or account records here.
Before replacing a legacy single-profile voice.json, retain that verified profile
for the categories it describes; a new fallback profile must not relabel old audio.

## Fallback and continuity

| Situation | Action |
| --- | --- |
| A category already has verified Kokoro audio | Keep its Kokoro profile for updates; do not switch back just because ElevenLabs is available. |
| ElevenLabs generation and saving work within authorized free usage | Continue the selected voice and retain reusable chunks. |
| A confirmed quota, login, payment, CAPTCHA or download/tool limitation prevents ElevenLabs | Save completed work, record the reason and continue eligible affected categories with Kokoro without another provider-approval question. |
| A transient service/network error occurs | Use a bounded retry when justified; if unavailable, record the failure and use Kokoro. Do not repeat a known blocked ElevenLabs probe for every category in the run. |
| The user requires ElevenLabs only, or Kokoro cannot support this host/language | Preserve scripts and pending coverage; explain the precise constraint. Do not silently translate or select another provider. |

Read [local Kokoro and shared assets](kokoro.md) when fallback is needed. Select a
supported voice and test a short reviewed passage before full generation. A provider
change invalidates chunk reuse for that category: regenerate its complete candidate
with Kokoro instead of stitching ElevenLabs and Kokoro chunks together. Preserve
the previous usable track until the replacement passes. Unaffected completed
categories remain intact, even if the playlist consequently has different voices.
Future updates reuse each category's actual profile unless the user requests a
change or the authorized fallback is needed again. Account reset/resume does not
automatically migrate Kokoro categories back to ElevenLabs.

## ElevenLabs anonymous website

Use available browser tools on the official [text-to-speech page](https://elevenlabs.io/text-to-speech).
Inspect the current UI instead of guessing selectors, request endpoints or limits.
Its [published guide](https://elevenlabs.io/blog/ai-generated-youtube-videos) describes
limited basic TTS without signup; this is distinct from its
[authenticated API](https://elevenlabs.io/docs/api-reference/authentication).
That documentation does not prove unlimited anonymous generation or unattended
full-course export. Verify those capabilities for the current session.

Select an educational/narration preset and inspect the custom-text generator.
Before a whole course, generate one short reviewed passage within the displayed
character limit. Confirm the output actually speaks that passage, not a stock
voice preview, and verify that the generated audio can be downloaded. Save the
sample and its settings under .build/ so it can become a reusable production chunk.
A play button or a marketing claim alone is not a successful generation test.

Use the visible download/export control or the browser tool's supported media
download capability. Configure/download into audio/.build/ where supported, moving
any browser-managed temporary file there immediately. Keep only reviewed narration
in the service; never upload raw course pages, personal records or credentials.

Split long scripts at semantic boundaries within the current per-request limit;
assemble chunks into one category file. Respect total usage limits as well as
request size. Record successful chunks immediately. Bound retries and inspect
the first useful error. A quota, login, payment or CAPTCHA gate is a real limit;
do not rotate identities/IPs, clear sessions, replay hidden endpoints or retry
unchanged failures to work around it. Do not create accounts or start subscriptions
as a side effect of audio generation. Never assume existing account credits are
free or spend them without authorization.

The ElevenLabs API is a separate route: use it only when credentials and permitted
usage/budget are already configured. Do not assume an anonymous demo authorizes
API access or existing paid credits. Other engines require an explicit selection;
this fallback policy authorizes Kokoro, not an open-ended chain of providers.

## Voice quality and continuity

Choose clarity and sustainable listening over dramatic expressiveness. Test
technical acronyms, unfamiliar names, numbers/negations and a dense explanation.
Use a short excerpt of the reviewed script that includes both plain explanation
and difficult wording. When listening tools are available, check intelligibility,
natural phrasing and thinking time; repair the excerpt or settings before full
synthesis. Do not choose a uniformly slow rate as a substitute for clear writing.
Reuse the course's pronunciation map; rewrite ambiguous input without changing
its meaning. Punctuation and explicit pauses should mark conceptual boundaries.
The same selected voice may sound different across providers/models; all relevant
settings and exposed versions belong in the chunk fingerprint.

Synthesize paragraph/sentence groups and preserve useful continuity context where
the engine supports it. Record that context in the cache key. Avoid tiny fragments
that sound disconnected and long requests that rush or truncate. Match loudness
and check joins after assembly. A file-size threshold is not proof of completion.
Never report a listening comparison, voice quality verdict or successful download
that was not actually checked with the available tools.
