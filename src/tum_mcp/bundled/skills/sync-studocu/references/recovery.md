# Recovery

Inspect the saved queue and project state before retrying. Preserve local edits,
original files and previous receipts. Resolve a mismatched course, changed group,
invalid PDF or modified file deliberately; never silently overwrite or relabel it.
Do not infer completeness from a limited search or treat an interrupted browser
download as a successful import. Continue only with remaining selected documents.
Status records a staged filename, so an interrupted import can resume with that
file instead of downloading again. A validation timeout leaves the original staged
with validation pending; review the limit before retrying import. For a browser action with an unavailable or
uncertain outcome, record it with `tum-mcp studocu mark PROJECT --document-id ID
--state unavailable` or `--state outcome_unknown`; review before marking it
`pending` and retrying.
