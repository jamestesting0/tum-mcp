# Reviewed relationship maintenance

Use this only when the student explicitly asks to record or review relationships that
the course's native links cannot express. Answering, tutoring and authoring never create
or edit `.tum-mcp/knowledge.json`.

## The registry

The optional private `.tum-mcp/knowledge.json` follows `tum-mcp study schema knowledge`:
course and semester, concepts and assertions. Do not copy course content into it. Prefer
cheatsheet concept keys; a registry concept with the same key names the same idea. Use
stable typed item refs; shared aliases stay ambiguous. Relations are teaches, practices,
assesses, clarifies, prerequisite_of and contrasts. Prerequisites point from foundation
to dependent. Add only useful, source-supported relations.

## Review an assertion

1. Finish the authorized content changes and settle item ids and source references.
2. Add the needed assertions for that scope together as `candidate` with
   `revision: null`. Each support group is conjunctive; separate groups are independent
   alternatives, not votes. Timed support needs reviewed, resolved evidence from the
   right recording.
3. Read the actual evidence and check meaning and conditions.
4. Run `tum-mcp study report . --section knowledge`. It reports `expected_revision` and
   `ready_for_review` and never approves anything. Resolve invalid roles, missing refs
   and prerequisite cycles first.
5. Only after that source review, set `review.status` to `reviewed` and copy the matching
   expected revision. A matching hash records an authorship decision, not a factual
   review.
6. Run the report again, then the existing item and course review gates.

Further relevant edits or failed checks need another actual review, never a copied fresh
hash.

## After a source refresh

Run `tum-mcp study impact . --source KEY` only for changed, added or withdrawn keys.
`unmapped` means no authored dependents, not already covered; incomplete inventory is not
proof of withdrawal. Read the changed evidence, fix authored content and coverage first,
then revise and re-review the affected assertions. An independent support alternative
may keep a relation but cannot repair stale owning content. Never rebind hashes to make
checks green. Retire obsolete assertions as `rejected` with `revision: null`; keep
unresolved candidates, homonyms and qualified alternatives inactive.

## Reports and review binding

The explicit knowledge report audits everything, including inactive records; context and
impact are bounded. Ordinary structure and review reports verify reviewed dependencies
without diagnosing candidates. Reviewed changes stale the course review's optional
`knowledge_revision` binding without changing its native `revision` or student
progress; save both fields after reviewing the integration. The binding is ignored while
Course Memory is disabled, and candidate- or rejected-only registries need none. Build,
sync and publication never read the registry; registry, packets and private notes never
enter app assets or published sites. Do not erase history or findings to get a clean
report.
