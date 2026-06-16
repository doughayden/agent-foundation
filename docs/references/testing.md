# Testing Strategy

Detailed testing patterns, organization, and requirements for the project.

## Test Lanes

A test's lane is decided by its runtime requirements and determinism, not by how many components it touches.

| Lane | Needs | Deterministic | Cost | Local command |
|---|---|---|---|---|
| unit | in-process only (mocks at boundaries) | yes | free/fast | `uv run pytest` (default) |
| integration | real external resource (Postgres) | yes | slower, no LLM/cloud | `uv run pytest tests/integration` |
| smoke | a live deployed URL | yes | needs a deploy | `uv run pytest tests/smoke` |
| eval | the real LLM | gate metrics yes; judge metrics no | costs money | `uv run pytest eval` |

The `tests/` lanes never call the live model; the `eval/` lane does. Non-unit lanes run by explicit path, both locally and in CI — the command or CI job is the selector. `testpaths = ["tests/unit"]` in `pyproject.toml` scopes a bare `uv run pytest` to the fast, free, deterministic lane so it can't accidentally require Postgres. An explicit path argument overrides it. Eval mechanics, commands, and gotchas live in [Agent Evals](agent-evals.md).

Only the unit lane runs `--cov` with the 100% gate.

## Integration Lane

The integration lane (`tests/integration/`) exercises the real FastAPI app against a real Postgres session service with no mocks. It builds the production app via ADK `get_fast_api_app()` with a `postgresql+asyncpg://` URI (a real `DatabaseSessionService`) and drives it in-process with httpx `ASGITransport`. The only substitution is the LLM: `root_agent.model` is replaced with a deterministic stub, so the run path persists and reads session state without a network call or cost. Agent behavior is owned by the eval lane, not this one.

### What it covers

- Session lifecycle through the API: create, get, list, delete
- An agent run that persists events and reads back session state
- Postgres dialect strictness: asyncpg rejects ISO strings for `timestamptz` where sqlite tolerates them, so direct SQL binds native Python objects via typed `bindparam`. These tests demonstrate the asyncpg strictness constraint that motivates the typed-bindparam convention in AGENTS.md; the session-lifecycle and agent-run tests are what actually catch dialect regressions through `DatabaseSessionService`.

### Run it locally

Start an ephemeral Postgres container, run the lane, then tear it down:

```bash
docker run -d --rm --name your-agent-pg \
  -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sessions \
  postgres:17

uv run pytest tests/integration

docker stop your-agent-pg
```

The connection defaults to `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sessions`. Override it with the `INTEGRATION_DATABASE_URI` environment variable to point at a different host or port. This is a test-harness variable, not application runtime config, so it lives here rather than in `docs/environment-variables.md`.

> [!NOTE]
> The lane needs no GCP credentials. The root `tests/conftest.py` `pytest_configure()` patches `dotenv.load_dotenv` and `google.auth.default` for every lane.

### How CI provides Postgres

The `ci.yml` `integration` job runs a `postgres:17` service container (with a `pg_isready` health check) and sets `INTEGRATION_DATABASE_URI` to reach it. It is gated on the `changes` job and folded into the always-runs `status` sentinel, so the single required check `CI / status` covers it. The job runs `uv run pytest tests/integration` without `--cov` — the 100% coverage gate is unit-lane-only.

## Smoke Lane

The smoke lane (`tests/smoke/`) hits the live deployed Cloud Run service URL after each environment apply to confirm a freshly deployed revision actually serves end to end. Unlike the integration lane, which builds the app in-process via httpx `ASGITransport`, nothing here is substituted: the request crosses the real network, the Auth Proxy sidecar, and Cloud SQL. The L2 turn invokes the real model, but the lane is still a deterministic gate. Behavioral correctness stays owned by the eval lane, pre-deploy wiring by the integration lane.

### What each layer catches

Checks run cheapest-first, each a distinct failure class so a failure localizes the broken subsystem:

- **L0 liveness**: `GET /health` -> 200. The revision serves HTTP at all.
- **L1 session create**: create a session, read it back -> 200. Cloud SQL is reachable through the Auth Proxy sidecar over VPC egress, and a session row persists. Deterministic, no model. A module-scoped fixture owns the create so teardown deletes the row unconditionally even when a later check fails.
- **L2 thin agent turn**: `POST /run_sse` with a trivial prompt, parse the SSE event stream, and assert at least one event carries a text part. The real model is invoked, but the assertion checks only that a text part returned, never what it says, so the check is robust to the model's stochastic output and carries no LLM-judge dependency.
- **Cleanup**: delete the smoke session, then a follow-up GET returns 404. Proves the delete path and leaves no residue.

### Run it locally

The lane targets a live deployed URL with an authenticated client, so it reads two env vars and fails clearly if either is unset:

