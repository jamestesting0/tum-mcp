# Workflow, records and recovery

## Layout

```text
videos/
  plan.json, manifest.json, style.json, voice.json   records (manifest = verified)
  README.md, COVERAGE.md, SOURCES.md, playlist.m3u    generated; your text outside
                                                      the managed markers is kept
  storyboards/STEM.json    you write; storyboard check validates
  scenes/STEM/chapters.py  you write
  assets/                  optional SVG files you provide
  narration/STEM.txt       published transcript (check writes a working copy in .build)
  tracks/ captions/ chapters/ posters/                published by publish
  reviews/                 teaching and coverage reviews you pass in
  .build/                  audio, timing, runs, caches (not published)
  archive/                 superseded published files
```

Stems look like `03_follow-the-frontier` and never change once planned. If `videos/`
already holds files Video Notes did not create, every write stops; ask the user to
move them. Never delete user files.

## Commands

All take the course project folder and print JSON.

| Step | Command |
| --- | --- |
| State | `inspect PROJECT [--video STEM] [--verify]` |
| Locators | `unit PROJECT UNIT` |
| Select | `plan PROJECT --selection FILE` |
| Validate | `storyboard check PROJECT STEM` |
| Audio list | `narration PROJECT STEM --profile KEY` |
| Timing | `timing PROJECT STEM --profile KEY` or `--silent` |
| Render | `render PROJECT STEM --draft|--final [--jobs N] [--max-minutes M] [--run RUN]` |
| Look | `frames PROJECT STEM --run RUN --at 12.5,40` |
| Recheck | `check PROJECT STEM --run RUN` |
| Publish | `publish PROJECT STEM --run RUN --teaching-review FILE --visual-review performed|not-performed` |
| Keep after edit | `acknowledge PROJECT STEM --review FILE` |
| Clean | `prune PROJECT [--keep N]` |
| Runtime | `runtime status`, `runtime install` |

Prefix each with `tum-mcp video-notes`. `schema NAME` prints the storyboard,
selection, style, voice, manifest and timing contracts.

## Rendering

`render` needs the runtime (`runtime status`; install it once with `runtime
install`, which reports exact prerequisite commands such as `brew install cairo` and
never runs them). If your sandbox blocks the install, ask the user to run it in their
terminal. A run lints `chapters.py`, renders chapters in parallel, mixes narration to
-16 LUFS, writes captions, chapters, a poster and one contact sheet per chapter, and
checks the result. Unchanged chapters come from the cache. A failed or interrupted
run keeps its finished chapters; resume with the printed `--run` command. Use
`--max-minutes` to fit a call inside your command timeout; the run stops at a
chapter boundary and resumes later. `.build` over 5 GiB blocks new renders until
`prune`, which keeps the newest `--keep` runs per video (default 1), removes older and
abandoned runs and caches of older runtimes, and never touches a run still rendering.

## Changes

`inspect` reports each planned video. Act on it:

| State | Action |
| --- | --- |
| `storyboard: missing` | Write the storyboard. |
| `storyboard: stale` | The unit's teaching changed: revise affected beats, copy the new hash and fingerprints from `unit`, re-time and render. |
| `published: teaching_changed` | Same as stale, then publish the new run. |
| `published: revision_changed_acknowledge_or_render` | The unit changed outside the video's teaching (for example a new card). Review coverage; if the video still holds, `acknowledge` with the review, otherwise revise. |
| `published: missing_or_changed_files` | Re-publish the last checked final run or render again. |
| `edited_since_publication: true` | Someone edited the storyboard or scene; keep the edits and render. |
| unfinished run | Resume it with `--run`. |
| `interrupted_publication: true` | The next Video Notes command restores the previous files automatically; if it reports that it could not, ask the user to review the journal and archive it names. |

A changed `style.json` or voice profile re-renders a video when you next render it;
nothing re-renders on its own, and one video never mixes profiles.

## Publication

`publish` accepts only a checked, narrated, final run whose inputs (storyboard,
scene, style, timing, voice, assets) are unchanged since rendering, plus a non-empty
teaching review. It archives the previous files, installs the new ones, writes the
manifest last and regenerates README, COVERAGE, SOURCES and the playlist. The app
shows the video in the unit's Content view on the next page load; no study build is
needed unless the installed app predates Video Notes. Hosted sites never include
videos.
