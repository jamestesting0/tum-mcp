"""Command line for the skill lab: `uv run skill-lab/lab.py <command>`."""

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skill_lab import LabError, models, paths, rounds
from skill_lab.models import ModelSpec


def show(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def cmd_profile(args: argparse.Namespace) -> None:
    from skill_lab import profiles

    selected = [args.host] if args.host else list(models.HOSTS)
    if args.action == "create":
        for host in selected:
            print(f"{host}: log in once with\n  {profiles.create(host)}")
    else:
        show([profiles.check(host) for host in selected])


def cmd_models(args: argparse.Namespace) -> None:
    show(models.available(args.host, paths.profile_home(args.host)))


def cmd_round(args: argparse.Namespace) -> None:
    if args.action == "status":
        show({"round": rounds.load(args.round), "runs": rounds.status_rows(args.round)})
        return
    if not args.scenario or not args.author or not args.judge or not args.reason:
        raise LabError("round new needs --scenario, --author, --judge and --reason.")
    if args.fresh == bool(args.previous):
        raise LabError("Choose exactly one of --fresh or --from.")
    show(
        rounds.new(
            args.round,
            scenario=args.scenario,
            confirm_scenario=args.confirm_scenario,
            author=args.author,
            judge=args.judge,
            confirm_judges=args.confirm_judge,
            matrix=args.matrix or [],
            reason=args.reason,
            base_ref=args.base,
            previous=args.previous,
            baselines=args.baseline,
            budget_runs=args.budget_runs,
            budget_judges=args.budget_judges,
            turn_timeout_min=args.turn_timeout_min,
        )
    )


def cmd_baseline(args: argparse.Namespace) -> None:
    show(rounds.set_baselines(args.round, args.runs)["baselines"])


def cmd_variant(args: argparse.Namespace) -> None:
    from skill_lab import variants

    base = rounds.base_of(rounds.load(args.round))
    directory = variants.create(args.round, args.name, base, args.patch)
    show(
        {"variant": args.name, "path": str(directory), "touched": variants.touched_paths(directory)}
    )


def cmd_run(args: argparse.Namespace) -> None:
    from skill_lab import runs

    if args.all_authors and args.author:
        raise LabError("Choose --author or --all-authors.")
    if args.all_authors:
        config = rounds.load(args.round)
        authors = [
            ModelSpec.from_dict(item) for item in (config["roles"]["author"], *config["matrix"])
        ]
    else:
        authors = [ModelSpec.parse(args.author) if args.author else None]
    for author in filter(None, authors):
        models.validate(author, role="author", profile_home=paths.profile_home(author.host))

    def run_author(author: ModelSpec | None) -> list[dict]:
        records = []
        for _ in range(args.repeat):
            record = runs.execute(
                args.round,
                args.variant,
                author=author,
                scenario_id=args.scenario,
                checkpoint=args.from_checkpoint,
                confirm=args.confirm,
            )
            records.append({key: record.get(key) for key in ("id", "status", "minutes", "error")})
        return records

    # Each author runs on its own host, so the authors' runs go side by side.
    with ThreadPoolExecutor(max_workers=len(authors)) as pool:
        show([record for records in pool.map(run_author, authors) for record in records])


def cmd_collect(args: argparse.Namespace) -> None:
    from skill_lab import collect

    targets = args.run or [run["id"] for run in rounds.runs_of(args.round)]
    show([collect.collect_run(args.round, run, visuals=not args.no_visuals) for run in targets])


def cmd_judge(args: argparse.Namespace) -> None:
    from skill_lab import judge

    pairs = [pair.split(":", 1) for pair in args.pairs or []]
    if args.confirm and not pairs:
        pairs = [["base", "composed"]]
    if not pairs:
        pairs = judge.default_pairs(args.round)
    specs = [ModelSpec.parse(text) for text in args.judge] if args.judge else None
    show(
        [
            judge.judge_pair(args.round, left, right, confirm=args.confirm, judges=specs)
            for left, right in pairs
        ]
    )


def cmd_review(args: argparse.Namespace) -> None:
    from skill_lab import judge

    specs = [ModelSpec.parse(text) for text in args.judge] if args.judge else None
    show([judge.review_run(args.round, run, judges=specs) for run in args.run])


def cmd_human(args: argparse.Namespace) -> None:
    from skill_lab import human

    text = args.note or (args.file.read_text(encoding="utf-8") if args.file else "")
    if text:
        human.add_note(args.round, args.run, text)
    show(human.summary(args.round, args.run))


def cmd_ledger(args: argparse.Namespace) -> None:
    from skill_lab import ledger

    print(ledger.add(args.round, args.decision))


def cmd_clean(args: argparse.Namespace) -> None:
    root = paths.rounds()
    found = (
        sorted(
            (path for path in root.iterdir() if (path / "round.yaml").is_file()),
            key=lambda path: (path / "round.yaml").stat().st_mtime,
        )
        if root.is_dir()
        else []
    )
    removed = [path.name for path in found[: max(0, len(found) - args.keep)]]
    for name in removed:
        shutil.rmtree(root / name)
        shutil.rmtree(paths.workspaces() / name, ignore_errors=True)
    show({"removed": removed, "kept": [path.name for path in found if path.name not in removed]})


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="lab", description="Skill lab (dev-only).")
    sub = top.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profile", help="Create or check the isolated host profiles.")
    p.add_argument("action", choices=("create", "check"))
    p.add_argument("--host", choices=models.HOSTS)
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("models", help="List the models and efforts a host profile can use.")
    p.add_argument("--host", choices=models.HOSTS, required=True)
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("round", help="Create a round or show its status.")
    p.add_argument("action", choices=("new", "status"))
    p.add_argument("round")
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--from", dest="previous")
    p.add_argument("--base", help="Git ref or WORKTREE for --fresh (default HEAD).")
    p.add_argument("--scenario")
    p.add_argument("--confirm-scenario")
    p.add_argument("--author", help="host:model:effort")
    p.add_argument("--judge", help="host:model:effort for probe judging")
    p.add_argument("--confirm-judge", action="append", help="repeatable host:model:effort")
    p.add_argument("--matrix", action="append", help="extra author host:model:effort")
    p.add_argument(
        "--baseline",
        action="append",
        help="ROUND/RUN to judge candidates against (default with --from: its newest per author)",
    )
    p.add_argument("--reason")
    p.add_argument("--budget-runs", type=int, default=10)
    p.add_argument("--budget-judges", type=int, default=6)
    p.add_argument("--turn-timeout-min", type=int, default=45)
    p.set_defaults(func=cmd_round)

    p = sub.add_parser(
        "baseline", help="Set the earlier runs a round's candidates are judged against."
    )
    p.add_argument("round")
    p.add_argument("runs", nargs="+", help="ROUND/RUN, one per author")
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("variant", help="Create a variant from the round base plus a patch.")
    p.add_argument("round")
    p.add_argument("name")
    p.add_argument("--patch", type=Path)
    p.set_defaults(func=cmd_variant)

    p = sub.add_parser("run", help="Run the scenario as a simulated student.")
    p.add_argument("round")
    p.add_argument("--variant", required=True)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--author", help="override host:model:effort (new comparison group)")
    p.add_argument(
        "--all-authors",
        action="store_true",
        help="run the round's author and every --matrix author at once, one per host",
    )
    p.add_argument("--scenario")
    p.add_argument("--from", dest="from_checkpoint", help="RUN@TURN or ROUND/RUN@TURN")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("collect", help="Compute workflow metrics for runs.")
    p.add_argument("round")
    p.add_argument("--run", action="append")
    p.add_argument("--no-visuals", action="store_true")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("judge", help="Blind-judge pairs of runs.")
    p.add_argument("round")
    p.add_argument("--pairs", nargs="*")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--judge", action="append", help="override judge host:model:effort")
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("review", help="Blind agent review of single runs (other host's judge).")
    p.add_argument("round")
    p.add_argument("--run", action="append", required=True)
    p.add_argument("--judge", action="append", help="override reviewer host:model:effort")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("human", help="Record your review of a run; collects in-app comments.")
    p.add_argument("round")
    p.add_argument("--run", required=True)
    p.add_argument("--note", help="A note about the run, in your words.")
    p.add_argument("--file", type=Path, help="A file with your notes.")
    p.set_defaults(func=cmd_human)

    p = sub.add_parser("ledger", help="Append a sanitized round entry to skill-lab/ledger.md.")
    p.add_argument("action", choices=("add",))
    p.add_argument("round")
    p.add_argument("--decision", type=Path, required=True)
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("clean", help="Delete old rounds' local state.")
    p.add_argument("--keep", type=int, default=3)
    p.set_defaults(func=cmd_clean)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except LabError as error:
        print(f"lab: {error}", file=sys.stderr)
        return 1
    return 0