```bash
SMOKE_BASE_URL="https://your-agent-dev-...run.app" \
SMOKE_ID_TOKEN="$(gcloud auth print-identity-token \
  --impersonate-service-account=SMOKE_INVOKER_SA \
  --audiences=https://your-agent-dev-...run.app)" \
  uv run pytest tests/smoke
```

- `SMOKE_BASE_URL`: the deployed service URL (the httpx `base_url`).
- `SMOKE_ID_TOKEN`: a Cloud Run ID token, sent as `Authorization: Bearer`.

Both are test-harness variables, not application runtime config, so they live here rather than in `docs/environment-variables.md`. A bare `uv run pytest` never collects this lane; select it explicitly with `uv run pytest tests/smoke`.

### How CI runs it post-deploy

The `smoke.yml` reusable workflow resolves the service URL with `gcloud run services describe`, resolves the dedicated invoker SA by display name, mints a Cloud Run ID token by impersonating it (`gcloud auth print-identity-token --impersonate-service-account --audiences`), runs the lane, and surfaces pass/fail in the GitHub job summary. The service deploys `--no-allow-unauthenticated`, so requests need an identity token; Cloud Run authorizes the token identity, the invoker SA. The `ci-cd.yml` orchestrator calls it as `smoke-dev` after `dev-apply` (and `smoke-stage` after `stage-apply` in production mode). This runs post-deploy against the live revision, not in the PR gate. The invoker identity and its least-privilege scoping are documented in [Security Posture](security-posture.md).

## Coverage Requirements

**100% coverage required on production code.**

**Included:**
- All code in `src/` except explicitly excluded files (see below)

