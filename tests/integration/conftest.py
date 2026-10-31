"""Integration lane Docker setup for testcontainers.

Holds only the ``pytest_configure`` hook, which pytest collects from ``conftest.py``
files and never from test modules. Fixtures and credential blocking stay in
``test_server_integration.py``.
"""

import os
import shutil
import subprocess

import pytest


def _docker(*args: str) -> str:
    """Run the docker CLI and return its stdout."""
    docker = shutil.which("docker")
    if docker is None:
        raise pytest.UsageError("integration tests need docker on PATH")
    try:
        result = subprocess.run(  # noqa: S603 - resolved docker binary, literal args
            [docker, *args], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as exc:
        raise pytest.UsageError(
            f"integration tests need a reachable docker daemon "
            f"(docker {' '.join(args)}): {exc.stderr.strip()}"
        ) from exc
    return result.stdout.strip()


def pytest_configure(config: pytest.Config) -> None:
    """Check that Docker answers, then point testcontainers at it.

    testcontainers uses the Docker SDK, which reads ``DOCKER_HOST`` and ignores
    docker contexts, so the active context's endpoint is exported here unless the
    caller already set one. Ryuk mounts that socket path into a container, which
    fails when the path exists only on the host, so the container fixture's context
    manager handles cleanup instead. ``INTEGRATION_DATABASE_URI`` skips the
    container, so Docker is not needed then.
    """
    if os.environ.get("INTEGRATION_DATABASE_URI"):
        return
    _docker("info")
    if "DOCKER_HOST" not in os.environ:
        os.environ["DOCKER_HOST"] = _docker(
            "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"
        )
        os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
