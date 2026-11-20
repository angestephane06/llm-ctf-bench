"""CTF task definitions.

Tasks are stored as ``<tasks_dir>/tasks.json`` (one entry per task) plus one asset folder per
task, ``<tasks_dir>/assets/<task_id>/``, which is copied into the sandbox. The expected flag stays
on the host: it is never copied into the container.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    task_id: int
    query: str
    flag: str
    category: str
    source: str
    assets_dir: Path


def load_tasks(tasks_dir: Path, ids: list[int] | str = "all") -> list[Task]:
    index_file = tasks_dir / "tasks.json"
    if not index_file.exists():
        raise FileNotFoundError(
            f"{index_file} not found. Run `python -m ctfbench fetch-tasks` first."
        )
    entries = json.loads(index_file.read_text(encoding="utf-8"))
    tasks = [
        Task(
            task_id=int(e["task_id"]),
            query=e["query"],
            flag=e["flag"],
            category=e["category"],
            source=e.get("source", ""),
            assets_dir=tasks_dir / "assets" / str(e["task_id"]),
        )
        for e in entries
    ]
    if isinstance(ids, str):
        if ids != "all":
            raise ValueError(f"tasks must be 'all' or a list of ids, got {ids!r}")
        return tasks
    wanted = set(ids)
    found = [t for t in tasks if t.task_id in wanted]
    missing = wanted - {t.task_id for t in found}
    if missing:
        raise KeyError(f"unknown task ids: {sorted(missing)}")
    return found