**Excluded:**
- `server.py` (FastAPI entrypoint - validate server behavior with integration tests)
- `**/agent.py` (pure ADK configuration - tests are the upstream project's responsibility)
- `**/prompt.py` (prompt templates - validate agent behavior with evaluations)
- `**/__init__.py` (module initialization)

## Test Organization

### Directory Structure

Lanes are top-level directories; unit test modules mirror source structure:

```
eval/                            # LLM eval lane
tests/
  conftest.py                    # Shared fixtures, mocks, and test environment setup (all lanes)
  unit/
    test_callbacks.py            # Tests for src/your_agent/callbacks.py
    test_tools.py                # Tests for src/your_agent/tools.py
    test_config.py               # Tests for src/your_agent/config.py
    ...
  integration/                   # Postgres + FastAPI lane
  smoke/                         # Live deployed-URL lane
```

The root `tests/conftest.py` applies to all `tests/` lanes (auth/dotenv mocking). Per-lane `conftest.py` files (e.g. a Postgres fixture in `integration/`) live in their lane directory. The eval lane lives outside `tests/` in the top-level `eval/` directory and loads the real `.env` itself (an autouse fixture in the test module).

### Naming Conventions

- **Files:** test module path mirrors source path: `src/<pkg>/config.py → tests/unit/test_config.py`; nested source paths flatten with underscores (`<pkg>/sub/foo.py → test_sub_foo.py`)
- **Functions:** `test_<what>_<condition>_<expected>`
- **Classes:** Group related tests for the same module/class (style preference)

### Shared Fixtures

All reusable fixtures go in `tests/conftest.py`:
- Type hint fixture definitions with both parameters and return types
- Use pytest-mock type aliases for returns: `MockType`, `AsyncMockType`
- Factory pattern (not context managers)

## Fixture Patterns

### Test Double Naming

Test double classes and fixtures follow a strict naming convention (established in root `conftest.py`):

| Kind | Prefix | Example | Returns |
|---|---|---|---|
| Test double class | `Mock` | `MockState`, `MockOAuthContextStore` | — (defined in conftest) |
| Instance fixture | `mock_` | `mock_state`, `mock_chat_client` | Single mock instance |
| Factory fixture | `create_mock_` | `create_mock_state`, `create_mock_oauth_store` | `Callable` that builds instances |
| Convenience fixture | (none) | `oauth_flow_config`, `valid_server_env` | Real objects / test data |

Factory fixtures use `_factory` as their inner function name:

```python
@pytest.fixture
def create_mock_state() -> Callable[..., MockState]:
    def _factory(data: dict | None = None) -> MockState:
        return MockState(data)
    return _factory
```

### Type Hints

**Fixture definitions (strict in conftest.py):**
```python
from pytest_mock import MockerFixture
from pytest_mock.plugin import MockType

@pytest.fixture
def mock_session(mocker: MockerFixture) -> MockType:
    """Create a mock ADK session."""
    return mocker.MagicMock(spec=...)
```

**Test functions (relaxed):**
- Don't type hint custom fixtures (pytest handles DI by name)
- Optional type hints on built-in fixtures for IDE support

### Environment Mocking

**No base env vars in `pytest_configure()`:** No module in the test import graph reads env vars at module level. `server.py` does (`initialize_environment` at line 26), but it's never imported during collection (PEP 562 lazy loading, coverage-excluded). Environment variables are set in test fixtures using `mocker.patch.dict`:

```python
def test_config_with_custom_region(mocker: MockerFixture) -> None:
    """Test configuration with non-default region."""
    mocker.patch.dict(os.environ, {"GOOGLE_CLOUD_LOCATION": "us-west1"})
    # Test config loading with custom region
```

If a future import chain triggers env var reads at collection time, add direct `os.environ` assignments in `pytest_configure()` (see section below).

## ADK Mock Strategy

### Using Conftest Fixtures

Prefer fixtures from `conftest.py` for standard mocks:
- `mock_state` - ADK state object
- `mock_session` - ADK session
- `mock_context` - ReadonlyContext with user_id

### Never Import Mock Classes

Never import mock classes directly in test files. Always use or add a fixture in `conftest.py`. For edge cases requiring custom internal structure, add a specific named fixture (e.g., `mock_event_non_text_content`) rather than importing the class.

### Mirror Real Interfaces

ADK mocks must exactly mirror real ADK interfaces:
- Use `spec=` parameter to enforce interface
- Include all properties and methods used in code
- Match return types and signatures

## pytest_configure()

**Special case: unittest.mock before pytest-mock available**

`pytest_configure()` runs before test collection, so pytest-mock isn't available yet.
Use `unittest.mock` here for setup that must happen before tests load:

```python
def pytest_configure() -> None:
    """Configure test environment before test collection."""
    from unittest.mock import Mock, patch

    # Patch load_dotenv to prevent loading real .env
    patch("dotenv.load_dotenv").start()

    # Patch google.auth.default to prevent ADC lookup
    mock_creds = Mock(token="fake", valid=True, expired=False)
    patch("google.auth.default", return_value=(mock_creds, "test-project")).start()
    patch("google.auth._default.default", return_value=(mock_creds, "test-project")).start()

    # Environment variables: No module in the test import graph reads env vars at
    # module level. server.py does (initialize_environment(ServerEnv)), but it's
    # never imported during collection (PEP 562 lazy loading, coverage-excluded).
    # If a future import chain triggers env var reads at collection time, set
    # defaults here using direct assignment:
    # import os
    # os.environ["KEY"] = "value"
```

See `tests/conftest.py` for the complete implementation with detailed lifecycle comments.

## Pydantic Validation Testing

### Validation Timing

Pydantic validates at model creation, not at property access:

```python
# Validation happens here ✓
config = ServerEnv.model_validate(env_dict)

# NOT here ✗
value = config.some_property
```

### Testing Validation

Expect `ValidationError` at model creation:

```python
import pytest
from pydantic import ValidationError

def test_config_invalid_project_id():
    """Test that empty project ID raises validation error."""
    env_dict = {"GOOGLE_CLOUD_PROJECT": ""}

    with pytest.raises(ValidationError):
        ServerEnv.model_validate(env_dict)
```

## What to Test

### Behaviors

Test function outputs and state changes:
- Return values are correct
- State is modified as expected
- Side effects occur (logging, callbacks)

### Error Conditions

Test invalid inputs and edge cases:
- Invalid parameter types
- Missing required values
- Boundary conditions (empty, max, negative)

### Integration Points

App and agent wiring (callbacks registered, tools attached, configuration flow) is validated by the integration lane against a real server.

## Mypy Scope

mypy is scoped to the source package. Test modules are not type-checked; conftest typing is a team convention enforced by reviewers. Full rationale and the expected-error categories that surface if you run `uv run mypy src tests` are in [Code Quality → Test Suite Typing Strategy](code-quality.md#test-suite-typing-strategy).

## Running Tests

```bash
# Unit lane (default) with full coverage report
uv run pytest --cov --cov-report=term-missing

# HTML report for detailed view
uv run pytest --cov --cov-report=html
open htmlcov/index.html

# Other lanes by explicit path
uv run pytest tests/integration
uv run pytest tests/smoke
uv run pytest eval

# Specific tests
uv run pytest tests/unit/test_callbacks.py -v
uv run pytest tests/unit/test_file.py::test_name -v

# Watch mode (requires pytest-watch)
uv run ptw
```

## Agent Evals

The eval lane scores real agent behavior against committed eval sets, the only lane that catches LLM behavioral regression. The deterministic gate, `uv run pytest eval`, runs on every code PR via the `agent-eval` job and folds into the `CI / status` required check. `tests/unit/test_eval_artifacts.py` schema-checks every eval artifact in the unit lane, so malformed eval data fails fast with no LLM cost.

The full eval surface, formats, every `adk` command, the metrics table, the deterministic-gate rationale, user simulation, and gotchas, lives in [Agent Evals](agent-evals.md).

## Examples

See `tests/conftest.py` and existing test files for complete patterns:
- Fixture factories
- ADK mocks
- Environment mocking
- Pydantic validation tests
- Async test patterns (with pytest-asyncio)

---

← [Back to References](README.md) | [Documentation](../README.md)
