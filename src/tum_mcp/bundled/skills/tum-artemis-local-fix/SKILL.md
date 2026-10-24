---
name: tum-artemis-local-fix
description: Implement or debug a confirmed TUM Artemis assignment workspace with local test evidence. Use when the assignment context is established, not unrelated Java debugging, read-only feedback explanation, or submission.
---

1. Confirm the workspace receipt using `tum_get_workflow_status`; resolve the
   exact exercise with `artemis_get_exercise`. Check the user's assistance mode
   and the stated course AI-use policy. Ask once before consequential automation
   if that policy remains unknown; do not infer a blanket ban or permission.
2. Inspect the statement, relevant files, and build/test recipes. Establish a
   baseline and distinguish pre-existing failures. If server feedback is needed,
   use the feedback procedure and require exact built-commit linkage.
3. Make focused local changes with the host's normal file tools. Run affected
   tests after minor edits and the full appropriate available suite at major
   milestones and before a proposed submission. Use the approved isolated recipe
   through `tum_run_tests` when available; do not pass credentials to tests.
4. Respect the configured repair budget (default three). Stop on repeated
   identical failure, missing dependencies, unreliable test signal, unexpected
   workspace changes, or unresolved permission. Dependency acquisition is a
   separate requested step.
5. Report the diff, test receipt, revision/fingerprint, skipped checks, and
   remaining limitations. Local edits/tests do not imply commit or submission.

Do not start participation, push, rebuild on the server, or change practice mode.
If the user requests submission, explain the explicit submission-skill route and
its separate trusted approval; never infer a remote-attempt budget from “fix it”.
