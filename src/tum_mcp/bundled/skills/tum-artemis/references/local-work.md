# Workspace and local work

Read the statement, release/deadline, offline-IDE eligibility and existing
participation. A statement read does not require workspace preparation.
Use `artemis_prepare_workspace` only when local setup is requested; preserve
unrelated work. On `ACTION_REQUIRED`, explain the missing participation/manual
step rather than starting it. Report the workspace, base revision and mode.

For implementation or repair, confirm the receipt with `tum_get_workflow_status`
and inspect the relevant files and available test recipes. Respect the user's
assistance mode and course AI-use policy; ask once when a consequential action
needs a choice that remains unknown. Do not invent a blanket ban or permission.
Establish a test baseline, make focused edits, and run affected tests; run the
full appropriate available suite at a major milestone or submission preview.
Use `tum_run_tests` for an approved isolated recipe. Dependency acquisition is a
separate requested step; never expose credentials to tests.

Respect the configured repair budget (default three). Stop on an identical
repeated failure, unreliable test signal, missing dependencies or unexpected
workspace changes. Report changed files, verification receipt/fingerprint and
remaining checks. Local editing/testing does not authorize commit or remote work.
