"""Integration tests: real FastAPI app against real Postgres, no mocks, no LLM.

Validates that the wired components (ADK ``get_fast_api_app()``,
``DatabaseSessionService``, asyncpg, session persistence) work together against the
Postgres dialect, not just sqlite. The session service is never mocked; the only
substitution is a deterministic stubbed model on the run path (``MockLlm`` below).

This lane builds the production FastAPI app via ADK ``get_fast_api_app()`` against a
real ``postgresql+asyncpg://`` session service and drives it in-process with httpx
``ASGITransport``. Only the LLM is replaced (``root_agent.model`` -> ``MockLlm``) so the
run path persists and reads session state without a network call or cost.

Every test carries two module-level marks (``pytestmark``): ``integration`` (the lane
runs only by explicit path, ``uv run pytest tests/integration``) and
``asyncio(loop_scope="session")``. The session loop scope is required because the
``integration_app`` and ``client`` fixtures are session-scoped (one connection pool per
run): their async setup and these tests must share one event loop, or the pool's asyncpg
connections get created on a loop that's closed before engine disposal.

Postgres connection is read from ``INTEGRATION_DATABASE_URI`` (default points at a
local ephemeral container on ``127.0.0.1:5432``). CI provides Postgres via a service
container; locally, run an ephemeral container (see
``docs/references/integration-tests.md``).

The lane needs no GCP credentials. The ``_mock_gcp_credentials`` autouse session
fixture below blocks real ADC and ``.env`` lookups. A fixture suffices because this
module imports the source package lazily — inside ``integration_app``, not at
collection — so the patch is in place before any agent code runs.
"""

from __future__ import annotations

import datetime
import importlib
import os
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from httpx import ASGITransport, AsyncClient
from pytest_mock import MockerFixture
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.types import DateTime

DEFAULT_DATABASE_URI = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sessions"

# Postgres URI for the session service. Defaults to a local ephemeral container;
# CI points it at a service container via INTEGRATION_DATABASE_URI.
DATABASE_URI = os.environ.get("INTEGRATION_DATABASE_URI", DEFAULT_DATABASE_URI)

# Source root holding the single agent package (src/<package>/). Both the ADK app name
# and the agent module are derived from it so a downstream fork that renames the package
# reuses this lane with no edits.
SRC_DIR = Path(__file__).parents[2] / "src"

# The ADK app name is that package's directory name. The template has exactly one
# package under src/, so the lone dir with an __init__.py is unambiguous; the marker
# skips non-package entries (.DS_Store, *.egg-info).
APP_NAME = next(SRC_DIR.glob("*/__init__.py")).parent.name

MOCK_RESPONSE_TEXT = "stubbed integration reply"

USER_ID = "integration-user"


class MockLlm(BaseLlm):
    """Deterministic, zero-cost stand-in for the real model on the run path.

    Subclasses ``BaseLlm`` so it satisfies the same interface ADK invokes; yields a
    single canned text response and never makes a network call. A canned reply is all
    the run path needs to exercise session persistence.
    """

    model: str = "stub-model"

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        """Yield one canned model response regardless of the request."""
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=MOCK_RESPONSE_TEXT)],
            )
        )


