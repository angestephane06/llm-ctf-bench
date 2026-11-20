"""Chat model clients. All models go through the same plain-text protocol, so no model gets
an advantage from a provider-specific tool-calling format."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ctfbench.config import ModelSpec


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float


class ChatModel(Protocol):
    name: str

    def chat(self, messages: list[Message], seed: int, temperature: float) -> Completion: ...

    def describe(self) -> dict[str, Any]: ...


class OllamaModel:
    def __init__(
        self,
        name: str,
        base_url: str,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self.name = name
        self._options = {"num_ctx": 16384, **(options or {})}
        self._think = think
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s)

    def chat(self, messages: list[Message], seed: int, temperature: float) -> Completion:
        start = time.monotonic()
        payload: dict[str, Any] = {
            "model": self.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {**self._options, "seed": seed, "temperature": temperature},
        }
        if self._think is not None:
            payload["think"] = self._think
        response = self._http.post("/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()
        return Completion(
            text=body["message"]["content"],
            prompt_tokens=int(body.get("prompt_eval_count", 0)),
            completion_tokens=int(body.get("eval_count", 0)),
            latency_s=time.monotonic() - start,
        )

    def describe(self) -> dict[str, Any]:
        """Exact model build, recorded with the results so a campaign can be reproduced."""
        try:
            tags = self._http.get("/api/tags").json().get("models", [])
            digest = next((m["digest"] for m in tags if m["name"] == self.name), None)
        except httpx.HTTPError:
            digest = None
        return {"name": self.name, "provider": "ollama", "digest": digest, "options": self._options}


class ScriptedModel:
    """Plays back fixed replies. Used by the tests and by the CI smoke campaign (no GPU)."""

    def __init__(self, name: str, replies: list[str]) -> None:
        if not replies:
            raise ValueError("a scripted model needs at least one reply")
        self.name = name
        self._replies = replies
        self._turn = 0

    def chat(self, messages: list[Message], seed: int, temperature: float) -> Completion:
        reply = self._replies[min(self._turn, len(self._replies) - 1)]
        self._turn += 1
        return Completion(
            text=reply,
            prompt_tokens=sum(len(m.content) for m in messages) // 4,
            completion_tokens=len(reply) // 4,
            latency_s=0.0,
        )

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "provider": "scripted"}


def build_model(spec: ModelSpec, ollama_url: str) -> ChatModel:
    if spec.provider == "scripted":
        return ScriptedModel(spec.name, list(spec.replies))
    return OllamaModel(spec.name, ollama_url, dict(spec.options), think=spec.think)
