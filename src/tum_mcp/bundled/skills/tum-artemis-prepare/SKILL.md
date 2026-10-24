---
name: tum-artemis-prepare
description: Read a released TUM Artemis programming exercise and prepare or reuse its local workspace. Use for assignment setup or download, not implementing a solution or submitting work.
---

1. Read `tum_status` and preferences; resolve the exact account, course, exercise,
   and graded/practice mode. Use `artemis_list_exercises` and
   `artemis_get_exercise`; do not enter exams or quizzes.
2. Inspect release/deadline, offline-IDE eligibility, and existing participation.
   Starting participation is a remote action. On `ACTION_REQUIRED`, explain the
   exact effect and the separate trusted local/manual start path.
3. Use `artemis_prepare_workspace` only when the user requests local preparation.
   It must preserve existing files, bind the workspace to this participation,
   and keep repository credentials outside model-visible output.
4. Report the statement source, workspace path, base revision, participation
   mode, and missing toolchain/Git capabilities. Do not execute downloaded code,
   install dependencies, implement a solution, commit, or push as part of setup.

Missing permissions/capabilities are supported limitations. Never scrape around
offline-IDE restrictions or overwrite an unrelated directory. Local implementation
requests belong to `tum-artemis-local-fix` after the workspace is confirmed.
