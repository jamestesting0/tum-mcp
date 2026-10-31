# Artemis

Choose the route needed; known IDs go directly to the read tool.

| Request | Route |
| --- | --- |
| Teaching content | `artemis_get_lecture`; use `artemis_list_lectures` only to discover lectures or inventory the course. |
| Student slides | `artemis_get_attachment` with needed page_start/page_limit. Set save_original=true only for a reusable local student copy. |
| Exercise statement | `artemis_get_exercise`; discover through `artemis_list_exercises` only when needed. |
| Own programming feedback | `artemis_get_feedback` with the exact full built commit and graded/practice mode from the user/record. |
| Course inventory | List both lectures and exercises. Teaching units include text, slides, video/online links and embedded exercise references. |

Use `artemis_list_courses` only for missing course metadata. By default it reads only
the active-course listing. For an explicit semester (for example WS23), an older
course, or a full inventory, set `include_past=true` to add the past-course listing,
active first with duplicate IDs removed. Match both title and requested semester;
never replace a requested past offering with a current one of the same name.
The `active` flag identifies the listing; past courses retain their `semester` label
when supplied by Artemis. An active course is not necessarily from the current semester:
match Moodle metadata or the course handbook when needed, rather than fetching every exercise.
For an explicitly requested older course, use its ID with the same lecture, attachment
and exercise tools. Known accessible IDs need not appear in either listing. If the server
denies access or no longer retains the content, report the restriction or missing source.
Server permissions determine access. Lecture start dates do not hide released self-study units.
Preserve lecture/unit order and distinguish teaching from assignments.

Only student PDF variants are retrieved; never substitute staff originals.
Video links are not transcripts. Unsupported/external units are coverage gaps.
Exams, quizzes and unreleased exercises are outside these reads. Missing
participation is not permission to create one. Existing own participation and visible feedback
need no extra local grant; distinguish pending/withheld results from visible success,
never hidden-test success.
