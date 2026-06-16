"""Fixtures for the smoke lane (real HTTP against a live deployed revision).

This lane verifies a freshly deployed Cloud Run revision actually serves: it drives
the live service URL over a real network with an authenticated httpx client. Unlike
the integration lane (which builds the app in-process via ASGI), nothing here is
substituted — the request crosses the network, the Auth Proxy sidecar, and Cloud SQL.
The L2 turn invokes the real model; the lane asserts only that a text part returned
(presence, never content), so it carries no LLM-judge dependency.

Runs only in CI after a deploy, where ``smoke.yml`` resolves the service URL and mints
a Cloud Run identity token impersonating the dedicated invoker SA, exporting both as
env vars:

- ``SMOKE_BASE_URL`` — the deployed service URL (the httpx ``base_url``).
- ``SMOKE_ID_TOKEN`` — a Cloud Run ID token (sent as ``Authorization: Bearer``).

Both are required; the fixtures fail clearly if either is unset, since this lane has
no meaning without a live target. A bare ``uv run pytest`` never collects it
(``testpaths`` is the unit lane); select it explicitly with ``uv run pytest
tests/smoke``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient

# ADK app name — the agent package directory discovered under src/
# (src/agent_foundation -> "agent_foundation").
APP_NAME = "agent_foundation"

USER_ID = "smoke-user"

# A conftest `pytestmark` does not propagate to sibling test modules: each smoke test
# module declares its own `pytestmark` (smoke marker + session loop scope, see
# test_smoke.py) so it is selected under the lane and shares the client's event loop.


@pytest.fixture(scope="session")
def base_url() -> str:
    """Live service URL, required from the environment."""
    url = os.environ.get("SMOKE_BASE_URL")
    if not url:
        pytest.fail(
            "SMOKE_BASE_URL is unset. The smoke lane targets a live deployed URL and "
            "only runs in CI after a deploy (see .github/workflows/smoke.yml)."
        )
    return url


@pytest.fixture(scope="session")
def id_token() -> str:
    """Cloud Run identity token, required from the environment."""
    token = os.environ.get("SMOKE_ID_TOKEN")
    if not token:
        pytest.fail(
            "SMOKE_ID_TOKEN is unset. The smoke lane needs a Cloud Run ID token minted "
            "by impersonating the invoker SA (see .github/workflows/smoke.yml)."
        )
    return token


@pytest.fixture(scope="session")
def app_name() -> str:
    """ADK app name (the agent package directory discovered under src/)."""
    return APP_NAME


@pytest.fixture(scope="session")
def user_id() -> str:
    """Synthetic user id for smoke session rows."""
    return USER_ID


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(base_url: str, id_token: str) -> AsyncIterator[AsyncClient]:
    """Authenticated httpx client over a real network to the live service."""
    async with AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=30.0,
    ) as c:
        yield c
