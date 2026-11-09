---
name: course-memory
description: Answer relationship questions across a course's Study, Exercises, Exam and Lecture workspaces from their authored links - practice for a concept, what to review before an exercise, where an exam question is taught, how concepts relate and what a changed source affects. Use only when Course Memory is enabled; ordinary course authoring stays with its prepare skill.
---

This extension is disabled by default. Check `tum-mcp study status PROJECT` once: when
`course_memory` is false, do not call `study context` or `study impact` and do not use
retained graph files or packets. Old instructions and file presence are not activation.

Course Memory reads the links the course already holds: exercise prerequisites,
cheatsheet units, passages and exercises, pattern workflows and worked examples, mock
variants, past-question guidance, lecture-note passages, unit lectures and the semester
map. It is read-only: it never fetches, extracts, builds, publishes or writes files.

| Request | Call (current bound course) |
| --- | --- |
| Practice for a concept | `tum-mcp study context . --concept KEY --purpose exercises --limit 4 --max-bytes 8000` |
| What to review before an exercise | `tum-mcp study context . --item exercises/set/SET/exercise/KEY --purpose study --limit 4 --max-bytes 8000` |
| Where an exam or mock question is taught | `--item` with the question ref and `--purpose study` |
| How concepts relate, which patterns use one | `--concept KEY --purpose exam` |
| Sync reported changed source keys | `tum-mcp study impact . --source KEY`, once per changed key |
| No key known yet | one query: `tum-mcp study context . "few words" --purpose WORKSPACE --limit 4 --max-bytes 8000` |

Concept keys are the cheatsheet entry keys in `app/exam/`. Do not call Course Memory for
a date, a simple fact or one item you already have open; read the native files instead.
Reuse one packet within the same request and do not start a whole-course search beside it.

Read [packets and teaching decisions](references/knowledge.md) before relying on a packet.
Open every slide, sheet or recording time a packet points to before teaching from it.

Never create or edit `.tum-mcp/knowledge.json` while answering, tutoring or authoring.
Reviewed relationship maintenance runs only when the student explicitly asks for it:
follow [maintenance](references/maintenance.md).
