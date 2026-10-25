# Artemis reading

Use `artemis_list_courses` for missing course metadata, then the selected course
with `artemis_list_lectures` AND `artemis_list_exercises`. Discovery grants no content access. Read a known
released statement with `artemis_get_exercise`. Reuse IDs. Exams, quizzes and
unreleased exercises stay outside this reading workflow.

Artemis also hosts teaching content. Use `artemis_get_lecture` for text units,
slide attachment metadata, video/online links and embedded exercise references.
Keep lecture/unit order and distinguish teaching units from assignments. A future
lecture date does not mean that its already released self-study content is hidden.
Use `artemis_get_attachment` for cited PDF pages, following page_start/page_limit;
save_original=true saves the student copy locally for a study project. The
student endpoint excludes hidden slides. Never fetch a staff/original variant.
Video links are references, not proof that a recording was watched or transcribed.
External content and unsupported unit types are explicit gaps. Never mark a
lecture unit complete or start a quiz/exercise while reading it.

For programming feedback, obtain the exact full built commit and graded/practice
mode from the user or an existing record. Use `artemis_get_feedback` for that
linkage. Do not substitute the newest result. Distinguish compilation failure,
pending/withheld results and completed visible assessment. Hidden-test success
cannot be inferred from visible passes. Feedback is a personal read and needs
its existing local scope.

A missing participation is a retrieval gap. Do not create one. The integration
provides no exercise start, workspace preparation, code execution, deployment,
submission, push or rebuild workflow. Do not bypass it with native Git or browser
actions. Save a cited statement locally if the study request needs an exercise
reference; solving a practice question does not authorize upstream actions.
