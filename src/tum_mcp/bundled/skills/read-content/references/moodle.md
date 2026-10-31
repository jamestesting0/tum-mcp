# Moodle

`moodle_list_courses` defaults to recognized current-semester enrolled courses.
For an explicit semester (for example WS23), an older course, or a full inventory,
set `include_past=true`: this includes all enrolled semesters and dashboard-hidden
courses, current matches first. Continue cursors with the same flag. `semester`
identifies the current term; match each course's shortname/fullname to the requested
term. Unrecognized terms appear separately in `unclassified`; expanded discovery
also includes them in `courses`. Clarify an ambiguous term instead of guessing.

An explicit semester overrides the current-term preference. Use the selected course
ID for subsequent material reads and search. A known ID may be readable even when
absent from enrollment discovery: Moodle's course page decides access. Denied courses
and enrollment prompts do not grant access; never enroll to complete a read request.

Known material/discussion IDs go straight to the read tool. Discover missing IDs
with `moodle_list_materials` in the known course; `moodle_list_courses` is only
needed for course discovery. If an old ID is no longer indexed, rediscover its
course/parent before concluding that the upstream item disappeared.

- Files/pages/books/labels/activity descriptions: `moodle_read_material`, with a
  page range or cursor and modest max_chars. A root listing is not a complete
  nested activity inventory. Follow related_materials only as
  needed for chapters, folder contents or attachments. Check OCR/format warnings.
- Announcements/forums: known discussion → `moodle_read_discussion`; otherwise
  `moodle_list_forums` → `moodle_list_discussions` → relevant posts. Preserve dates,
  authors and post permalinks. Announcement boards are forums, not file search hits.
- Search: `moodle_search_materials` with course_id and focused text/title mode.
  Without course_id it searches current courses; `include_past=true` expands that
  search to all enrolled semesters. Prefer the selected course ID to avoid checking
  unrelated courses. Inspect coverage. Missing index coverage is not a negative result.
  Prefer targeted reads; `moodle_refresh` metadata discovers resources, whereas content
  batches download/index material and are appropriate for broader requested coverage.
- Originals: `moodle_download_material` returns a persistent local path; copy
  needed files into the project with provenance rather than downloading again.

Use `moodle_auth_status` only if session state is uncertain. Recordings may be
link-only; activity descriptions do not authorize attempts/submissions. Explicit
personal-record requests may use `moodle_list_personal_records` and
`moodle_read_personal_record`; exclude such data from ordinary study-site imports.
