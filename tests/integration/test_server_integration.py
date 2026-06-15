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

pytestmark = [
    pytest.mark.integration,
    # The app/client fixtures are session-scoped (one connection pool per run); their
    # async setup and these tests must share one event loop or the pool's asyncpg
    # connections are created on a loop that's closed before engine disposal.
    pytest.mark.asyncio(loop_scope="session"),
]

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
        self, client, app_name, mock_response_text
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
            part.get("text") == mock_response_text
            for event in events
            for part in event.get("content", {}).get("parts", [])
        )

        reloaded = await client.get(
            f"/apps/{app_name}/users/{USER_ID}/sessions/{session_id}"
        )
        assert reloaded.status_code == 200
        body = reloaded.json()
        assert body["state"]["seed"] == "value"
        # Both the user message and the stubbed model response persisted to Postgres.
        # Assert presence rather than an exact count: ADK does not guarantee a fixed
        # persisted-event count and the lane tracks weekly ADK releases, so a future
        # lifecycle/state-delta event must not read as a false regression.
        persisted = body["events"]
        assert len(persisted) >= 2
        assert any(
            event.get("content", {}).get("role") == "user" for event in persisted
        )
        assert any(
            part.get("text") == mock_response_text
            for event in persisted
            for part in event.get("content", {}).get("parts", [])
        )


class TestSessionDeleteCascadesToEvents:
    """A raw session delete cascades to its events via the Postgres FK.

    The scheduled ``pg_cron`` retention job deletes stale rows straight from the
    ``sessions`` table with raw SQL, relying on the events FK's ``ON DELETE CASCADE``
    to remove the orphaned events. ADK's API delete instead uses the ORM relationship
    cascade (``all, delete-orphan``), so only a direct ``DELETE`` exercises the
    database-level constraint the retention job actually depends on — a dropped
    ``ondelete="CASCADE"`` would orphan events here while the API path still passed.
    """

    async def test_raw_session_delete_removes_events(
        self, client, app_name, database_uri
    ) -> None:
        """Deleting a session row directly leaves none of its events behind."""
        create = await client.post(
            f"/apps/{app_name}/users/{USER_ID}/sessions",
            json={"state": {}},
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

        params = {"app": app_name, "user": USER_ID, "sid": session_id}
        count_stmt = text(
            "SELECT count(*) FROM events "
            "WHERE app_name = :app AND user_id = :user AND session_id = :sid"
        )
        engine = create_async_engine(database_uri)
        try:
            async with engine.connect() as conn:
                before = (await conn.execute(count_stmt, params)).scalar_one()
            assert before > 0

            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "DELETE FROM sessions "
                        "WHERE app_name = :app AND user_id = :user AND id = :sid"
                    ),
                    params,
                )

            async with engine.connect() as conn:
                after = (await conn.execute(count_stmt, params)).scalar_one()
            assert after == 0
        finally:
            await engine.dispose()


class TestPostgresDialectStrictness:
    """asyncpg rejects ISO strings for typed columns where sqlite tolerates them.

    These tests demonstrate the asyncpg strictness constraint that motivates the
    ``text(...).bindparams(...)`` convention documented in AGENTS.md. Binding a typed
    column requires native Python objects (or a dialect-aware ``bindparam``); an ISO
    string bound without type info raises ``DataError`` against asyncpg but silently
    coerces under sqlite, so a sqlite-only suite would miss the bug.
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
                # The CAST target drives asyncpg's timestamptz codec inference, so the
                # str is rejected before it reaches Postgres — the same failure mode the
                # production path hits without a dialect-aware bindparam.
                stmt = text("SELECT CAST(:ts AS timestamptz) AS ts")
                with pytest.raises(
                    Exception, match=r"expected a datetime\.date.*got 'str'"
                ):
                    await conn.execute(stmt, {"ts": "2026-06-11T00:00:00+00:00"})
        finally:
            await engine.dispose()
