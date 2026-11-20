"""Command line: `python -m ctfbench run configs/campaign.yaml`."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctfbench", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a campaign described by a YAML file")
    run.add_argument("config", type=Path)

    fetch = sub.add_parser("fetch-tasks", help="download the task files from upstream")
    fetch.add_argument("--manifest", type=Path, default=ROOT / "tasks" / "manifest.yaml")
    fetch.add_argument("--cache", type=Path, default=ROOT / "data" / "upstream")
    fetch.add_argument("--out", type=Path, default=ROOT / "data" / "tasks")

    report = sub.add_parser("report", help="recompute the CSV/JSON reports of a campaign")
    report.add_argument("campaign_dir", type=Path)

    args = parser.parse_args(argv)

    if args.command == "run":
        from ctfbench.config import load_config
        from ctfbench.runner import run_campaign

        rows = run_campaign(load_config(args.config))
        _print_summary(rows)
    elif args.command == "fetch-tasks":
        from ctfbench.fetch import fetch_tasks

        count = fetch_tasks(args.manifest, args.cache, args.out)
        print(f"{count} tasks written to {args.out}")
    elif args.command == "report":
        from ctfbench.metrics import write_reports
        from ctfbench.runner import load_episodes

        _print_summary(write_reports(args.campaign_dir, load_episodes(args.campaign_dir)))
    return 0


def _print_summary(rows: list[dict[str, object]]) -> None:
    print(f"\n{'model':<28}{'category':<22}{'solved':>8}{'rate':>8}")
    for row in rows:
        print(
            f"{row['model']!s:<28}{row['category']!s:<22}"
            f"{row['solved']!s:>4}/{row['episodes']!s:<3}{row['success_rate']!s:>8}"
        )
