# Testing Strategy

The lane taxonomy and the unit-test guide; the specialized lanes link to their own references.

## Test Lanes

A test's lane is decided by its runtime requirements and determinism, not by how many components it touches.

| Lane | Needs | Deterministic | Cost | Local command |
|---|---|---|---|---|
| unit | in-process only (mocks at boundaries) | yes | free/fast | `uv run pytest` (default) |
| integration | real external resource (Postgres) | yes | slower, no LLM/cloud | `uv run pytest tests/integration` |
| smoke | a live deployed URL | yes | needs a deploy | `uv run pytest tests/smoke` |
| eval | the real LLM | gate metrics yes; judge metrics no | costs money | `uv run pytest tests/eval` |

The unit, integration, and smoke lanes never call the live model; the eval lane does. Evals are still a test shape, so the lane lives under `tests/` alongside the others — pytest uses importlib import mode (location-agnostic), and `adk eval` takes explicit evalset and config filepaths, so nothing depends on where the lane sits. Non-unit lanes run by explicit path, both locally and in CI — the command or CI job is the selector. `testpaths = ["tests/unit"]` in `pyproject.toml` scopes a bare `uv run pytest` to the fast, free, deterministic lane so it can't accidentally require Postgres. An explicit path argument overrides it.

Only the unit lane runs `--cov` with the 100% gate.

## Specialized Lanes

The rest of this guide covers the unit lane. The non-unit lanes each carry their own reference doc:

- **Integration** (`tests/integration/`) — the real FastAPI app against a real Postgres session service, no mocks. See [Integration Tests](integration-tests.md).
- **Smoke** (`tests/smoke/`) — assertions against a live deployed URL, run post-deploy against a freshly applied Cloud Run revision. See [Smoke Tests](smoke-tests.md).
- **Eval** (`tests/eval/`) — real agent behavior scored against committed eval sets; the only lane that catches LLM behavioral regression. Cases split by pytest marker: `deterministic` (exact tool-trajectory + ROUGE match, the PR gate) and `judge` (LLM-judged, non-deterministic). Inference runs the full `App` and its plugins, so evals score the same agent the deployed server runs. The deterministic gate runs on every code PR, and `tests/unit/test_eval_artifacts.py` schema-checks the eval data in the unit lane. See [Agent Evals](agent-evals.md).

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
tests/
  eval/                          # LLM eval lane (real model, deterministic + judge markers)
  unit/
    conftest.py                  # Shared fixtures, mocks, and unit test environment setup
    test_callbacks.py            # Tests for src/your_agent/callbacks.py
    test_tools.py                # Tests for src/your_agent/tools.py
    test_config.py               # Tests for src/your_agent/config.py
    ...
  integration/                   # Postgres + FastAPI lane
    test_server_integration.py   # Fixtures, mocks, and tests in one module
  smoke/                         # Live deployed-URL lane
```

Each lane owns its credential posture: the unit lane's `tests/unit/conftest.py` mocks credentials within the `pytest_configure` hook; the integration lane mocks credentials in an autouse session fixture; the smoke lane uses real credentials. The eval lane loads the real `.env` itself (an autouse fixture in the test module). There is deliberately no shared `tests/conftest.py` — its absence keeps the unit lane's credential mocking out of the eval and smoke lanes, which run against real credentials.

### Naming Conventions

- **Files:** test module path mirrors source path: `src/<pkg>/config.py → tests/unit/test_config.py`; nested source paths flatten with underscores (`<pkg>/sub/foo.py → test_sub_foo.py`)
- **Functions:** `test_<what>_<condition>_<expected>`
- **Classes:** Group related tests for the same module/class (style preference)

### Shared Fixtures

All reusable unit-lane fixtures go in `tests/unit/conftest.py`:
- Type hint fixture definitions with both parameters and return types
- Use pytest-mock type aliases for returns: `MockType`, `AsyncMockType`
- Factory pattern (not context managers)

## Fixture Patterns

### Test Double Naming

Test double classes and fixtures follow a strict naming convention (established in `tests/unit/conftest.py`):

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

See `tests/unit/conftest.py` for the complete implementation with detailed lifecycle comments.

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
uv run pytest tests/eval

# Specific tests
uv run pytest tests/unit/test_callbacks.py -v
uv run pytest tests/unit/test_file.py::test_name -v

# Watch mode (requires pytest-watch)
uv run ptw
```

## Examples

See `tests/unit/conftest.py` and existing test files for complete patterns:
- Fixture factories
- ADK mocks
- Environment mocking
- Pydantic validation tests
- Async test patterns (with pytest-asyncio)

---

← [Back to References](README.md) | [Documentation](../README.md)
