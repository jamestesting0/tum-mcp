# Teaching through sound

Aim for the shortest self-contained explanation that preserves the prepared
learning objectives and distinct ideas. Adapt for a listener without a screen;
do not turn every website block into its own spoken paragraph. An unclear or
contradictory source needs a reported content issue, not a guessed correction.
Do not add new subject-matter claims, invented examples or exercises.

## Plan meaning, then write speech

Outline the affected category before drafting. Collect its definitions, mechanisms,
worked examples, comparisons and conditions, including distinct teaching in correct
practice feedback. Merge duplicates across blocks, cards and questions. Several
source locators can map to one explanation; preserve any detail that changes the
reasoning, result or applicability. Keep prerequisites and the prepared topic order.

A useful default is a plain definition, an existing concrete example, the important
qualification and a brief recall or comparison. Adapt that order to the concept;
do not force four paragraphs or equal-length sections for every topic. Give a hard
derivation more room than a simple definition. Define exact course terminology
before relying on it, and use a familiar phrase alongside it when helpful.

Reuse an existing example across related ideas when it already supports them.
Introduce components as they act in a diagram or execution trace, instead of
listing every label upfront and then listing them again during the walkthrough.
Keep each necessary step, relationship and outcome explicit.

## Make each sentence earn its place

Prefer short active sentences with one main idea and unambiguous referents. Each
paragraph should define, explain a mechanism, apply an example, distinguish ideas
or preserve a necessary condition. Merge or cut paragraphs that only restate work
already done. Announce meaningful transitions without narrating the production
process. Say "For example" rather than "The prepared website's authored example";
keep provenance, lecture references and editorial qualifications in SOURCES.md.
Preserve a source qualification when it affects the subject matter itself.

Repeat an idea when the repetition does new work: applying it, contrasting it or
asking the listener to recall it. Avoid repeated definitions, a second example
with the same teaching purpose, and full re-explanations inside the recap. A recap
should recover the central relationship or decision rule in a few sentences.
State an important caveat clearly where it matters, using the source's example
when needed; do not surround it with several equivalent warnings.

For instance, a long ownership discussion can say: "The Composite pattern does
not determine ownership. UML composition can fit when a whole exclusively owns a
part and controls its lifetime. Shared or independently existing parts may need
aggregation. If two pictures share a Line that must survive deleting either
picture, neither picture can exclusively own it." This illustrates compression
with conditions intact; use only a course's own concepts and examples in its audio.

Do not impose a percentage reduction, equal chapter lengths or a duration cap.
After cutting repetition, check that the listener can still follow the reasoning.
Estimate listening time from script words and the actual course voice. Around
130–150 spoken words/minute is a starting point, not a comprehension test. Shape
dense reasoning with phrasing and local pauses; avoid uniformly stretching speech
or increasing speed to compensate for a verbose script. Spell out ambiguous
symbols/acronyms for synthesis and maintain their pronunciation map in voice.json.

## Adapt each content type

| Prepared content | Spoken adaptation |
| --- | --- |
| Bullets | Explain the relationship between items; label steps and distinguish independent cases. |
| Comparison table | Name the shared comparison criterion, then explain how each concept differs under it. |
| Inline LaTeX | Interpret the expression in `\( ... \)` as mathematical meaning; speak the variable or relationship naturally, never delimiters or backslash commands. |
| Formula | Explain the purpose, symbols and conditions, state the expression unambiguously, then follow any existing worked example. |
| Code | Name the inputs and state, follow the relevant operations/branches and explain the result using the prepared example. Avoid long punctuation readings. |
| Diagram | Establish the starting state and edge meanings; introduce components as needed while walking through frames in order. Replace "here/above/this arrow" with explicit names. |
| Flashcard/practice | Select existing prompts that check a central distinction; leave a thinking pause, then explain the answer. Consolidate duplicate feedback and label any misconception discussed. |

Retain the source's exact relationships, qualifications, numeric results and
logical direction. Verify that verbalizing a formula has not reversed an
inequality or lost a negation. Explain the reasoning behind a code transformation;
refer listeners to the corresponding prepared section for exact syntax when
necessary. Audio can explain a construction without proving the listener can
independently perform it. Disclose a genuine visual/practical dependency instead
of claiming audio-only mastery or silently reducing coverage.

Use one consistent tutor narrator by default. Skip background music, theatrical
dialogue, sound effects and voice switching unless requested. Where the prepared
content offers useful recall prompts, place a few after the relevant teaching,
rather than immediately restating the answer as another lecture paragraph. A
roughly 3–5 second thinking pause is a starting setting to test, not an evidence-based
optimum. Record it as intentional silence in synthesis/chapter inputs. Continue
with the correct answer automatically; require no speaking, tapping or screen use.
Do not imply that background listening proves recall or practical competence.

Keep raw URLs, citations, Markdown, production notes and metadata out of spoken
text. Store titles and chapter markers separately; headings that should be heard
must be written as natural spoken transitions. If a service supports speech tags,
separate its synthesis input from the plain narration and record both fingerprints.

## Teaching check before synthesis

Review the complete affected script as continuous speech, then repair failures:

- Coverage: map each distinct source idea and objective to an explanation, including
  required steps, conditions and outcomes. Naming a concept is insufficient.
- Fidelity: trace every technical claim back to prepared content; check negations,
  ownership, logical direction and other conditions that compression could lose.
- Listenability: terms and referents are introduced in time, transitions are clear,
  and spoken explanations stand alone. Any remaining visual/practical dependency
  is disclosed and reflected in coverage.
- Concision: each section has a teaching purpose; repeated framing, duplicate
  examples and recaps that repeat the lesson have been removed or justified.
- Recall: any selected source question has a deliberate pause and an automatic
  correct answer; the prompt and lead-in do not give away the answer before the pause.

Recheck repaired sections and their dependencies before handing text to synthesis.
Record a brief review with the script and guidance fingerprints as described in
[workflow and coverage](workflow.md). Check audio delivery separately after
generation. A passed script review, transcript match or signal check does not
prove learning effectiveness or an auditioned voice. Report content gaps back to
prepare-study; do not expand the syllabus during conversion.
