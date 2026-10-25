# Artemis

Choose the route needed; known IDs go directly to the read tool.

| Request | Route |
| --- | --- |
| Teaching content | `artemis_get_lecture`; use `artemis_list_lectures` only to discover lectures or inventory the course. |
| Student slides | `artemis_get_attachment` with needed page_start/page_limit. Set save_original=true only for a reusable local student copy. |
| Exercise statement | `artemis_get_exercise`; discover through `artemis_list_exercises` only when needed. |
| Own programming feedback | `artemis_get_feedback` with the exact full built commit and graded/practice mode from the user/record. |
| Course inventory | List both lectures and exercises. Teaching units include text, slides, video/online links and embedded exercise references. |

Use `artemis_list_courses` only for missing course metadata; discovery grants no
content access. Lecture start dates do not hide already released self-study units.
Preserve lecture/unit order and distinguish teaching from assignments.

Only student PDF variants are retrieved; never substitute staff originals.
Video links are not transcripts. Unsupported/external units are coverage gaps.
Exams, quizzes and unreleased exercises are outside these reads. Missing
participation is not permission to create one. Feedback needs its personal-read
scope; distinguish pending/withheld results from visible success, never hidden-test success.
