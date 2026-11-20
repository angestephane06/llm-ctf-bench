"""Download the selected InterCode-CTF tasks from a pinned upstream commit."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml


def _git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def fetch_tasks(manifest_path: Path, cache_dir: Path, tasks_dir: Path) -> int:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    upstream = manifest["upstream"]
    checkout = cache_dir / "intercode"
    if not checkout.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", upstream["repo"], str(checkout))
    _git("fetch", "--quiet", "origin", cwd=checkout)
    _git("checkout", "--quiet", upstream["commit"], cwd=checkout)
    head = _git("rev-parse", "HEAD", cwd=checkout)
    if head != upstream["commit"]:
        raise RuntimeError(f"upstream checkout is at {head}, expected {upstream['commit']}")

    index = json.loads((checkout / upstream["index"]).read_text(encoding="utf-8"))
    by_id = {int(t["task_id"]): t for t in index}
    wanted = [int(i) for i in manifest["tasks"]]
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise KeyError(f"task ids not in upstream index: {missing}")

    if tasks_dir.exists():
        shutil.rmtree(tasks_dir)
    (tasks_dir / "assets").mkdir(parents=True)
    entries = []
    for task_id in wanted:
        task = by_id[task_id]
        source = checkout / upstream["assets"] / str(task_id)
        shutil.copytree(
            source,
            tasks_dir / "assets" / str(task_id),
            ignore=shutil.ignore_patterns("solution", ".placeholder", ".ignore"),
        )
        entries.append(
            {
                "task_id": task_id,
                "query": task["query"],
                "flag": task["gold"],
                "category": task["tags"][0],
                "source": task.get("source", ""),
            }
        )
    (tasks_dir / "tasks.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return len(entries)
