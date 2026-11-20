from __future__ import annotations

import itertools

import pytest

from ctfbench.agent import parse_action, run_episode
from ctfbench.config import Limits
from ctfbench.models import Completion, Message, ScriptedModel
from ctfbench.tasks import Task
from tests.conftest import FakeShell


@pytest.mark.parametrize(
    ("reply", "kind", "content"),
    [
        ("```bash\nls -la\n```", "command", "ls -la"),
        ("Let me check.\n```sh\ncat a.txt | grep pico\n```", "command", "cat a.txt | grep pico"),
        ("```\nfile x\n```", "command", "file x"),
        ("SUBMIT: picoCTF{abc}", "submit", "picoCTF{abc}"),
        ("Found it!\nSUBMIT: `picoCTF{abc}`", "submit", "picoCTF{abc}"),
        # A submission wins over a command block in the same reply.
        ("```bash\necho done\n```\nSUBMIT: picoCTF{abc}", "submit", "picoCTF{abc}"),
        ("I think the answer is picoCTF{abc}", "invalid", ""),
        # Reasoning is ignored, only the final answer counts.
        ("<think>maybe SUBMIT: picoCTF{guess}</think>\n```bash\nls\n```", "command", "ls"),
        ("<think>unfinished reasoning ```bash\nrm x\n```", "invalid", ""),
        ("```bash\n\n```", "invalid", ""),
    ],
)
def test_parse_action(reply: str, kind: str, content: str) -> None:
    action = parse_action(reply)
    assert (action.kind, action.content) == (kind, content)


def test_solves_after_command(task: Task) -> None:
    model = ScriptedModel("m", ["```bash\ncat note\n```", "SUBMIT: flag{x}"])
    shell = FakeShell({"cat note": "flag{x}\n"})
    ep = run_episode(task, model, shell, Limits(), seed=0, temperature=0.0)
    assert ep.solved and ep.stop_reason == "solved"
    assert ep.turns == 2 and ep.submissions == 1 and ep.flag_seen
    assert shell.commands == ["cat note"]


def test_wrong_submission_continues(task: Task) -> None:
    model = ScriptedModel("m", ["SUBMIT: flag{wrong}", "SUBMIT: flag{x}"])
    ep = run_episode(task, model, FakeShell(), Limits(), seed=0, temperature=0.0)
    assert ep.solved and ep.submissions == 2
    assert ep.steps[0].observation.startswith("Incorrect")


def test_stops_at_max_turns_and_records_flag_seen(task: Task) -> None:
    model = ScriptedModel("m", ["```bash\ncat note\n```"])
    shell = FakeShell({"cat note": "flag{x}"})
    ep = run_episode(task, model, shell, Limits(max_turns=4), seed=0, temperature=0.0)
    assert not ep.solved and ep.stop_reason == "max_turns" and ep.turns == 4
    assert ep.flag_seen  # printed but never submitted


def test_invalid_reply_gets_a_reminder(task: Task) -> None:
    model = ScriptedModel("m", ["hmm", "SUBMIT: flag{x}"])
    ep = run_episode(task, model, FakeShell(), Limits(), seed=0, temperature=0.0)
    assert ep.steps[0].action == "invalid" and "No action found" in ep.steps[0].observation
    assert ep.solved


def test_task_timeout(task: Task) -> None:
    ticks = itertools.count(0, 100)  # each clock read advances 100 s
    model = ScriptedModel("m", ["```bash\nls\n```"])
    ep = run_episode(
        task,
        model,
        FakeShell(),
        Limits(task_timeout_s=250),
        seed=0,
        temperature=0.0,
        clock=lambda: float(next(ticks)),
    )
    assert ep.stop_reason == "task_timeout" and not ep.solved


def test_model_error_is_recorded_not_raised(task: Task) -> None:
    class Broken:
        name = "broken"

        def chat(self, messages: list[Message], seed: int, temperature: float) -> Completion:
            raise ConnectionError("ollama unreachable")

        def describe(self) -> dict[str, str]:
            return {}

    ep = run_episode(task, Broken(), FakeShell(), Limits(), seed=0, temperature=0.0)
    assert ep.stop_reason == "model_error" and "ollama unreachable" in (ep.error or "")


def test_long_output_is_truncated(task: Task) -> None:
    model = ScriptedModel("m", ["```bash\nyes\n```"])
    shell = FakeShell({"yes": "y\n" * 5000})
    ep = run_episode(
        task, model, shell, Limits(max_turns=1, output_chars=300), seed=0, temperature=0.0
    )
    assert ep.steps[0].observation.endswith("[output truncated]")
    assert len(ep.steps[0].observation) < 400
