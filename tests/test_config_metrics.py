from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ctfbench.config import CampaignConfig, load_config
from ctfbench.metrics import summarize, write_reports

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_configs_are_valid() -> None:
    for path in (ROOT / "configs").glob("*.yaml"):
        config = load_config(path)
        assert config.models and config.tasks_dir.is_absolute()


def test_network_cannot_be_enabled() -> None:
    with pytest.raises(ValidationError):
        CampaignConfig.model_validate(
            {"name": "x", "models": [{"name": "m"}], "sandbox": {"network": "bridge"}}
        )


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignConfig.model_validate({"name": "x", "models": [{"name": "m"}], "sedds": [1]})


def _ep(model: str, task: int, seed: int, solved: bool, category: str = "Crypto") -> dict:
    return {
        "model": model,
        "task_id": task,
        "category": category,
        "seed": seed,
        "solved": solved,
        "stop_reason": "solved" if solved else "max_turns",
        "turns": 2 if solved else 10,
        "submissions": int(solved),
        "flag_seen": not solved and task == 2,
        "wall_time_s": 5.0,
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "error": None,
    }


def test_summarize_rates_and_seed_variance() -> None:
    episodes = [
        _ep("a", 1, 0, True),
        _ep("a", 2, 0, False),  # seed 0: 50 %
        _ep("a", 1, 1, True),
        _ep("a", 2, 1, True),
    ]  # seed 1: 100 %
    row = next(r for r in summarize(episodes) if r["category"] == "ALL")
    assert row["solved"] == 3 and row["success_rate"] == 0.75
    assert row["success_std"] == 0.25
    assert row["mean_turns_solved"] == 2 and row["seen_not_submitted"] == 1


def test_write_reports(tmp_path: Path) -> None:
    rows = write_reports(tmp_path, [_ep("a", 1, 0, True), _ep("b", 1, 0, False)])
    assert {r["model"] for r in rows} == {"a", "b"}
    assert (tmp_path / "episodes.csv").read_text().count("\n") == 3
    assert (tmp_path / "summary.json").exists()
