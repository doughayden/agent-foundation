"""Fixtures for the integration lane (real Postgres + FastAPI, no mocks, no LLM).

This lane builds the production FastAPI app via ADK ``get_fast_api_app()`` against a
real ``postgresql+asyncpg://`` session service (a real ``DatabaseSessionService``) and
drives it in-process with httpx ``ASGITransport``. The only substitution is the LLM:
``root_agent.model`` is replaced with a deterministic stub so the run path persists and
reads session state without a network call or cost. The session service itself is never
mocked.

The root ``tests/conftest.py`` ``pytest_configure()`` already patches
``dotenv.load_dotenv`` and ``google.auth.default`` for every lane, so no GCP
credentials are required here.

Postgres connection is read from ``INTEGRATION_DATABASE_URI`` (default points at a
local ephemeral container on ``127.0.0.1:5432``). CI provides Postgres via a service
container; locally, run an ephemeral container (see ``docs/references/testing.md``).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from fastapi import FastAPI
    from google.adk.models import LlmRequest

DEFAULT_DATABASE_URI = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sessions"

# App name is the agent package directory name discovered by the ADK agent loader
# under src/ (src/agent_foundation -> "agent_foundation").
APP_NAME = "agent_foundation"

MOCK_RESPONSE_TEXT = "stubbed integration reply"


class MockLlm(BaseLlm):
    """Deterministic, zero-cost stand-in for the real model on the run path.

    Subclasses ``BaseLlm`` so it satisfies the same interface ADK invokes; yields a
    single canned text response and never makes a network call. Agent behavior is
    owned by the eval lane, not this lane.
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


@pytest.fixture(scope="session")
def database_uri() -> str:
    """Postgres URI for the session service, overridable via env var."""
    return os.environ.get("INTEGRATION_DATABASE_URI", DEFAULT_DATABASE_URI)


@pytest.fixture(scope="session")
def app_name() -> str:
    """ADK app name (the agent package directory discovered under src/)."""
    return APP_NAME


@pytest.fixture(scope="session")
def mock_response_text() -> str:
    """Canned text the stubbed model yields on the run path."""
    return MOCK_RESPONSE_TEXT


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def integration_app(database_uri: str) -> AsyncIterator[FastAPI]:
    """Build the production FastAPI app against real Postgres with a stubbed model.

    Reuses production wiring (``get_fast_api_app`` with a real ``postgresql+asyncpg://``
    session service). The only override is replacing ``root_agent.model`` with
    ``MockLlm`` so the run path is deterministic and free; the model is restored at the
    end of the session to avoid leaking the stub into other lanes.

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

    import agent_foundation.agent as agent_mod

    session_service = DatabaseSessionService(db_url=database_uri)
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
            agents_dir=str(Path(__file__).parent.parent.parent / "src"),
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
