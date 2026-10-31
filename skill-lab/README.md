# Skill lab

Dev-only tooling that improves the bundled skills (`src/tum_mcp/bundled/skills/`) from
simulated student runs. It lives in this repository and is never part of the npm package or
the Python wheel. Method inspired by google-research/harness2 (Apache-2.0); prompts are
paraphrased.

A trial is a simulated student: a connected TUM account, an empty folder and a scenario of
student messages. The agent (Claude Code or Codex) discovers the course itself, sets up its
own course project with sync-course, then builds and reviews content with the skills of one
**variant** (this repo at a base commit plus a candidate patch). A round compares variants on
the same scenario, judges the outputs blind and records what each change did.

`lab` below means `uv run skill-lab/lab.py`, run from the repository root.

## One-time setup (human)

```sh
tum-mcp login          # be a connected student; repeat when the session expires
tum-mcp doctor

lab profile create     # prints one login command per host
CLAUDE_CONFIG_DIR="$PWD/.omo/skill-lab/profiles/claude/config" claude auth login
HOME="$PWD/.omo/skill-lab/profiles/codex/home" codex login
lab profile check      # host login, models, live campus state (no secrets printed)
```

Claude gets its own config folder (`CLAUDE_CONFIG_DIR`; macOS keeps its login in your
keychain under a separate entry) and Codex its own HOME, both under `.omo/skill-lab/profiles/`.
Your real `~/.claude`, `~/.codex`, their session lists and `~/Downloads/TUM Moodle` stay
untouched. Codex fills its model list after its first run in the profile.

Every run first checks the campus connection live and refuses to start unless Moodle is
Ready; a run whose Moodle session expires midway stops as `campus-session-expired`. Run
`tum-mcp login` and select Moodle, then repeat the run.

## A round

A round judges candidate skills against a **baseline**: runs that already exist, normally the
previous round's result. Nothing is rerun to get it. Only the very first round runs a baseline.

```sh
lab models --host claude
lab models --host codex

# First round only: run the current skills once per author; these runs become the baseline.
lab round new r0 --fresh --scenario course-workspaces --author claude \
  --matrix codex:gpt-6.1-terra:xhigh --judge codex:gpt-6.1-sol:xhigh --reason "first baseline"
lab variant r0 base
lab run r0 --variant base --all-authors     # Claude and Codex at once

# Every later round: --from takes the previous round's newest completed run per author as
# the baseline (or name them with --baseline ROUND/RUN, or later with `lab baseline`).
lab round new r1 --from r0 --scenario course-workspaces --author claude \
  --matrix codex:gpt-6.1-terra:xhigh --judge codex:gpt-6.1-sol:xhigh --reason "headings"
lab variant r1 candidate --patch .omo/skill-lab/rounds/r1/candidate.patch
lab run r1 --variant candidate --all-authors
lab collect r1
lab judge r1          # each baseline against the newest candidate run by the same author
lab review r1 --run candidate-1   # a workspace only the candidate built gets a single review

# your review of a run: leave passage comments in its app, then add overall notes
lab human r1 --run candidate-1 --note "Exercise guides now read per part."

# write the decision with prompts/reflect.md
lab ledger add r1 --decision .omo/skill-lab/rounds/r1/decision.md
lab round status r1
lab clean --keep 3
```

Rounds run one after another. Within a round, `--all-authors` runs the round's author and
its `--matrix` authors at once, one trial per host. The judge pairs runs by author model only:
a baseline and a candidate compare when the same host, model and effort wrote them. Their
scenarios may differ. The judge then sees only the workspaces both built and the
materials either read; `unjudged` names a workspace only one built, and `same_materials`
says whether both read the same files. A candidate's new workspace is judged by `lab review`.

To compare several candidate patches in one round (INV and DOM from `prompts/`), create one
variant per patch, run each, then `lab judge r1 --pairs r0/base-1:inv-1 r0/base-1:dom-1`.
Compose the winners with `prompts/compose.md` into `composed`, run it, and keep it only if
`lab judge r1 --confirm` (both confirmation judges) prefers it.

Human review outranks the judge. `lab human` stores your notes in
`.omo/skill-lab/rounds/<round>/human/<run>.md` and collects the passage comments you left in
that run's app (`.tum-mcp/comments.json`). The change writers read it first, and the composer
keeps no edit a human finding contradicts. The blind judge never sees it, so its verdict stays
independent. To look at a run's app:

```sh
.omo/skill-lab/rounds/r1/variants/base/venv/bin/python -I -m tum_mcp study serve \
  ~/.skill-lab/workspaces/r1/base-1 --port 8811
```

Models are `host:model:effort`; a bare `claude` or `codex` means that host's default author,
`claude:opus:medium` or `codex:gpt-6.1-terra:xhigh`. Claude takes an alias (`opus`, `sonnet`, `haiku`, `fable`)
or a `claude-*` name with `low|medium|high|xhigh|max`; Codex takes a model from its list with
a supported effort. Judges default to `claude:claude-opus-5-5:xhigh` and
`codex:gpt-6.1-sol:xhigh` for confirmation; `ultra` is refused for judging. A baseline and
its candidates compare only within one host, model and effort; `--author` on `lab run` starts
another comparison group. A run whose host reports a different model is marked
`invalid-model`.

## Boundaries

- Campus access is read-only. A filter in front of the TUM server hides and refuses
  `tum_logout`, `tum_connect`, `moodle_login`, `moodle_logout`, `moodle_clear_cache`,
  `zulip_save_checkpoint` and any tool marked destructive. The trial's `tum-mcp` command
  refuses `login`, `logout`, `setup`, `install`, `uninstall`, `update`, `manage`, `serve` and
  `study publish`.
- Claude trials cannot use web tools, `git push`, `gh`, `curl`, `wget` or `npm publish`.
  Codex trials run in the workspace-write sandbox without shell network; the TUM server runs
  outside the shell sandbox.
- Variants may change skills and study-side code, never campus, session, install or lab code.
- One live trial per host: a trial installs its variant into, and clears the logs of, its host's
  profile. A Claude and a Codex trial run side by side. Downloads go to a folder per run.
- Each run's workspace lives outside this repository, in `~/.skill-lab/workspaces/`
  (linked from the run folder), so the trial agent never reads this repo's `AGENTS.md`.
- After the last turn the lab keeps only redacted transcripts: TUMonline, Zulip, personal
  records, forum reads and feedback become byte counts and hashes. A credential scan
  quarantines a run on any hit. Raw host session logs in the profile are deleted.
- Everything real stays in the gitignored `.omo/skill-lab/`. CI only runs the synthetic tests
  in `skill-lab/tests/`; it never logs in, reads campus or runs a trial.

## Layout

| Path | Purpose |
| --- | --- |
| `lab.py`, `skill_lab/` | the command line and its modules |
| `prompts/` | change writers (INV, DOM), composer, reflector, judge |
| `scenarios/` | generic student scenarios; local overrides in `.omo/skill-lab/scenarios/` |
| `ledger.md` | sanitized round entries |
| `tests/` | synthetic-fixture tests |
