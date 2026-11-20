"""Run a campaign: every model on every task with every seed. Each episode is saved as soon
as it ends, so an interrupted campaign resumes where it stopped."""

from __future__ import annotations

import json
import platform
import re
import subprocess
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ctfbench import __version__
from ctfbench.agent import run_episode
from ctfbench.config import CampaignConfig, ModelSpec
from ctfbench.metrics import write_reports
from ctfbench.models import ChatModel, build_model
from ctfbench.sandbox import DockerSandbox, Shell
from ctfbench.tasks import Task, load_tasks

SandboxFactory = Callable[[Task], AbstractContextManager[Shell]]
ModelFactory = Callable[[ModelSpec, str], ChatModel]


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def docker_sandbox_factory(config: CampaignConfig) -> SandboxFactory:
    import docker

    client = docker.from_env()

    def factory(task: Task) -> AbstractContextManager[Shell]:
        return DockerSandbox(config.sandbox, task.assets_dir, client=client)

    return factory


def run_campaign(
    config: CampaignConfig,
    sandbox_factory: SandboxFactory | None = None,
    model_factory: ModelFactory = build_model,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    out = config.output_dir / config.name
    traces = out / "traces"
    tasks = load_tasks(config.tasks_dir, config.tasks)
    factory = sandbox_factory or docker_sandbox_factory(config)

    metadata: dict[str, Any] = {
        "campaign": config.name,
        "started_at": datetime.now(UTC).isoformat(),
        "ctfbench_version": __version__,
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "config": config.model_dump(mode="json"),
        "models": [],
    }

    total = len(config.models) * len(tasks) * len(config.seeds)
    done = 0
    # Model-major order: each model is loaded into GPU memory once, not once per task.
    for spec in config.models:
        metadata["models"].append(model_factory(spec, config.ollama_url).describe())
        for task in tasks:
            for seed in config.seeds:
                done += 1
                trace = traces / _slug(spec.name) / f"task{task.task_id}_seed{seed}.json"
                if trace.exists():
                    log(f"[{done}/{total}] {spec.name} task {task.task_id} seed {seed}: kept")
                    continue
                model = model_factory(spec, config.ollama_url)
                with factory(task) as shell:
                    episode = run_episode(
                        task, model, shell, config.limits, seed, config.temperature
                    )
                trace.parent.mkdir(parents=True, exist_ok=True)
                trace.write_text(json.dumps(episode.to_dict(), indent=2), encoding="utf-8")
                verdict = "SOLVED" if episode.solved else episode.stop_reason
                log(
                    f"[{done}/{total}] {spec.name} task {task.task_id} seed {seed}: "
                    f"{verdict} in {episode.turns} turns, {episode.wall_time_s:.0f}s"
                )

    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    episodes = load_episodes(out)
    return write_reports(out, episodes)


def load_episodes(campaign_dir: Path) -> list[dict[str, Any]]:
    episodes = []
    for path in sorted((campaign_dir / "traces").glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("steps", None)
        episodes.append(data)
    return episodes