@pytest.fixture(scope="session", autouse=True)
def _mock_gcp_credentials(session_mocker: MockerFixture) -> None:
    """Block real ADC and ``.env`` lookups for the whole lane.

    Runs as an autouse session fixture set up before the session-scoped
    ``integration_app`` fixture, which is the only place the source package is
    imported, so the patch is active before any agent code runs. Uses
    ``session_mocker`` (not ``unittest.mock``) since fixtures run after pytest-mock
    is available.
    """
    mock_credentials = session_mocker.Mock()
    mock_credentials.token = "test-mock-token-totally-not-real"  # noqa: S105
    mock_credentials.valid = True
    mock_credentials.expired = False
    mock_credentials.refresh = session_mocker.Mock()
    mock_credentials.universe_domain = "googleapis.com"
    session_mocker.patch("dotenv.load_dotenv")
    # Patch both public and private auth paths (ADK uses private path internally).
    session_mocker.patch(
        "google.auth.default", return_value=(mock_credentials, "test-project")
    )
    session_mocker.patch(
        "google.auth._default.default",
        return_value=(mock_credentials, "test-project"),
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def integration_app() -> AsyncIterator[FastAPI]:
    """Build the production FastAPI app against real Postgres with a stubbed model.

    Reuses production wiring (``get_fast_api_app`` with a real ``postgresql+asyncpg://``
    session service). The only override is replacing ``root_agent.model`` with
    ``MockLlm`` so the run path is deterministic and free; the model is restored at the
    end of the session so the stub does not persist on the shared ``root_agent``.

    The session service is constructed explicitly here and injected by patching ADK's
    ``create_session_service_from_options`` factory (the binding ``get_fast_api_app``
    actually calls) so the fixture owns the connection pool and disposes its engine on
    teardown. ``get_fast_api_app`` otherwise builds the service from the URI internally
    and discards the handle, so its asyncpg pool would leak; ADK's ``internal_lifespan``
    closes runners but never disposes the session engine, and httpx ``ASGITransport``
    never emits ASGI lifespan events in any case. Session-scoped so one pool is built
    and disposed per run rather than one per test.

    ADK's ``get_fast_api_app`` accepts only ``session_service_uri`` (a URI string), not
    a pre-built service object, so the factory binding is the only injection point. No
    upstream adk-python issue requests a ``session_service`` parameter yet. Remove this
    patch when such a parameter lands.
    """
    import google.adk.cli.fast_api as fast_api_mod
    from google.adk.cli.fast_api import get_fast_api_app

    agent_mod = importlib.import_module(f"{APP_NAME}.agent")

    session_service = DatabaseSessionService(db_url=DATABASE_URI)
    original_model = agent_mod.root_agent.model
    agent_mod.root_agent.model = MockLlm()
    original_factory = fast_api_mod.create_session_service_from_options
    fast_api_mod.create_session_service_from_options = (
        lambda *args, **kwargs: session_service
    )
    try:
        # The factory patch above supplies the session service; no URI is passed
        # here since get_fast_api_app would otherwise build (and leak) its own.
        app = get_fast_api_app(
            agents_dir=str(SRC_DIR),
            web=False,
        )
        yield app
    finally:
        fast_api_mod.create_session_service_from_options = original_factory
        agent_mod.root_agent.model = original_model
        await session_service.db_engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(integration_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """In-process httpx client driving the app over ASGI (no socket, no server)."""
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://integration") as c:
        yield c


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


class TestSessionLifecycle:
    """Session create / get / list / delete through the FastAPI surface."""

    async def test_create_get_list_delete_session(self, client) -> None:
        """A session can be created, fetched, listed, then deleted via the API."""
        create = await client.post(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions",
            json={"state": {"favorite_color": "blue"}},
        )
        assert create.status_code == 200
        session_id = create.json()["id"]

        get = await client.get(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{session_id}"
        )
        assert get.status_code == 200
        assert get.json()["state"]["favorite_color"] == "blue"

        listing = await client.get(f"/apps/{APP_NAME}/users/{USER_ID}/sessions")
        assert listing.status_code == 200
        assert any(s["id"] == session_id for s in listing.json())

        delete = await client.delete(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{session_id}"
        )
        assert delete.status_code == 200

        gone = await client.get(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{session_id}"
        )
        assert gone.status_code == 404

    async def test_get_missing_session_returns_404(self, client) -> None:
        """Fetching a nonexistent session returns 404 from the real service."""
        missing = await client.get(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/does-not-exist"
        )
        assert missing.status_code == 404


class TestAgentRunStatePersistence:
    """An agent run persists events and reads back session state."""

    async def test_run_persists_events_and_state(self, client) -> None:
        """Running the agent appends events to the session in Postgres.

        The model is stubbed (no LLM call). After the run, the session reloaded from
        Postgres contains both the user message and the model response event.
        """
        create = await client.post(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions",
            json={"state": {"seed": "value"}},
        )
        assert create.status_code == 200
        session_id = create.json()["id"]

        run = await client.post(
            "/run",
            json={
                "app_name": APP_NAME,
                "user_id": USER_ID,
                "session_id": session_id,
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )
        assert run.status_code == 200
        events = run.json()
        assert any(
            part.get("text") == MOCK_RESPONSE_TEXT
            for event in events
            for part in event.get("content", {}).get("parts", [])
        )

        reloaded = await client.get(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions/{session_id}"
        )
        assert reloaded.status_code == 200
        body = reloaded.json()
        assert body["state"]["seed"] == "value"
        # Both the user message and the stubbed model response persisted to Postgres.
        # Assert only presence: ADK does not guarantee a fixed persisted-event count,
        # so a future lifecycle/state-delta event must not read as a false regression.
        persisted = body["events"]
        assert len(persisted) >= 2
        assert any(
            event.get("content", {}).get("role") == "user" for event in persisted
        )
        assert any(
            part.get("text") == MOCK_RESPONSE_TEXT
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

    async def test_raw_session_delete_removes_events(self, client) -> None:
        """Deleting a session row directly leaves none of its events behind."""
        create = await client.post(
            f"/apps/{APP_NAME}/users/{USER_ID}/sessions",
            json={"state": {}},
        )
        assert create.status_code == 200
        session_id = create.json()["id"]

        run = await client.post(
            "/run",
            json={
                "app_name": APP_NAME,
                "user_id": USER_ID,
                "session_id": session_id,
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )
        assert run.status_code == 200

        params = {"app": APP_NAME, "user": USER_ID, "sid": session_id}
        count_stmt = text(
            "SELECT count(*) FROM events "
            "WHERE app_name = :app AND user_id = :user AND session_id = :sid"
        )
        engine = create_async_engine(DATABASE_URI)
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

    async def test_timestamptz_requires_typed_bindparam(self) -> None:
        """A native datetime via a typed bindparam round-trips through timestamptz."""
        engine = create_async_engine(DATABASE_URI)
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

    async def test_timestamptz_rejects_iso_string(self) -> None:
        """An ISO string bound without type info is rejected by asyncpg."""
        engine = create_async_engine(DATABASE_URI)
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
