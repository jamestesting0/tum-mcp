# Reflector: the ledger entry

Write the round's decision file for `lab ledger add`. It enters the tracked ledger, so write in
general terms: no course text, quotes, names, links, local paths or personal data.

Sections, in this order:

## Weakness
One sentence and the signal that picked it (metrics, judge, or human review).

## Edits
One row per changed file: what changed, the observed difference, and a verdict:
`helped`, `hurt`, `no observed effect` or `confounded`. Use `confounded` whenever several files
changed together or one run is all there is. The judge compared outputs with the variants
hidden, so its pick says which output read best, not which edit worked.

## Lesson
At most one: cue (the shape of situation it applies to), lesson (an operation on a named skill
file or check), evidence (the row it rests on), confidence, and the models it was observed on.
Write "No lesson" when the rows do not support one.

## Decision
Shipped, revised or dropped, and why. Name the commit once it ships.
