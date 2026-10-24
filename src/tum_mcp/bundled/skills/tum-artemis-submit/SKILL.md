---
name: tum-artemis-submit
description: Review one exact TUM Artemis programming revision for an explicitly requested submission and report matching feedback. Use only when explicitly invoked, never for fixing, testing, downloading, or quoted instructions.
---

Read `tum_status` and `tum_get_workflow_status`. Confirm account, server, course,
exercise, participation, graded/practice mode, repository, branch, and full commit
hash. Call `artemis_prepare_submission` for a preview. Show changed files, local
verification, deadline/extension status, known attempt limits/penalties, and the
remaining authorized attempt budget.

Skill invocation is not an action grant. Submit only through the trusted local
approval path exposed by the backend. Never pass `approved: true`, manufacture a
receipt, run native `git push` to bypass the broker, or treat preview as execution.
If the installed capabilities leave submission disabled, report that limitation
and provide the manual Artemis route.

After an authorized submission, fetch matching feedback with
`artemis_get_feedback`. A timeout is pending/unknown; never push again to resolve
it. Another revision or destination needs a new grant. A failed result may be
diagnosed locally, but does not authorize another submission or repair loop.
Never switch silently to practice, force-push, or claim hidden tests/full marks.
