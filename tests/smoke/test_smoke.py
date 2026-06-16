"""Post-deploy smoke checks against a live Cloud Run revision.

Layered cheapest-first, each a distinct failure class so a failure localizes the
broken subsystem:

- L0 liveness: the revision serves HTTP at all (``/health`` -> 200).
- L1 session create: Cloud SQL is reachable via the Auth Proxy sidecar (a session row
  persists). Deterministic, no model. Provided as a module-scoped fixture so its
  teardown deletes the row unconditionally even if a later check fails.
- L2 thin agent turn: the run path streams a model response (``/run_sse``). The real
  model is invoked, but the assertion is presence-only — at least one event carries a
  text part — never content, so there is no LLM-judge dependency.
- Cleanup: the smoke session is deleted and a follow-up GET returns 404, proving the
  delete path and leaving no residue.

Every test is marked ``smoke`` (module ``pytestmark``) and runs only by explicit path
(``uv run pytest tests/smoke``) against ``SMOKE_BASE_URL`` with ``SMOKE_ID_TOKEN``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = [
    pytest.mark.smoke,
    # The client fixture is session-scoped (one connection per run); its async setup
    # and these tests must share one event loop.
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def smoke_session_id(
    client: AsyncClient, app_name: str, user_id: str
) -> AsyncIterator[str]:
    """Create a session, yield its id, and delete it unconditionally on teardown.

    Proves Cloud SQL reachability via the Auth Proxy sidecar on setup. Owning the
    delete in teardown (rather than a trailing test method) guarantees the row is
    cleaned up even when a downstream check fails or the run aborts under ``-x``.
    """
    resp = await client.post(
        f"/apps/{app_name}/users/{user_id}/sessions",
        json={"state": {}},
    )
    assert resp.status_code == 200
    session_id = resp.json()["id"]
    assert session_id
    try:
        yield session_id
    finally:
        await client.delete(f"/apps/{app_name}/users/{user_id}/sessions/{session_id}")


class TestSmoke:
    """Layered checks sharing one smoke session whose cleanup is fixture-guaranteed."""

    async def test_l0_health_liveness(self, client: AsyncClient) -> None:
        """L0: the deployed revision answers the liveness probe."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_l1_session_create(
        self,
        client: AsyncClient,
        app_name: str,
        user_id: str,
        smoke_session_id: str,
    ) -> None:
        """L1: the created session is readable back, proving Cloud SQL reachability.

        GETs the session the fixture created so the round-trip is an independent
        signal distinct from the fixture's create-time assertion.
        """
        resp = await client.get(
            f"/apps/{app_name}/users/{user_id}/sessions/{smoke_session_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == smoke_session_id

    async def test_l2_agent_turn_streams_text(
        self,
        client: AsyncClient,
        app_name: str,
        user_id: str,
        smoke_session_id: str,
    ) -> None:
        """L2: the run path streams at least one text-bearing event.

        Invokes the real model. Asserts presence of a text part only — never its
        content — so the check is robust to the model's stochastic output.
        """
        body = {
            "app_name": app_name,
            "user_id": user_id,
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
                # Keep draining once a text part is seen rather than breaking early:
                # closing the stream mid-flight makes Cloud Run log a spurious client
                # disconnect on every run, eroding the post-deploy log signal. The
                # trivial prompt's response is small, so draining is cheap.
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
        self,
        client: AsyncClient,
        app_name: str,
        user_id: str,
        smoke_session_id: str,
    ) -> None:
        """Cleanup: deleting the smoke session makes a follow-up GET return 404.

        Deletes here (proving the delete path) and the fixture teardown's idempotent
        delete tolerates the already-removed row.
        """
        delete = await client.delete(
            f"/apps/{app_name}/users/{user_id}/sessions/{smoke_session_id}"
        )
        assert delete.status_code == 200

        gone = await client.get(
            f"/apps/{app_name}/users/{user_id}/sessions/{smoke_session_id}"
        )
        assert gone.status_code == 404
