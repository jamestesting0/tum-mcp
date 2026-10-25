# Moodle

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
  Inspect coverage. Missing index coverage is not a negative result. Prefer
  targeted reads; `moodle_refresh` metadata discovers resources, whereas content
  batches download/index material and are appropriate for broader requested coverage.
- Originals: `moodle_download_material` returns a persistent local path; copy
  needed files into the project with provenance rather than downloading again.

Use `moodle_auth_status` only if session state is uncertain. Recordings may be
link-only; activity descriptions do not authorize attempts/submissions. Explicit
personal-record requests may use `moodle_list_personal_records` and
`moodle_read_personal_record`; exclude such data from ordinary study-site imports.
