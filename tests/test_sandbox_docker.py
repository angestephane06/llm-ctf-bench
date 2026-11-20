"""Security properties of the real sandbox. Needs Docker and `make image`."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ctfbench.config import SandboxSpec
from ctfbench.sandbox import DockerSandbox

docker = pytest.importorskip("docker")
pytestmark = pytest.mark.docker

ASSETS = Path(__file__).parent / "fixtures" / "tasks" / "assets" / "1"


@pytest.fixture(scope="module")
def client() -> object:
    try:
        c = docker.from_env()
        c.images.get(SandboxSpec().image)
    except Exception as exc:  # no daemon, or image not built
        pytest.skip(f"docker sandbox unavailable: {exc}")
    return c


@pytest.fixture
def box(client: object) -> Iterator[DockerSandbox]:
    with DockerSandbox(SandboxSpec(), ASSETS, client=client) as sandbox:
        yield sandbox


def test_task_files_are_present(box: DockerSandbox) -> None:
    result = box.exec("cat note.txt", timeout_s=10)
    assert "flag{smoke_test}" in result.output


def test_no_network(box: DockerSandbox) -> None:
    probe = (
        'python3 -c "import socket; s=socket.socket(); s.settimeout(3); '
        "s.connect(('1.1.1.1', 53)); print('CONNECTED')\""
    )
    result = box.exec(probe, timeout_s=10)
    assert "CONNECTED" not in result.output and result.exit_code != 0
    interfaces = box.exec("ls /sys/class/net", timeout_s=10).output.split()
    assert interfaces == ["lo"]


def test_runs_unprivileged(box: DockerSandbox) -> None:
    assert box.exec("id -u", timeout_s=10).output.strip() == "1000"
    assert box.exec("grep CapEff /proc/self/status", timeout_s=10).output.split()[-1] == (
        "0000000000000000"
    )


def test_command_timeout_kills_the_command(box: DockerSandbox) -> None:
    result = box.exec("sleep 30", timeout_s=2)
    assert result.timed_out and result.duration_s < 10


def test_container_is_removed(client: object) -> None:
    with DockerSandbox(SandboxSpec(), ASSETS, client=client) as sandbox:
        container_id = sandbox._container.id
    with pytest.raises(docker.errors.NotFound):
        client.containers.get(container_id)  # type: ignore[attr-defined]
