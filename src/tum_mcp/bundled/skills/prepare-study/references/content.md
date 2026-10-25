# Content and build contract

Edit study/content.json. Preserve unaffected unit objects and stable IDs. Build
copies the renderer; ordinary content edits need no HTML/CSS/JS asset inspection.
For unfamiliar fields or validation failures, redirect `tum-mcp study schema content`
to a private file and inspect needed definitions. The bundled example is a format
reference: inspect one relevant object, not the entire course or asset tree.
`tum-mcp study demo PROJECT` is only for an explicitly requested synthetic demo.

Top level: schema_version=1, course_key, organization=lectures/weeks/topics,
introduction, units. Units carry key/label/title/summary/minutes, objectives,
sources, blocks, flashcards and questions. Sources pair a resource key with its
exact current SHA-256 from state; citations use those declared keys.

| Block | Specific requirements |
| --- | --- |
| text | paragraphs and/or points, never an empty explanation. |
| formula | Native safe MathML, plain equivalent, symbol definitions and conditions. Keep the math namespace; no script, links, events, styles or foreign XML. |
| table | Column labels, rectangular rows and a meaningful caption. |
| code | Language, literal code and explanation; label authored examples. Do not execute downloaded code. |
| diagram | Positioned nodes/edges/frames in 600×320. Long labels need shape=box, centers x=70–530. Optional directed edges/labels. state_labels=caption omits traversal bookkeeping for concept diagrams. Self-loops require an extension. |

Every block has a title and sources. Frames name active/frontier/visited node
keys; visited is shown as seen, not necessarily finished. Flashcards use one
objective plus front/back/sources. Questions use an objective, prompt, level,
3–5 distinct options with individual feedback, one correct key, explanation and
sources. Every objective needs a question; counts follow learning needs, not quotas.

Run `tum-mcp study build PROJECT` after a coherent batch. It blocks stale or
conflicted sources and edited generated data.mjs. Review source meaning/locators
before rebinding hashes; byte changes alone need not require rewriting valid teaching.
A modified unit gets a new revision/progress namespace. Unchanged units retain theirs.

Build preserves edited templates and reports them. Verify their compatibility;
unknown files remain untouched. Add block types only with schema, safe rendering
and accessible fallback. Do not change renderer code to bypass invalid content.

Preview: `tum-mcp study serve PROJECT --port 0` prints an available loopback URL.
It serves only study/; the app needs no campus credentials or external services.
