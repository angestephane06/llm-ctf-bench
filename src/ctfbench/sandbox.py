"""One throw-away Docker container per episode, with no network and tight resource limits."""

from __future__ import annotations

import io
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from ctfbench.config import SandboxSpec

WORKDIR = "/ctf"
SANDBOX_UID = 1000
# Exit status of coreutils `timeout` when it had to stop the command.
TIMEOUT_EXIT = 124


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    output: str
    timed_out: bool
    duration_s: float


class Shell(Protocol):
    """What the agent needs from a sandbox. Tests provide an in-memory implementation."""

    def exec(self, command: str, timeout_s: int) -> ExecResult: ...


class DockerSandbox:
    """Context manager: starts the container on enter, always removes it on exit."""

    def __init__(self, spec: SandboxSpec, assets_dir: Path | None, client: Any = None) -> None:
        if client is None:
            import docker

            client = docker.from_env()
        self._client = client
        self._spec = spec
        self._assets_dir = assets_dir
        self._container: Any = None

    def __enter__(self) -> DockerSandbox:
        self._container = self._client.containers.run(
            self._spec.image,
            command=["sleep", "infinity"],
            detach=True,
            network_mode=self._spec.network,
            user=f"{SANDBOX_UID}:{SANDBOX_UID}",
            working_dir=WORKDIR,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            mem_limit=self._spec.memory,
            memswap_limit=self._spec.memory,
            nano_cpus=int(self._spec.cpus * 1e9),
            pids_limit=self._spec.pids_limit,
            labels={"ctfbench": "sandbox"},
        )
        if self._assets_dir is not None and self._assets_dir.exists():
            self._container.put_archive(WORKDIR, _tar_dir(self._assets_dir))
        return self

    def exec(self, command: str, timeout_s: int) -> ExecResult:
        if self._container is None:
            raise RuntimeError("sandbox not started")
        start = time.monotonic()
        # The time limit is enforced inside the container, so a runaway command is killed
        # there and not merely abandoned by the host.
        argv = ["timeout", "--kill-after=2", str(timeout_s), "bash", "-c", command]
        code, raw = self._container.exec_run(argv, workdir=WORKDIR, user=str(SANDBOX_UID))
        output = raw.decode("utf-8", errors="replace") if raw else ""
        duration = time.monotonic() - start
        # 137 (SIGKILL) only counts as a timeout if the limit was reached: it can also be OOM.
        timed_out = code == TIMEOUT_EXIT or (code == 137 and duration >= timeout_s)
        return ExecResult(
            exit_code=int(code), output=output, timed_out=timed_out, duration_s=duration
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._container is not None:
            self._container.remove(force=True)
            self._container = None


def _tar_dir(folder: Path) -> bytes:
    """Tar a task folder, owned by the sandbox user, without any `solution` directory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if "solution" in rel.parts:
                continue
            info = tar.gettarinfo(str(path), arcname=str(rel))
            info.uid = info.gid = SANDBOX_UID
            info.uname = info.gname = ""
            if path.is_file():
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
            else:
                tar.addfile(info)
    return buffer.getvalue()
