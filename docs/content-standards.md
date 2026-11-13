# Content standards

What every prepared page must meet, in one place. Each requirement names what enforces it:
an invariant flag holds readiness until fixed, a ruled flag must be ruled on by a fresh
checker, a review check is judged in review, and "skill" means the authoring skills teach
it without a mechanical check. A new flag or review check gets its row here; a unit test
fails while a flag has no row or a row names a check that no longer exists.

## Study

| ID | Requirement | Enforced by |
| --- | --- | --- |
| S1 | A rendered section never runs more than two authored paragraphs in a row; the rest is points, steps, an example, a table, a figure or a formula | `prose_run`, `long_section` |
| S2 | A paragraph holds one idea in a few sentences | `dense_paragraph`, `inline_list`, `inline_steps` |
| S3 | A worked case shows what is given, the working and the result (`example`, table or walkthrough), not a story | `example_in_prose`, `unworked_result`, `prose_calculation`, `compressed_working` |
| S4 | Each idea has the shape that fits it: comparisons as tables, procedures stepped, models drawn, parallel cases as tables or examples | `no_visual`, `static_trace`, `static_walkthrough`, `graph_as_table`, `trace_as_table`, `unstepped_table`, `slide_image`, `representation.shape_fits` |
| S5 | Objects the text names are shown, not described | `described_object`, `representation.shown_not_described` |
| S6 | Every symbol and formula is LaTeX, with words in math set as text | `plain_math`, `math_word` |
| S7 | Terms are defined before use and never redefined differently | `forward_term`, `definition_refined` |
| S8 | No narration of the source or the page | `meta_reference`, `clarity.no_meta` |
| S9 | Facts, values and citations match the cited pages | `arithmetic`, `citation_page`, `answer_key`, `correctness.source_match` |
| S10 | The unit covers its recorded outcomes | `thin_unit`, `unrecorded_sources`, `coverage.ledger_outcomes` |
| S11 | Sentences are the course's own, written from its sources; exemplars lend a shape, never text | `exemplar_copy` |
| S12 | Critical source demonstrations and teaching figures are considered in planning. Each selected example retains its inputs, representation, decisive working, endpoint and the comparison or result that makes its point through drafting and repairs; repeats that add nothing are left out. Useful continuations are allowed | the plan check (each one names its example), `repeated_example`, `coverage.examples_selected`, `correctness.source_match`, `redundancy.said_once` |
| S13 | Each step connects its own facts to its rule; calculations show original inputs and working, arguments show premises and inference. Repeated wording needs a ruling on whether the step's evidence is shown. Visible graph annotations retain the values the source shows | ruled `repeated_step_reason`, invariant `dropped_node_value`, `intuition.reasons` |
| S14 | Repeated content must add a distinct teaching purpose; a static copy of a walkthrough stage needs a reason. A lesson opens with enough context to orient the learner | `duplicate_stage`, `untitled_opening` |
| S15 | A staged explanation reveals every source element needed for its reasoning and distinguishes completed work from work stopped by a limit. For graphs, every stage node appears somewhere in the runs; a node stopped by a depth limit uses `cutoff`, not `visited`. A source shown whole stays whole; extraneous nodes are removed | invariant `never_shown_nodes`, skill |

## Practice (Study practice, Revision, guides, exam drills and mocks)

| ID | Requirement | Enforced by |
| --- | --- | --- |
| P1 | The stem is one clear question, answerable before reading the options | `clarity.one_reading` |
| P2 | Context appears only when it carries data the question needs, with real headers | `generic_table`, `text_only_question` |
| P3 | A visual idea gets a visual context, never a description of it | `representation.picture_carries_data` |
| P4 | Usually three or four options with one defensible key and parallel length and grammar | `key_longest` |
| P5 | Distractors come from real misconceptions | `practice.plausible_options` |
| P6 | No "all/none of the above", no unmarked negative stem | `all_of_above`, `negative_stem` |
| P7 | No word shared only by the stem and the key | `stem_key_overlap` |
| P8 | Feedback names the specific error of each option; the explanation appears once | `repeated_feedback` |
| P9 | One layout everywhere: prompt, context, options, Check, feedback, Explain | skill |

## Exercises

| ID | Requirement | Enforced by |
| --- | --- | --- |
| X1 | A released statement keeps its original wording and gives its givens; a part is titled with its number and its words appear once | `statement_framing`, `summary_repeats_objective`, `repeated_title` |
| X2 | Guides and solutions follow S1-S6 | `prose_run`, `plain_math` |
| X3 | The exercise links the Study passages, cheatsheet entries and patterns it uses (Recall) | `undecided_link` |

## Exam

| ID | Requirement | Enforced by |
| --- | --- | --- |
| E1 | Every pattern step that computes or applies a rule shows it under `apply` | `bare_workflow`, `redundant_workflow_detail` |
| E2 | Cheatsheet entries give procedures as steps and set mathematics as LaTeX | `method_without_steps`, `sheet_plain_math`, `sheet_dense_paragraph` |
| E3 | Practice is guided before it is unguided; every listed paper can be replayed | `unguided_practice`, `unreplayable_paper` |
| E4 | Cheatsheet entries link the lessons and exercises that teach and practise them | `undecided_link` |
| E5 | The cheatsheet has a semester map; every idea on it links what it builds on or contrasts with | `unlinked_map` |

## Lecture notes

| ID | Requirement | Enforced by |
| --- | --- | --- |
| L1 | A note stands alone for a student who skipped the lecture: setup, takeaway with condition, the lecturer's working or example, why it matters | `coverage.note_stands_alone` |
| L2 | A frame of the slide or board is attached when it carries the point, legible and never decorative | `coverage.note_stands_alone` |
| L3 | A note adds what the slides do not say and never narrates | `clarity.no_meta` |
| L4 | A note links the Study passage that teaches it | `undecided_link` |

## App text

| ID | Requirement | Enforced by |
| --- | --- | --- |
| U1 | No label, date or count is shown twice in one card or header; no line describes the page | skill |
| U2 | Lecture titles name the topic, never the date | lecture readiness |
