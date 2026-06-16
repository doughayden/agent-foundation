"""Post-deploy smoke checks against a live Cloud Run revision.

Layered cheapest-first, each a distinct failure class so a failure localizes the
broken subsystem:

- L0 liveness: the revision serves HTTP at all (``/health`` -> 200).
- L1 session create: Cloud SQL is reachable via the Auth Proxy sidecar (a session row
  persists). Deterministic, no model.
- L2 thin agent turn: the run path streams a model response (``/run_sse``). The real
  model is invoked, but the assertion is presence-only — at least one event carries a
  text part — never content, so there is no LLM-judge dependency.
- Cleanup: the smoke session is deleted and a follow-up GET returns 404, proving the
  delete path and leaving no residue.

Every test is marked ``smoke`` (lane conftest) and runs only by explicit path
(``uv run pytest tests/smoke``) against ``SMOKE_BASE_URL`` with ``SMOKE_ID_TOKEN``.
"""

from __future__ import annotations

import json

from httpx import AsyncClient


class TestSmoke:
    """Ordered, layered checks sharing one smoke session for guaranteed cleanup.

    The session id is stashed on the class by the create check and consumed by the
    later checks, so the layers run cheapest-first and the cleanup check always has the
    id it needs to delete. pytest runs tests in declaration order within a class, so the
    L0 -> L1 -> L2 -> cleanup sequence holds without an ordering plugin.
    """

    session_id: str

    async def test_l0_health_liveness(self, client: AsyncClient) -> None:
        """L0: the deployed revision answers the liveness probe."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_l1_session_create(
        self, client: AsyncClient, app_name: str, user_id: str
    ) -> None:
        """L1: a session persists, proving Cloud SQL reachability via Auth Proxy."""
        resp = await client.post(
            f"/apps/{app_name}/users/{user_id}/sessions",
            json={"state": {}},
        )
        assert resp.status_code == 200
        session_id = resp.json()["id"]
        assert session_id
        TestSmoke.session_id = session_id

    async def test_l2_agent_turn_streams_text(
        self, client: AsyncClient, app_name: str, user_id: str
    ) -> None:
        """L2: the run path streams at least one text-bearing event.

        Invokes the real model. Asserts presence of a text part only — never its
        content — so the check is robust to the model's stochastic output.
        """
        body = {
            "app_name": app_name,
            "user_id": user_id,
            "session_id": TestSmoke.session_id,
            "new_message": {"role": "user", "parts": [{"text": "Hi!"}]},
            "streaming": True,
        }

        saw_text = False
        async with client.stream("POST", "/run_sse", json=body) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if not payload:
                    continue
                event = json.loads(payload)
                parts = event.get("content", {}).get("parts", [])
                if any(isinstance(p.get("text"), str) and p["text"] for p in parts):
                    saw_text = True
                    break

        assert saw_text, "no text-bearing event in the /run_sse stream"

    async def test_l3_cleanup_session_deleted(
        self, client: AsyncClient, app_name: str, user_id: str
    ) -> None:
        """Cleanup: the smoke session is deleted and a follow-up GET returns 404."""
        session_id = TestSmoke.session_id
        delete = await client.delete(
            f"/apps/{app_name}/users/{user_id}/sessions/{session_id}"
        )
        assert delete.status_code == 200

        gone = await client.get(
            f"/apps/{app_name}/users/{user_id}/sessions/{session_id}"
        )
        assert gone.status_code == 404
