# Moodle reading

Moodle covers more than lecture files. `moodle_list_materials` discovers course
sections, labels, pages, books, links, exercises and activities. Reuse the exact
course ID. Use `moodle_list_courses` only when that ID is missing.

For announcements or discussion, use `moodle_list_forums`, then
`moodle_list_discussions` and `moodle_read_discussion`. Follow their cursors.
Announcement boards are forums. Keep post authors, dates and permalinks. Do not
assume a course has no updates because a file-title search found nothing.

Search `moodle_search_materials` within the course. Inspect its coverage. Use
`moodle_refresh` in metadata/content batches when the index lacks relevant
material. Read decisive passages with `moodle_read_material`; reuse page cursors
instead of repeating ranges. Pages, course labels, activity descriptions and
forum attachments can contain exam rules or study information. Activity access
does not authorize an attempt or submission.

Use `moodle_download_material` for requested reusable originals. It returns a
local path. Copy an original into the study project only when needed and retain
its provenance. A recording/player link is not a transcript. Some interactive
resources expose only a link or description; say what you could actually read.

Check `moodle_auth_status` when needed. For explicitly requested personal study
records, `moodle_list_personal_records` and `moodle_read_personal_record` provide
bounded reads. Keep the user's course and semester scope. Do not bulk-import
private conversations, grades or submissions into a study site.
