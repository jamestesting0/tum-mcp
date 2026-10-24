# Feedback and submission preview

For feedback, confirm participation/mode and the full built commit from the
workspace or user. Call `artemis_get_feedback` for that exact linkage; never
substitute the latest result. Distinguish compilation/test failure, pending or
withheld results and completed visible assessment. On `STALE_RESULT`, obtain the
correct revision before diagnosing. Cite matched result/statement sources and
participation/submission IDs. Visible passes do not prove hidden-test success.

For an explicitly requested submission review, use `tum_get_workflow_status`
and `artemis_prepare_submission`. Confirm the repository, branch, full revision,
mode, changed files, local verification and deadline/attempt constraints. A
preview has no remote effect. This release cannot submit; provide the manual
Artemis route. Never fabricate `approved: true`, a grant or a receipt.
A pending/unknown result is not a reason to repeat a push or attempt. Another
revision does not inherit authorization from an earlier request.
