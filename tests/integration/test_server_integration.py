"""Integration tests: real FastAPI app against real Postgres, no mocks, no LLM.

Validates that the wired components (ADK ``get_fast_api_app()``,
``DatabaseSessionService``, asyncpg, session persistence) work together against the
Postgres dialect, not just sqlite. The session service is never mocked; the only
substitution is a deterministic stubbed model on the run path (see the lane conftest).

Every test is marked ``integration`` and runs only by explicit path
(``uv run pytest tests/integration``); a bare ``pytest`` runs the unit lane.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.types import DateTime

pytestmark = pytest.mark.integration

USER_ID = "integration-user"


class TestSessionLifecycle:
    """Session create / get / list / delete through the FastAPI surface."""

    async def test_create_get_list_delete_session(self, client, app_name) -> None:
        """A session can be created, fetched, listed, then deleted via the API."""
        create = await client.post(
            f"/apps/{app_name}/users/{USER_ID}/sessions",
            json={"state": {"favorite_color": "blue"}},
        )
        assert create.status_code == 200
        session_id = create.json()["id"]

        get = await client.get(
            f"/apps/{app_name}/users/{USER_ID}/sessions/{session_id}"
        )
        assert get.status_code == 200
        assert get.json()["state"]["favorite_color"] == "blue"

        listing = await client.get(f"/apps/{app_name}/users/{USER_ID}/sessions")
        assert listing.status_code == 200
        assert any(s["id"] == session_id for s in listing.json())

        delete = await client.delete(
            f"/apps/{app_name}/users/{USER_ID}/sessions/{session_id}"
        )
        assert delete.status_code == 200

        gone = await client.get(
            f"/apps/{app_name}/users/{USER_ID}/sessions/{session_id}"
        )
        assert gone.status_code == 404

    async def test_get_missing_session_returns_404(self, client, app_name) -> None:
        """Fetching a nonexistent session returns 404 from the real service."""
        missing = await client.get(
            f"/apps/{app_name}/users/{USER_ID}/sessions/does-not-exist"
        )
        assert missing.status_code == 404


class TestAgentRunStatePersistence:
    """An agent run persists events and reads back session state."""

    async def test_run_persists_events_and_state(
        self, client, app_name, stub_response_text
    ) -> None:
        """Running the agent appends events to the session in Postgres.

        The model is stubbed (no LLM call). After the run, the session reloaded from
        Postgres contains both the user message and the model response event.
        """
        create = await client.post(
            f"/apps/{app_name}/users/{USER_ID}/sessions",
            json={"state": {"seed": "value"}},
        )
        assert create.status_code == 200
        session_id = create.json()["id"]

        run = await client.post(
            "/run",
            json={
                "app_name": app_name,
                "user_id": USER_ID,
                "session_id": session_id,
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )
        assert run.status_code == 200
        events = run.json()
        assert any(
            part.get("text") == stub_response_text
            for event in events
            for part in event.get("content", {}).get("parts", [])
        )

        reloaded = await client.get(
            f"/apps/{app_name}/users/{USER_ID}/sessions/{session_id}"
        )
        assert reloaded.status_code == 200
        body = reloaded.json()
        assert body["state"]["seed"] == "value"
        # User message + stubbed model response both persisted to Postgres.
        assert len(body["events"]) == 2


class TestPostgresDialectStrictness:
    """asyncpg rejects ISO strings for typed columns where sqlite tolerates them.

    This is the regression class the lane exists to catch. Binding a typed column
    requires native Python objects (or a dialect-aware ``bindparam``); an ISO string
    bound without type info raises ``DataError`` against asyncpg but silently coerces
    under sqlite, so a sqlite-only suite would miss the bug.
    """

    async def test_timestamptz_requires_typed_bindparam(self, database_uri) -> None:
        """A native datetime via a typed bindparam round-trips through timestamptz."""
        engine = create_async_engine(database_uri)
        try:
            async with engine.connect() as conn:
                now = datetime.datetime.now(tz=datetime.UTC)
                stmt = text("SELECT :ts AS ts").bindparams(
                    bindparam("ts", type_=DateTime(timezone=True))
                )
                result = await conn.execute(stmt, {"ts": now})
                returned = result.scalar_one()
                assert returned == now
        finally:
            await engine.dispose()

    async def test_timestamptz_rejects_iso_string(self, database_uri) -> None:
        """An ISO string bound without type info is rejected by asyncpg."""
        engine = create_async_engine(database_uri)
        try:
            async with engine.connect() as conn:
                stmt = text("SELECT CAST(:ts AS timestamptz) AS ts")
                with pytest.raises(Exception, match="DataError|invalid input|expected"):
                    await conn.execute(stmt, {"ts": "2026-06-11T00:00:00+00:00"})
        finally:
            await engine.dispose()
