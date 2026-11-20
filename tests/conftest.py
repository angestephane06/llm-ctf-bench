from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ctfbench.sandbox import ExecResult
from ctfbench.tasks import Task

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FakeShell:
    """In-memory sandbox: maps a command to its output."""

    outputs: dict[str, str] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)

    def exec(self, command: str, timeout_s: int) -> ExecResult:
        self.commands.append(command)
        return ExecResult(
            exit_code=0, output=self.outputs.get(command, ""), timed_out=False, duration_s=0.01
        )

    def __enter__(self) -> FakeShell:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def task() -> Task:
    return Task(
        task_id=1,
        query="Find the flag.",
        flag="flag{x}",
        category="Fixture",
        source="test",
        assets_dir=FIXTURES / "tasks" / "assets" / "1",
    )
