"""Campaign configuration, loaded from YAML and validated before anything runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    # A misspelled key would otherwise be ignored and the campaign would run with a default.
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSpec(_Strict):
    name: str
    provider: Literal["ollama", "scripted"] = "ollama"
    # Extra Ollama options (num_ctx, top_p, ...). Seed and temperature are set per campaign.
    options: dict[str, Any] = Field(default_factory=dict)
    # Reasoning mode of models that have one (qwen3). None leaves the model's default.
    think: bool | None = None
    # Only for provider "scripted": the replies the fake model plays back, in order.
    replies: list[str] = Field(default_factory=list)


class Limits(_Strict):
    max_turns: int = Field(15, ge=1, le=100)
    command_timeout_s: int = Field(30, ge=1, le=600)
    task_timeout_s: int = Field(600, ge=10, le=7200)
    output_chars: int = Field(2000, ge=200, le=20000)


class SandboxSpec(_Strict):
    image: str = "ctfbench-sandbox:latest"
    # Deliberately not configurable: the selected tasks need no service, so the container
    # gets no network interface at all. See README, "Security model".
    network: Literal["none"] = "none"
    memory: str = "512m"
    cpus: float = Field(1.0, gt=0, le=8)
    pids_limit: int = Field(128, ge=16, le=4096)


class CampaignConfig(_Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    models: list[ModelSpec] = Field(min_length=1)
    tasks: list[int] | Literal["all"] = "all"
    seeds: list[int] = Field(default_factory=lambda: [0], min_length=1)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    ollama_url: str = "http://localhost:11434"
    tasks_dir: Path = Path("data/tasks")
    output_dir: Path = Path("results")
    limits: Limits = Field(default_factory=Limits)  # type: ignore[arg-type]
    sandbox: SandboxSpec = Field(default_factory=SandboxSpec)  # type: ignore[arg-type]


def load_config(path: str | Path) -> CampaignConfig:
    """Read a campaign YAML. Relative paths are resolved against the YAML's directory parent."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    config = CampaignConfig.model_validate(raw)
    root = path.resolve().parent.parent
    updates = {}
    for key in ("tasks_dir", "output_dir"):
        value: Path = getattr(config, key)
        if not value.is_absolute():
            updates[key] = root / value
    return config.model_copy(update=updates)
