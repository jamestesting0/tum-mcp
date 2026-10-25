# Source-linked content and local build

Read `tum-mcp study schema content` for the exact schema. The bundled
assets/example/content.json is a complete synthetic example; its companion
snapshot supplies matching source hashes. `tum-mcp study demo PROJECT` creates
that example locally for style review without campus access.

The agent writes study/content.json. Top-level fields: schema_version=1,
course_key, organization (lectures/weeks/topics), introduction, units. Each unit
has a stable key, label, title, summary, estimated minutes, objectives, sources,
blocks, flashcards and questions. Keep IDs stable while meaning stays stable.
Unit sources contain the resource key and the exact SHA-256 from current study
state. Each content/card/question citation names one of those sources.

Blocks:
- text: title, paragraphs and/or points, sources.
- formula: title, safe MathML, plain-language equivalent, symbol/meaning pairs,
  conditions, sources. The native math namespace is required. Scripts, links,
  style/event attributes and foreign XML are rejected. Keep a readable text form.
- table: title, columns, rectangular rows, caption, sources.
- code: title, language, code, explanation, sources. Render as literal text; never execute it. Label authored examples and explain their purpose.
- diagram: title, description, positioned nodes, edges and frames, sources.
  Nodes use key/label/x/y in a 600×320 viewBox. Use shape=box for labels longer than four characters; keep box centers within x=70–530. Edges name start/end node keys, optional directed=true and a short label.
  Each frame has a caption, active nodes, frontier order and visited (seen) nodes.
  Use meaningful steps and explain the state. Use state_labels=caption for concept/call-flow diagrams without frontier/visited semantics. Do not autoplay.

Flashcards have key, objective, front, back, sources. A question has key,
objective, prompt, level (recall/apply/reason), three to five distinct options,
one correct option key, explanation and sources. Each option supplies its own
feedback. Every declared objective needs a practice question. This structural
check does not establish that an answer or distractor is pedagogically correct;
the author must check those against source passages.

Run `tum-mcp study build PROJECT`. A different course, changed source hash,
withdrawn/conflicted source, edited generated data or invalid content stops the
build. Fix the affected units instead of copying new hashes onto old explanations.
Unchanged units can retain their data. A changed unit revision gets separate
learner progress, so stale answers are not counted after a content change.

The renderer and generated data are separate. Build keeps user-edited templates
and reports their names; it does not overwrite them. Edited data.mjs requires
review because content.json is the authoritative input. Unknown files are kept.
Use the shared CSS tokens and renderer functions when extending the site. Add
new block types only with schema validation, safe rendering and accessible text.

Preview: `tum-mcp study serve PROJECT --port 8765`. It binds 127.0.0.1 and serves
only study/, with no directory listing or symlink escape. No external CDN,
analytics, remote model or campus credential is needed by the study website.
