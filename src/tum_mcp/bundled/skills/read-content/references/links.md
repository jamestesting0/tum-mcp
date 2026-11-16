# Course link packets

## Selectors and limits

Give exactly one selector:

- `--item REF`: a typed item ref such as `study/unit/U/block/B`,
  `exercises/set/S/exercise/E`, `exam/concept/C`, `exam/pattern/P`,
  `exam/sitting/S/variant/V/question/Q`, `exam/mock/M/question/Q` or
  `lectures/lecture/L/section/N`.
- `--concept KEY`: a cheatsheet concept key, the same as `--item exam/concept/KEY`.
- a short free-text query, when no key is known.

`--purpose` names the workspace the answer needs (study, exercises, exam, lectures or
review). For teaching use `--limit 4 --max-bytes 8000`; the CLI defaults are 12 items
and 24,000 bytes. Retrieval stops at two hops, 256 nodes, 2,048 edges, 64 source
payloads and four lectures, so a packet never describes the whole curriculum.

## Packet fields

- `items`: for `--item` and `--concept`, the selected item comes first, then the items
  it links to in the requested workspace, then one home per other workspace. A query
  ranks the purpose workspace first.
- `paths`: how each item was reached. `origin` is `native` (authored in the course) or
  `lexical` (a shared defined term, navigation only). Follow the recorded direction:
  reverse navigation does not reverse a prerequisite.
- `evidence_status` and `usable_as_evidence`: only `current` items are evidence. Stale,
  unverified or unknown items are navigation. `locators` name the exact source, pages and
  `follow_up` command, or the recording time.
- `tags`: `role` (core or enrichment), `origin`, `solution_origin`, `relevance` of past
  papers, `classification` and `topic` (the semester map region).
- `gaps`: links the author recorded as not fitting, with the reason. A gap is a finding
  to report, not a missing result to search for.
- `status`: `ok`; `partial` (a limit or budget was reached: narrow the selector); or
  `empty`. After an empty or partial result, try at most one narrower selector, then use
  the native sources or state the gap.

## Impact packets

`study impact` lists `direct` items that cite the changed source and
`review_candidates` that build on them through authored links. `unmapped` means no
authored item cites the source; it does not mean the content is covered. Read the
changed pages before you change any content.

Keep released statements, official, student and authored solutions, synthetic practice,
outdated exams, uncertain recordings and optional Explore content distinct. Explore never
satisfies a core prerequisite.
