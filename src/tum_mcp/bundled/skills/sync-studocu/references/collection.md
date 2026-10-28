# Selection and collection

First identify the course ID using `studocu_search_courses`. Create a local JSON
selection file, then run `tum-mcp studocu plan PROJECT --selection FILE`:

```json
{"course_id":"123", "documents":[
  {"document_id":"42", "title":"Mock exam", "url":"https://www.studocu.com/de/document/42", "group":"exams", "document_type":"mock", "decision":"include", "reason":"Relevant mock exam"}
]}
```

Before including an exam, compare it with the local exams (`tum-mcp study
exam-report PROJECT`): if an official copy of that sitting is already stored, include
the Studocu document only for its solutions or annotations.

Use an empty `documents` list initially to establish the search scope, then call
`studocu_search_materials` to record course-scoped discovery evidence. Add reviewed
documents with `summaries`, `exams` or `other` group; `document_type` is `exam`,
`mock`, `solution`, `summary` or `other`. Use canonical Studocu document URLs,
not session URLs. Include `year`, `lecturer` and `language` when the source
actually supplies them. `tum-mcp studocu status PROJECT --json` resumes the queue.
Set `decision` to `include`, `exclude` or `review`, with a short `reason` for
each. Only included documents can be acquired. Repeated plans retain prior
decisions. To reclassify, update the group or source metadata in the selection and
plan again. Imported originals move only if unchanged and the destination is free.
When the provider's course title does not exactly match the project title, ask the
user to confirm the course and set `confirmed_course` to true only after confirmation.
To deliberately refresh an already imported document, set `refresh` to `true`
in its selection entry and plan again. The previous PDF is retained in private
version history if the newly selected original differs.

Exact same-year, same-type matches in one group share a retained original through
a private alias; each document keeps its own ID and citation. The inventory is
authoritative for resolving aliases, so do not make filesystem links or delete
the retained original. An alias inventory entry has no path; its `alias_of` is
the source key of the retained original. Use `studocu_get_document` with the
alias document ID so citations retain that document's URL. Reclassification or
refresh safely separates documents when they no longer match. Replanning a selection converts older unchanged
duplicate files; edited files remain for review.

Use `tum-mcp studocu import PROJECT --document-id ID --file FILE` for the file
the user chose. For MCP import instead, stage it with `tum-mcp studocu stage
PROJECT --document-id ID --file FILE`, then pass the returned basename to
`studocu_import_document`. Do not pair a saved file with a different ID. Report
the association as user-selected; verify visible document identity separately.
