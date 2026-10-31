---
name: course-memory
description: Set up and maintain optional private course memory for source-backed relationships across Study, Exercises, Exam and Lecture, including prerequisites, practice choices and changed-source impact. Use only when Course Memory is enabled; ordinary course authoring stays with its prepare skill.
---

This extension is disabled by default. `tum-mcp install course-memory` enables it;
`tum-mcp uninstall course-memory` stops its use and preserves course files. Check
`tum-mcp study status PROJECT`: when `course_memory` is false, do not read or use
retained graph files or packets. Old instructions and file presence are not activation.

On the next relationship, prerequisite, practice-choice or source-update request,
read [local course relationships](references/knowledge.md). Work only in the current
bound course. Use one narrow context packet and reuse it; simple facts need no graph.
The native workspace links are available immediately, even without extra annotations.
Do not build a whole-course graph before answering the student.

If private `.tum-mcp/knowledge.json` is absent (legacy `.study/`), initialize schema 1
using the exact course key and semester from state, with `concepts: []` and
`assertions: []`. Add only useful relationships for this request, checked against the
actual sources. Installation permits this bounded local memory setup and maintenance;
it does not authorize new campus reads, app edits, publication, model benchmarks or
recording processing. Read PDFs natively where supported; existing source helpers are
optional fallbacks. Never manufacture reviewed assertions from names or co-occurrence.

For existing or reinstalled memory, inspect a narrow context packet first. Malformed
or unsupported metadata needs explicit recovery; preserve it and continue teaching
from native sources without using that graph. Stale relationships remain inactive
until actual source/content review and explicit receipts make them current. Do not
copy a new fingerprint merely to pass validation.

After authorized source/content changes, run impact for changed keys, repair affected
owners and relationships, then the explicit knowledge report. Keep unrelated memory,
rejected history, unresolved candidates and intentional alias ambiguity. When the
course review report supplies `knowledge_revision`, copy that field along with its
native `revision` only after reviewing cross-workspace integration. The optional
binding is ignored when the extension is disabled; ordinary course review remains.

Use the student's stated goal, time and work shown to make a small source-backed
recommendation. Course coverage is not mastery. No learner profile, automatic chat
archive, background updater, cross-course graph or mandatory document pipeline exists.
Client reload or a new chat may be needed to remove instructions/context already read
before uninstall; new graph tool calls are blocked by the disabled capability.
