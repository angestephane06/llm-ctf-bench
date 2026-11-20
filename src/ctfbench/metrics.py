"""Aggregate episodes into per-model and per-category metrics, exported as CSV and JSON."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

EPISODE_FIELDS = [
    "model",
    "task_id",
    "category",
    "seed",
    "solved",
    "stop_reason",
    "turns",
    "submissions",
    "flag_seen",
    "wall_time_s",
    "prompt_tokens",
    "completion_tokens",
    "error",
]


def summarize(episodes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (model, category), plus one (model, "ALL") row.

    `success_std` is the standard deviation of the success rate across seeds: with a single
    seed it is 0, which says nothing about run-to-run variance.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for ep in episodes:
        groups[(ep["model"], ep["category"])].append(ep)
        groups[(ep["model"], "ALL")].append(ep)

    rows = []
    for (model, category), eps in sorted(groups.items()):
        by_seed: dict[int, list[bool]] = defaultdict(list)
        for ep in eps:
            by_seed[int(ep["seed"])].append(bool(ep["solved"]))
        seed_rates = [sum(v) / len(v) for v in by_seed.values()]
        solved = [ep for ep in eps if ep["solved"]]
        rows.append(
            {
                "model": model,
                "category": category,
                "episodes": len(eps),
                "solved": len(solved),
                "success_rate": round(len(solved) / len(eps), 4),
                "success_std": round(statistics.pstdev(seed_rates), 4) if seed_rates else 0.0,
                "mean_turns": round(statistics.fmean(ep["turns"] for ep in eps), 2),
                "mean_turns_solved": (
                    round(statistics.fmean(ep["turns"] for ep in solved), 2) if solved else None
                ),
                "mean_wall_time_s": round(statistics.fmean(ep["wall_time_s"] for ep in eps), 2),
                "total_tokens": sum(ep["prompt_tokens"] + ep["completion_tokens"] for ep in eps),
                # The model printed the flag but never submitted it: a planning failure, not a
                # capability failure, worth separating from plain misses.
                "seen_not_submitted": sum(1 for ep in eps if ep["flag_seen"] and not ep["solved"]),
                "errors": sum(1 for ep in eps if ep["stop_reason"] == "model_error"),
            }
        )
    return rows


def write_reports(out_dir: Path, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "episodes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EPISODE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(episodes, key=lambda e: (e["model"], e["task_id"], e["seed"])))

    rows = summarize(episodes)
    if rows:
        with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows
