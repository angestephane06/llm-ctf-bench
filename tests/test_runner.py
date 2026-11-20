from __future__ import annotations

from pathlib import Path

from ctfbench.config import load_config
from ctfbench.runner import run_campaign
from ctfbench.tasks import Task
from tests.conftest import FakeShell

ROOT = Path(__file__).resolve().parents[1]


def _fake_factory(task: Task) -> FakeShell:
    return FakeShell({"ls -la && cat note.txt": "The flag is flag{smoke_test}"})


def test_campaign_runs_and_resumes(tmp_path: Path) -> None:
    config = load_config(ROOT / "configs" / "smoke.yaml").model_copy(
        update={"output_dir": tmp_path}
    )
    rows = run_campaign(config, sandbox_factory=_fake_factory, log=lambda _: None)
    overall = {r["model"]: r for r in rows if r["category"] == "ALL"}
    assert overall["scripted-solver"]["success_rate"] == 1.0
    assert overall["scripted-idle"]["success_rate"] == 0.0
    assert len(list((tmp_path / "smoke" / "traces").glob("*/*.json"))) == 4

    logs: list[str] = []
    run_campaign(config, sandbox_factory=_fake_factory, log=logs.append)
    assert all(line.endswith("kept") for line in logs)  # nothing re-run
