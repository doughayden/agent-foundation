"""Post-deploy smoke checks against a live Cloud Run revision.

This lane confirms a freshly deployed revision actually serves: it drives the live
service URL over a real network with an authenticated httpx client, so a request
crosses the network, the Auth Proxy sidecar, and Cloud SQL exactly as production
traffic does.

Checks are layered cheapest-first, each a distinct failure class so a failure localizes
the broken subsystem:

- L0 liveness: the revision serves HTTP at all (``/health`` -> 200).
- L1 session create: Cloud SQL is reachable via the Auth Proxy sidecar (a session row
  persists). Deterministic, no model. Provided as a module-scoped fixture so its
  teardown deletes the row unconditionally even if a later check fails.
- L2 thin agent turn: the run path streams a model response (``/run_sse``). The real
  model is invoked, but the assertion is presence-only — at least one event carries a
  text part — never content, so there is no LLM-judge dependency.
- L3 cleanup: the smoke session is deleted and a follow-up GET returns 404, proving the
  delete path and leaving no residue.

The service is private (``--no-allow-unauthenticated``), so Cloud Run requires a
Google-signed OIDC ID token whose audience is the service URL. The caller's own
Application Default Credentials — the developer's gcloud login locally, the GitHub
Actions WIF principal in CI — cannot mint that token directly, so the client
impersonates a dedicated invoker service account (``SMOKE_INVOKER_SA``) to generate the
ID token in-process and sends it as ``Authorization: Bearer``. The lane runs only by
explicit path (``uv run pytest tests/smoke``) against ``SMOKE_BASE_URL``.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

import google.auth
import pytest
import pytest_asyncio
from google.auth import impersonated_credentials
from google.auth.transport.requests import Request
from httpx import AsyncClient, TransportError

# Source root holding the single agent package (src/<package>/). The ADK app name is
# its directory name, discovered so a renamed fork reuses the lane with no edits.
SRC_DIR = Path(__file__).parents[2] / "src"
APP_NAME = next(SRC_DIR.glob("*/__init__.py")).parent.name

# Fail fast if the required environment variables are not set
SMOKE_BASE_URL = os.environ.get("SMOKE_BASE_URL")
if not SMOKE_BASE_URL:
    pytest.fail(
        "SMOKE_BASE_URL is unset. The smoke test targets a live deployed URL and "
        "runs only by explicit path (uv run pytest tests/smoke), after a deploy."
    )
SMOKE_INVOKER_SA = os.environ.get("SMOKE_INVOKER_SA")
if not SMOKE_INVOKER_SA:
    pytest.fail(
        "SMOKE_INVOKER_SA is unset. The test impersonates this service account to "
        "mint the Cloud Run ID token."
    )

# Smoke test session user
USER_ID = "smoke-user"

# Scope for the impersonation exchange; Cloud Run authorizes on IAM, not the scope.
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Cold-start budget for the post-deploy readiness wait (Cloud Run startup-probe window).
READINESS_DEADLINE = 180.0
READINESS_INTERVAL = 3.0

pytestmark = [
    pytest.mark.smoke,
    # The client fixture is session-scoped (one connection per run); its async setup
    # and these tests must share one event loop.
    pytest.mark.asyncio(loop_scope="session"),
]


async def _wait_until_serving(http_client: AsyncClient) -> None:
    """Poll ``/health`` until the revision serves, tolerating cold-start latency.

    A freshly deployed revision is cold, and Cloud Run holds the first request until the
    container passes its startup probe (~120s credential-init budget). Warming up here
    keeps the layered checks from absorbing that one-time latency, so they run with the
    normal per-request timeout.
    """
    deadline = time.monotonic() + READINESS_DEADLINE
    while True:
        try:
            resp = await http_client.get("/health", timeout=READINESS_DEADLINE)
            if resp.status_code == 200:
                return
        except TransportError:
            pass
        if time.monotonic() >= deadline:
            pytest.fail(
                f"service did not serve /health within {READINESS_DEADLINE:.0f}s"
            )
        await asyncio.sleep(READINESS_INTERVAL)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client() -> AsyncIterator[AsyncClient]:
    """Authenticated httpx client over a real network to the live service.

    Targets the module-level ``SMOKE_BASE_URL`` and impersonates ``SMOKE_INVOKER_SA``
    (both validated at import) to mint an OIDC ID token whose audience is the service
    URL, sent as ``Authorization: Bearer``. Impersonation runs in-process from the
    caller's own ADC, so no token is passed through the environment.
    """
    source_credentials, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
    id_token_credentials = impersonated_credentials.IDTokenCredentials(
        impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=SMOKE_INVOKER_SA,
            target_scopes=[CLOUD_PLATFORM_SCOPE],
        ),
        target_audience=SMOKE_BASE_URL,
        include_email=True,
    )
    id_token_credentials.refresh(Request())
    async with AsyncClient(
        base_url=SMOKE_BASE_URL,
        headers={"Authorization": f"Bearer {id_token_credentials.token}"},
        timeout=30.0,
    ) as http_client:
        await _wait_until_serving(http_client)
        yield http_client


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def smoke_session_id(client: AsyncClient) -> AsyncIterator[str]:
    """Create a session, yield its id, and delete it unconditionally on teardown.

    Proves Cloud SQL reachability via the Auth Proxy sidecar on setup. Owning the
    delete in teardown (rather than a trailing test method) guarantees the row is
    cleaned up even when a downstream check fails or the run aborts under ``-x``.
    """
    resp = await client.post(
        f"/apps/{APP_NAME}/users/{USER_ID}/sessions",
        json={"state": {}},
    )
    assert resp.status_code == 200
    session_id = resp.json()["id"]
    assert session_id
    try:
        yield session_id
    finally:
        await client.delete(f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{session_id}")


class TestSmoke:
    """Layered checks sharing one smoke session whose cleanup is fixture-guaranteed."""

    async def test_l0_health_liveness(self, client: AsyncClient) -> None:
        """L0: the deployed revision answers the liveness probe.

        Redundant with the client fixture's readiness poll, which already drove
        ``/health`` to 200. Kept as an explicit, separately-reported liveness check —
        explicit over implicit — rather than leaving liveness as an unnamed setup step.
        """
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_l1_session_create(
        self, client: AsyncClient, smoke_session_id: str
    ) -> None:
        """L1: the created session is readable back, proving Cloud SQL reachability.

        GETs the session the fixture created so the round-trip is an independent
        signal distinct from the fixture's create-time assertion.
        """
        resp = await client.get(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{smoke_session_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == smoke_session_id

    async def test_l2_agent_turn_streams_text(
        self, client: AsyncClient, smoke_session_id: str
    ) -> None:
        """L2: the run path streams at least one text-bearing event.

        Invokes the real model but asserts presence of a text part only, never its
        content, so the check is robust to stochastic output. Drains the whole stream
        instead of breaking on first text: closing mid-flight makes Cloud Run log a
        spurious client disconnect on every run, eroding the post-deploy log signal,
        and the trivial prompt's response is small enough that draining is cheap.
        """
        body = {
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "session_id": smoke_session_id,
            "new_message": {"role": "user", "parts": [{"text": "Hi!"}]},
            "streaming": True,
        }

        saw_text = False
        async with client.stream("POST", "/run_sse", json=body) as resp:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode(errors="replace")
                pytest.fail(f"/run_sse returned {resp.status_code}: {detail}")
            async for line in resp.aiter_lines():
                if saw_text or not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if not payload:
                    continue
                event = json.loads(payload)
                parts = event.get("content", {}).get("parts", [])
                if any(isinstance(p.get("text"), str) and p["text"] for p in parts):
                    saw_text = True

        assert saw_text, "no text-bearing event in the /run_sse stream"

    async def test_l3_session_delete_returns_404(
        self, client: AsyncClient, smoke_session_id: str
    ) -> None:
        """L3 cleanup: deleting the smoke session makes a follow-up GET return 404.

        Deletes here (proving the delete path) and the fixture teardown's idempotent
        delete tolerates the already-removed row.
        """
        delete = await client.delete(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{smoke_session_id}"
        )
        assert delete.status_code == 200

        gone = await client.get(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{smoke_session_id}"
        )
        assert gone.status_code == 404
