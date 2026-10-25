# Regression lookup

Read rows relevant to changed behavior or a failure. For an unmodified bundled
renderer, reuse known checks and verify new course content; do not repeat this
whole matrix for each unit. These failure modes remain part of the design contract.

| Area / prior failure | Check |
| --- | --- |
| Mobile unit opens midway down | Scroll to end, navigate to another unit; its beginning is visible. Cover phone document scroll and desktop main-pane scroll. |
| Tabs point to nonexistent panels | All aria-controls targets exist, including inactive panels; one panel shown; arrow/Home/End keys select/focus correctly. |
| Skip link resets route | From a nonfirst unit/view, skip to main without changing unit/view. |
| Replacement loses focus | Next/previous/retry focuses the new prompt/legend. Focus mode keeps navigation; Escape restores its outline/control. |
| Theme flash / color-only instructions | Colors switch immediately. Captions use active/highlighted/state descriptions, not dark/green; meaning survives either theme. |
| Wide content overflows | No page-wide horizontal scroll. Table/formula/code/diagram regions scroll by keyboard; labels and notation stay legible at narrow widths/zoom. |
| Long names stretch outlines | Stress course AND unit titles with unbroken identifiers. Inspect sidebar and mobile summary as well as main content. |
| Hidden storage failure | Block storage, rate/answer; memory-only study works and its warning is visible outside closed settings, also on mobile. |
| Unrelated change resets progress | Adding a binding preserves course namespace; unchanged units retain progress on reload. Revised units get separate answers; reset leaves other courses intact. |
| Answer leaks / early advance | Card front hides answer/sources/ratings. Feedback remains after checking; next is explicit; retry clears attempt and restores focus. |
| Plausible wrong trace | Independently compute ordering, frontier, discovery versus processing and directed endpoints. First/last controls are bounded; no autoplay. |
| Valid key, invalid teaching | Verify every changed option/assumption; compare prose, formulas, tables and cards. Repair ambiguity rather than force an answer. |
| Update destroys edits / hides stale material | In a disposable copy, change source/template; sync/build preserves/reports edits and rejects affected stale units. Review before rebinding hashes. |
| Distracting admin copy | Visible text serves study/navigation. Coverage details are concise disclosures; storage errors conditional; no duplicated labels, banners or boilerplate tips. |
| Screenshot masks broken behavior | Observe keyboard, feedback, persistence and navigation on the actual app, plus console/asset errors; a successful click is insufficient. |
| QA dominates implementation | Reuse renderer, data-derived selectors and input-stamped evidence. Avoid question × viewport × theme multiplication and recapturing unchanged cases. |
