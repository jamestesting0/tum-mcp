# Composer: one change from the evidence

You have the baseline runs, the INV and DOM patches, one probe run of each, the blind
judgements and any human review (`rounds/<round>/human/<run>.md` and `.json`: notes plus the
passage comments left in the app). Compose one patch for confirmation.

Weigh the evidence:
0. Human review outranks the judge. Keep no edit that a human finding contradicts, and say
   for each open human comment whether the composed patch addresses it.
1. Each probe is one run. A single good or bad outcome is weak evidence either way.
2. An edit earns its place when a specific moment in a probe transcript or output shows it
   working. "Looks like good practice" is not evidence.
3. If a probe produced no project or no content, treat its edits as unsafe unless the rest of
   the evidence is overwhelming, and say why.
4. Merge INV and DOM edits when both earn their place; resolve overlaps instead of stacking.
5. Keeping the current skills is a valid outcome.

Output: the composed patch, plus one line per edit:
`kept|revised|dropped -> <edit> -> <transcript moment or metric, with counts>`.
